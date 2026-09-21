"""Membership commands and keyset-paginated tenant audit read model."""
import json
from typing import Literal
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy.orm import Session
from backend.app.core.database import get_db
from backend.app.core.dependencies import get_current_user
from backend.app.models.user import User, AuditLog
from backend.app.models.brand_team import BrandMembership, BrandInvitation
from backend.app.services.brand_access import BrandTeamService, require_partner, resolve, utc, now

router = APIRouter(prefix='/partner', tags=['Brand team'])
Role = Literal['owner', 'manager', 'staff', 'analyst', 'catalog_editor']


class InviteInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    email: EmailStr
    role: Role


class RoleInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    role: Role


class AcceptInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    token: str = Field(min_length=32, max_length=128)


@router.post('/team/invitations', status_code=201)
def invite(payload: InviteInput, user=Depends(require_partner('team.manage')), db: Session = Depends(get_db)):
    return BrandTeamService(db, user).invite(str(payload.email), payload.role)


@router.post('/team/accept')
def accept(payload: AcceptInput, user=Depends(get_current_user), db: Session = Depends(get_db)):
    return BrandTeamService(db, user).accept(payload.token)


@router.delete('/team/invitations/{invitation_id}')
def revoke(invitation_id: int, user=Depends(require_partner('team.manage')), db: Session = Depends(get_db)):
    return BrandTeamService(db, user).revoke(invitation_id)


@router.patch('/team/members/{member_id}')
def change_role(member_id: int, payload: RoleInput, user=Depends(require_partner('team.manage')), db: Session = Depends(get_db)):
    return BrandTeamService(db, user).change_member(member_id, payload.role)


@router.delete('/team/members/{member_id}')
def remove(member_id: int, user=Depends(require_partner('team.manage')), db: Session = Depends(get_db)):
    return BrandTeamService(db, user).change_member(member_id, remove=True)


def _page(rows, limit, serialise):
    more = len(rows) > limit
    items = rows[:limit]
    return {'items': [serialise(row) for row in items], 'next_cursor': items[-1].id if more else None}


@router.get('/team/members')
def members(after: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
            user=Depends(require_partner()), db: Session = Depends(get_db)):
    from sqlalchemy.orm import joinedload
    brand_id = resolve(db, user).brand_id
    rows = db.query(BrandMembership).options(joinedload(BrandMembership.user)).filter(
        BrandMembership.brand_id == brand_id, BrandMembership.id > after).order_by(BrandMembership.id).limit(limit + 1).all()
    return _page(rows, limit, lambda row: {'id': row.id, 'user_id': row.user_id, 'email': row.user.email, 'role': row.role})


@router.get('/team/invitations')
def invitations(after: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
                user=Depends(require_partner('team.manage')), db: Session = Depends(get_db)):
    brand_id = resolve(db, user).brand_id
    rows = db.query(BrandInvitation).filter(BrandInvitation.brand_id == brand_id,
        BrandInvitation.id > after).order_by(BrandInvitation.id).limit(limit + 1).all()
    return _page(rows, limit, lambda row: {'id': row.id, 'email': row.email, 'role': row.role,
        'status': 'expired' if row.status == 'pending' and utc(row.expires_at) <= now() else row.status,
        'expires_at': row.expires_at})


@router.get('/audit')
def audit(after: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
          user=Depends(require_partner()), db: Session = Depends(get_db)):
    brand_id = resolve(db, user).brand_id
    rows = db.query(AuditLog).filter(AuditLog.brand_id == brand_id, AuditLog.id > after).order_by(AuditLog.id).limit(limit + 1).all()
    return _page(rows, limit, lambda row: {'id': row.id, 'actor_id': row.user_id, 'action': row.action,
        'entity': row.resource_type, 'entity_id': row.resource_id, 'request_id': row.request_id,
        'timestamp': utc(row.timestamp), 'before': json.loads(row.before_json) if row.before_json else None,
        'after': json.loads(row.after_json) if row.after_json else None})
