"""Placement invariants shared by create, patch and tracking (legacy DB stores UTC-naive)."""
from datetime import datetime, timezone
from backend.app.core.money import validate_money

PLACEMENT_TYPES = ('stylist_featured', 'trending_hero', 'fit_recom_top')


def utc_naive(value):
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if not isinstance(value, datetime):
        raise ValueError('Date must be an ISO-8601 datetime')
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


def validate_placement(data, spent=0):
    bid = validate_money(data['bid_amount_per_click'], 'bid_amount_per_click', allow_zero=False, required=True, exact_scale=True)
    budget = validate_money(data['daily_budget'], 'daily_budget', allow_zero=False, required=True, exact_scale=True)
    if bid > 100 or budget > 10000 or bid > budget:
        raise ValueError('Bid must be <= 100 and <= budget; budget must be <= 10000')
    if budget < spent:
        raise ValueError('Budget cannot be reduced below recorded spend')
    if data['placement_type'] not in PLACEMENT_TYPES:
        raise ValueError('Unsupported placement type')
    start, end = utc_naive(data.get('start_date')), utc_naive(data.get('end_date'))
    if start and end and start >= end:
        raise ValueError('Start date must be before end date')
    return dict(data, bid_amount_per_click=bid, daily_budget=budget, start_date=start, end_date=end)
