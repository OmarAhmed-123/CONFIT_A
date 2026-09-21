"""Idempotent partner-reported counters, NOT verified ad delivery or invoices.

The legacy endpoint only authenticates an advertiser, not a rendered consumer
impression. Keeping that provenance explicit is essential: this journal must
not be exported as billable events without a trusted serving/acceptance path.
"""
import hashlib
import json
import re
from datetime import datetime, timezone
from fastapi import HTTPException
from backend.app.models.brand_analytics import SponsoredPlacement, PlacementCounterEvent
from backend.app.models.user import BrandProfile
from backend.app.services.partner_audit import append_event
from backend.app.core.money import money_add, money_sub


def record(db, brand_id, placement_id, kind, key):
    p=db.query(SponsoredPlacement).filter_by(id=placement_id,brand_id=brand_id).populate_existing().with_for_update().first()
    if not p:raise HTTPException(404,'Placement unavailable')
    if not key or not re.fullmatch(r'[A-Za-z0-9_-]{16,100}',key):
        raise HTTPException(422,'A 16–100 character Idempotency-Key is required')
    fingerprint=hashlib.sha256(key.encode()).hexdigest()
    old=db.query(PlacementCounterEvent).filter_by(placement_id=p.id,kind=kind,key_hash=fingerprint).first()
    if old:return json.loads(old.response_json)
    if db.get(BrandProfile,brand_id).is_test:
        raise HTTPException(409,'Production test tenants cannot record advertising counters')
    now=datetime.now(timezone.utc);day=now.date()
    if p.spend_day is None:
        # Preserve the unknown legacy opening counter on the cut-over day.
        p.spend_day=day
    elif p.spend_day!=day:
        p.spent_today=0;p.spend_day=day
        if p.status=='budget_exhausted':p.status='active'
    if p.status!='active':raise HTTPException(400,'Placement is not active')
    naive=now.replace(tzinfo=None)
    if (p.start_date and naive<p.start_date) or (p.end_date and naive>p.end_date):
        raise HTTPException(400,'Placement is outside its scheduled dates')
    amount=p.bid_amount_per_click if kind=='click' else 0
    if p.spent_today+amount>p.daily_budget or p.spent_today>=p.daily_budget:
        raise HTTPException(400,'Daily budget would be exceeded')
    if kind=='click':
        p.clicks+=1;p.spent_today=money_add(p.spent_today,amount)
        if p.spent_today>=p.daily_budget:p.status='budget_exhausted'
    else:p.impressions+=1
    result={'status':'tracked','provenance':'partner_reported','billable':False,'clicks':p.clicks,
        'impressions':p.impressions,'spent_today':float(p.spent_today),'remaining_budget':float(money_sub(p.daily_budget,p.spent_today)),
        'day':str(day)}
    entry=PlacementCounterEvent(placement_id=p.id,brand_id=brand_id,kind=kind,key_hash=fingerprint,
        amount=amount,event_day=day,response_json=json.dumps(result))
    db.add(entry);db.flush()
    append_event(db,brand_id,'BRAND_PLACEMENT_COUNTER_RECORDED','PlacementCounterEvent',entry.id,
        after={'placement_id':p.id,'kind':kind,'amount':str(amount),'day':str(day),'billable':False})
    db.commit()
    return result
