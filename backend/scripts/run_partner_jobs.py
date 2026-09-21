"""Durable partner import / asset cleanup runner. No web server or seed data.

Run from the repository root with DATABASE_URL and storage configuration supplied
by a secret manager. All emitted output is counters/state, never row payloads.
"""
import argparse
import json
import os
import secrets
import sys


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--max-batches',type=int,default=25)
    parser.add_argument('--purge-assets',action='store_true')
    args=parser.parse_args()
    if not 1<=args.max_batches<=100:parser.error('max-batches must be between 1 and 100')
    if not os.environ.get('DATABASE_URL'):parser.error('DATABASE_URL is required; no SQLite fallback')
    # This is a non-serving process. It neither issues JWTs nor reads encrypted
    # body data, so it must NOT receive the production signing/decryption keys.
    # Per-process ephemeral values satisfy shared Settings bootstrap only.
    os.environ['ENVIRONMENT']='production'
    for key in ('SECRET_KEY','JWT_REFRESH_SECRET','ENCRYPTION_KEY_FOR_BODY_DATA'):
        os.environ.setdefault(key,secrets.token_urlsafe(48))
    from backend.app.core.database import SessionLocal,engine
    from backend.app.core.schema_gate import evaluate,acceptable
    if not acceptable(evaluate(engine),'production'):
        print(json.dumps({'state':'schema_incompatible'}));return 2
    from backend.app.services.partner_import_queue import PartnerImportQueue
    from backend.app.models.brand_operations import ProductAsset
    from backend.app.services.partner_assets import purge
    summary={'batches':0,'rows':0,'retry_attempts':0,'assets_purged':0}
    for _ in range(args.max_batches):
        with SessionLocal() as db:
            result=PartnerImportQueue(db).run_batch()
            if result.get('state')=='idle_or_claimed':break
            summary['batches']+=1;summary['rows']+=result.get('processed',0)
            summary['retry_attempts']+=int(result.get('state')=='retry_scheduled_or_superseded')
    if args.purge_assets:
        with SessionLocal() as db:
            ids=[r[0] for r in db.query(ProductAsset.id).filter(ProductAsset.state.in_(['upload_pending','delete_pending'])).order_by(ProductAsset.created_at).limit(20).all()]
        for asset_id in ids:
            with SessionLocal() as db:summary['assets_purged']+=int(purge(db,asset_id))
    print(json.dumps(summary))
    return 1 if summary['retry_attempts'] else 0


if __name__=='__main__':
    try:sys.exit(main())
    except Exception as exc:
        print(json.dumps({'state':'worker_error','error_type':type(exc).__name__}),file=sys.stderr)
        sys.exit(2)
