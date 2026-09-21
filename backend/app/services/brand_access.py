"""One-tenant membership policy and invitation use cases.

Lock order is BrandProfile -> membership/invitation. Every membership mutation
locks the same parent, including first invitations and last-owner decisions.
"""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException, Depends, Request
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from backend.app.core.database import get_db
from backend.app.core.dependencies import get_current_user
from backend.app.core.exceptions import AuthorizationError
from backend.app.models.user import User, BrandProfile
from backend.app.models.brand_team import BrandMembership, BrandInvitation
from backend.app.services.partner_audit import append_event

READ = {'read'}
PERMISSIONS = {
    'owner': READ | {'catalog.import', 'catalog.publish', 'pricing.write', 'catalog.write', 'inventory.write', 'stores.write', 'placements.write', 'team.manage'},
    'manager': READ | {'catalog.import', 'catalog.publish', 'pricing.write', 'catalog.write', 'inventory.write', 'stores.write', 'placements.write'},
    'staff': READ,  # least-privilege default, not an implicit write role
    'analyst': READ,
    'catalog_editor': READ | {'catalog.write'},
}


def now():
    return datetime.now(timezone.utc)


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def resolve(db, user, permission='read', *, lock=False):
    member = db.query(BrandMembership).filter_by(user_id=user.id).first()
    if not member:
        raise AuthorizationError('No active brand membership')
    if lock:
        db.query(BrandProfile).filter_by(id=member.brand_id).with_for_update().one()
        member = db.query(BrandMembership).filter_by(user_id=user.id).populate_existing().first()
        if not member:
            raise AuthorizationError('Brand membership was revoked')
    if permission not in PERMISSIONS[member.role]:
        raise AuthorizationError('Brand membership does not permit this operation')
    db.info['partner_actor'] = user.id
    return member


def require_partner(permission='read'):
    def dependency(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
        resolve(db, user, permission, lock=permission != 'read')
        db.info['partner_request_id'] = getattr(request.state, 'request_id', None)
        return user
    return dependency


class BrandTeamService:
    def __init__(self, db, user):
        self.db, self.user = db, user

    def _owner(self):
        return resolve(self.db, self.user, 'team.manage', lock=True)

    def invite(self, email, role):
        member = self._owner()
        email = email.strip().lower()
        existing_user = self.db.query(User).filter(User.email == email).first()
        if existing_user and self.db.query(BrandMembership).filter_by(user_id=existing_user.id).first():
            raise HTTPException(409, 'Account already belongs to a brand')
        existing = self.db.query(BrandInvitation).filter_by(brand_id=member.brand_id, email=email, status='pending').all()
        for invite in existing:
            if utc(invite.expires_at) > now():
                raise HTTPException(409, 'An invitation is already pending')
            invite.status = 'expired'
        token = secrets.token_urlsafe(32)
        invitation = BrandInvitation(brand_id=member.brand_id, email=email, role=role,
            token_hash=hashlib.sha256(token.encode()).hexdigest(), invited_by=self.user.id,
            expires_at=now() + timedelta(hours=72))
        self.db.add(invitation)
        self.db.flush()
        append_event(self.db, member.brand_id, 'BRAND_INVITATION_CREATED', 'BrandInvitation', invitation.id,
                     after={'role': role, 'expires_at': invitation.expires_at})
        self.db.commit()
        # Returned once over authenticated TLS. Never in audit/history/URLs.
        return {'id': invitation.id, 'token': token, 'expires_at': invitation.expires_at, 'delivery': 'manual_secure_share'}

    def accept(self, token):
        fingerprint = hashlib.sha256(token.encode()).hexdigest()
        invitation = self.db.query(BrandInvitation).filter_by(token_hash=fingerprint).first()
        if not invitation:
            raise HTTPException(404, 'Invitation unavailable')
        self.db.query(BrandProfile).filter_by(id=invitation.brand_id).with_for_update().one()
        invitation = self.db.query(BrandInvitation).filter_by(id=invitation.id).populate_existing().one()
        if invitation.status != 'pending' or utc(invitation.expires_at) <= now():
            raise HTTPException(410, 'Invitation expired or no longer pending')
        if self.user.email.lower() != invitation.email or not self.user.is_verified:
            raise AuthorizationError('Sign in with the verified invited account')
        if self.db.query(BrandMembership).filter_by(user_id=self.user.id).first():
            raise HTTPException(409, 'Account already belongs to a brand')
        member = BrandMembership(brand_id=invitation.brand_id, user_id=self.user.id, role=invitation.role)
        self.db.add(member)
        invitation.status = 'accepted'
        self.db.info['partner_actor'] = self.user.id
        try:
            self.db.flush()
            append_event(self.db, member.brand_id, 'BRAND_INVITATION_ACCEPTED', 'BrandMembership', member.id, after={'role': member.role})
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise HTTPException(409, 'Account already belongs to a brand')
        return {'brand_id': member.brand_id, 'role': member.role}

    def revoke(self, invitation_id):
        actor = self._owner()
        invitation = self.db.query(BrandInvitation).filter_by(id=invitation_id, brand_id=actor.brand_id).first()
        if not invitation:
            raise HTTPException(404, 'Invitation unavailable')
        if invitation.status != 'pending':
            raise HTTPException(409, 'Invitation is not pending')
        invitation.status = 'revoked'
        append_event(self.db, actor.brand_id, 'BRAND_INVITATION_REVOKED', 'BrandInvitation', invitation.id)
        self.db.commit()
        return {'status': 'revoked'}

    def change_member(self, member_id, role=None, *, remove=False):
        actor = self._owner()
        member = self.db.query(BrandMembership).filter_by(id=member_id, brand_id=actor.brand_id).first()
        if not member:
            raise HTTPException(404, 'Member unavailable')
        before = {'role': member.role, 'user_id': member.user_id}
        if member.role == 'owner' and (remove or role != 'owner'):
            other = self.db.query(BrandMembership).join(User, User.id == BrandMembership.user_id).filter(User.is_active.is_(True),
                BrandMembership.brand_id == actor.brand_id, BrandMembership.role == 'owner',
                BrandMembership.id != member.id).order_by(BrandMembership.id).first()
            if not other:
                raise HTTPException(409, 'The last owner cannot be removed or demoted')
            # Preserve legacy integrations that still read BrandProfile.user_id.
            brand = self.db.query(BrandProfile).filter_by(id=actor.brand_id).one()
            if brand.user_id == member.user_id:
                brand.user_id = other.user_id
        if remove:
            self.db.delete(member)
        else:
            member.role = role
        append_event(self.db, actor.brand_id, 'BRAND_MEMBER_REMOVED' if remove else 'BRAND_MEMBER_ROLE_CHANGED',
                     'BrandMembership', member_id, before=before, after=None if remove else {'role': role})
        self.db.commit()
        return {'status': 'removed' if remove else 'updated'}
