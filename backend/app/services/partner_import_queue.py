"""PostgreSQL-backed bounded import queue, with transactional batch checkpoints.

A worker owns a work-row lock (SKIP LOCKED), not an in-memory lease. Losing its
connection releases the claim and rolls back the entire uncheckpointed batch.
Each invalid row uses a savepoint; successes, audit and cursor commit together.
"""
import hashlib
import json
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from backend.app.models.catalog_import import CatalogImportJob
from backend.app.models.brand_operations import CatalogImportWork
from backend.app.models.user import User, BrandProfile
from backend.app.services.brand_catalog_service import BrandCatalogService, CatalogImportError
from backend.app.services.brand_access import resolve
from backend.app.services.partner_audit import append_event


def now():return datetime.now(timezone.utc)


class PartnerImportQueue:
    BATCH_SIZE = 20
    MAX_ATTEMPTS = 5

    def __init__(self, db):self.db = db

    def enqueue(self, user, raw, key, *, csv=False, filename='api_import.json'):
        member = resolve(self.db, user, 'catalog.import', lock=True)
        encoded = raw if isinstance(raw, str) else json.dumps(raw, sort_keys=True, ensure_ascii=False)
        if len(encoded.encode()) > BrandCatalogService.MAX_BYTES:raise HTTPException(413, 'Import exceeds 10 MiB')
        digest = hashlib.sha256(encoded.encode()).hexdigest()
        old = self.db.query(CatalogImportWork).filter_by(brand_id=member.brand_id,idempotency_key=key).first()
        if old:
            if old.payload_hash != digest:raise HTTPException(409,'Idempotency key belongs to another payload')
            return {'job_id':old.job_id,'duplicate':True}
        service = BrandCatalogService(self.db)
        valid,errors,stats = service.parse_csv(raw,member.brand_id) if csv else service._prepare_rows(raw,member.brand_id)
        # Only public remote origins in the deployed CSP are accepted by the
        # new queued workflow. Blank images create drafts for secure upload.
        from urllib.parse import urlsplit
        supported=[]
        for row in valid:
            url=row.get('thumbnail_url')
            if url and (urlsplit(url).scheme!='https' or urlsplit(url).hostname not in {'images.unsplash.com','placehold.co'}):
                errors.append(CatalogImportError(row['_row_number'],'thumbnail_url','Unsupported image host; omit image to create a draft, then upload its image'))
                stats['rejected']+=1
            else:supported.append(row)
        valid=supported
        job = CatalogImportJob(brand_id=member.brand_id,file_name=filename[:500],file_size=len(encoded.encode()),
            status='queued' if valid else 'failed',total_rows=stats['total'],accepted_rows=0,
            rejected_rows=stats['rejected'],duplicate_rows=stats['duplicate'],errors_json=json.dumps([e.to_dict() for e in errors]))
        self.db.add(job);self.db.flush()
        self.db.add(CatalogImportWork(job_id=job.id,brand_id=member.brand_id,actor_id=user.id,
            idempotency_key=key,payload_hash=digest,payload_json=json.dumps(valid),cursor=0,attempts=0,next_attempt_at=now()))
        append_event(self.db,member.brand_id,'BRAND_IMPORT_QUEUED','CatalogImportJob',job.id,
                     after={'total_rows':job.total_rows,'rejected_rows':job.rejected_rows,'payload_hash':digest})
        self.db.commit()
        return {'job_id':job.id,'status':job.status,'duplicate':False}

    def retry(self,user,job_id):
        member=resolve(self.db,user,'catalog.import',lock=True)
        work=self.db.query(CatalogImportWork).filter_by(job_id=job_id,brand_id=member.brand_id).with_for_update().first()
        if not work:raise HTTPException(404,'Import unavailable')
        job=self.db.get(CatalogImportJob,job_id)
        if work.payload_json=='[]':raise HTTPException(409,'No interrupted rows remain to retry')
        if job.status!='failed':raise HTTPException(409,'Only failed jobs can be retried')
        work.attempts=0;work.next_attempt_at=now();work.actor_id=user.id;job.status='queued'
        append_event(self.db,member.brand_id,'BRAND_IMPORT_RETRIED','CatalogImportJob',job.id)
        self.db.commit();return {'job_id':job.id,'status':job.status}

    def run_batch(self,job_id=None,brand_id=None):
        query=self.db.query(CatalogImportWork).join(CatalogImportJob).filter(
            CatalogImportJob.status.in_(['queued','processing']),CatalogImportWork.next_attempt_at<=now())
        if job_id is not None:query=query.filter(CatalogImportWork.job_id==job_id)
        if brand_id is not None:query=query.filter(CatalogImportWork.brand_id==brand_id)
        candidate=query.order_by(CatalogImportWork.job_id).first()
        if not candidate:
            self.db.rollback();return {'processed':0,'state':'idle_or_claimed'}
        # Same lock order as interactive commands: tenant before work row.
        parent=self.db.query(BrandProfile).filter_by(id=candidate.brand_id).with_for_update(skip_locked=True).first()
        if not parent:
            self.db.rollback();return {'processed':0,'state':'idle_or_claimed'}
        work=query.filter(CatalogImportWork.job_id==candidate.job_id).populate_existing().with_for_update(skip_locked=True,of=CatalogImportWork).first()
        if not work:
            self.db.rollback();return {'processed':0,'state':'idle_or_claimed'}
        wid,checkpoint=work.job_id,work.cursor
        try:
            actor=self.db.get(User,work.actor_id)
            if not actor or not actor.is_active:raise ValueError('Import actor unavailable')
            member=resolve(self.db,actor,'catalog.import',lock=True)
            if member.brand_id!=work.brand_id:raise ValueError('Import actor changed tenant')
            job=self.db.get(CatalogImportJob,wid)
            job.status='processing';job.started_at=job.started_at or now()
            # sqlite3 legacy transaction control does not BEGIN on SELECT;
            # without this, releasing the first SAVEPOINT could commit a row.
            connection=self.db.connection()
            if connection.dialect.name=='sqlite' and not connection.connection.driver_connection.in_transaction:
                connection.exec_driver_sql('BEGIN')
            rows=json.loads(work.payload_json)
            errors=json.loads(job.errors_json)
            service=BrandCatalogService(self.db)
            for row in rows[checkpoint:checkpoint+self.BATCH_SIZE]:
                try:
                    with self.db.begin_nested():
                        service.import_products([row],work.brand_id,commit_each=False)
                    job.accepted_rows+=1
                except (ValueError,IntegrityError) as exc:
                    errors.append({'row':row['_row_number'],'field':'row','message':str(exc) if isinstance(exc,ValueError) else 'Catalog identity conflict'})
                    job.rejected_rows+=1
                work.cursor+=1
            job.errors_json=json.dumps(errors)
            work.attempts=0
            if work.cursor>=len(rows):
                job.status='partially_completed' if job.accepted_rows and job.rejected_rows else 'completed' if job.accepted_rows else 'failed'
                job.completed_at=now()
                # Raw upload content is no longer needed after durable completion.
                work.payload_json='[]'
            append_event(self.db,work.brand_id,'BRAND_IMPORT_CHECKPOINT','CatalogImportJob',wid,
                         after={'cursor':work.cursor,'accepted':job.accepted_rows,'rejected':job.rejected_rows,'status':job.status})
            processed=work.cursor-checkpoint
            self.db.commit()
            return {'job_id':wid,'processed':processed,'status':job.status}
        except Exception:
            self.db.rollback()
            work=self.db.query(CatalogImportWork).filter_by(job_id=wid).populate_existing().with_for_update().one()
            job=self.db.get(CatalogImportJob,wid)
            if work.cursor==checkpoint and job.status in ('queued','processing'):
                work.attempts+=1;work.next_attempt_at=now()+timedelta(seconds=min(300,2**work.attempts*5))
                if work.attempts>=self.MAX_ATTEMPTS:job.status='failed'
                append_event(self.db,work.brand_id,'BRAND_IMPORT_RETRY_SCHEDULED','CatalogImportJob',wid,
                             after={'attempt':work.attempts,'status':job.status})
                self.db.commit()
            else:self.db.rollback()
            return {'job_id':wid,'processed':0,'state':'retry_scheduled_or_superseded'}
