"""Negative tenant/RBAC tests; no production accounts or email delivery."""
from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy import event
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.models.user import User, UserRole, AuditLog
from backend.app.models.brand_team import BrandMembership, BrandInvitation
from backend.app.models.catalog import ProductSKU
from backend.app.core.security import create_access_token
from backend.tests.test_brand_portal_regressions import portal, row, upload


def invitee(factory, *, email='invitee@example.com', verified=True):
    with factory() as db:
        user = User(email=email, full_name='Invited user', hashed_password='not-a-login',
                    role=UserRole.CONSUMER, is_verified=verified)
        db.add(user); db.commit()
        return user.id, {'Authorization': 'Bearer ' + create_access_token({'sub': str(user.id)})}


def invitation(client, headers, email='invitee@example.com', role='manager'):
    r = client.post('/partner/team/invitations', headers=headers, json={'email': email, 'role': role})
    assert r.status_code == 201, r.text
    return r.json()


def test_membership_workflow_does_not_promote_global_role(portal):
    client, factory, headers, brands = portal
    uid, invited = invitee(factory)
    token = invitation(client, headers[0])
    result = client.post('/partner/team/accept', headers=invited, json={'token': token['token']})
    assert result.status_code == 200, result.text
    assert result.json()['brand_id'] == brands[0]
    assert client.get('/brand/profile', headers=invited).json()['membership_role'] == 'manager'
    me = client.get('/auth/me', headers=invited).json()
    assert me['role'] == 'consumer' and me['brand_id'] == brands[0]
    with factory() as db:
        assert db.get(User, uid).role == UserRole.CONSUMER
        member = db.query(BrandMembership).filter_by(user_id=uid).one()
        mid = member.id
        stored = db.query(BrandInvitation).one()
        assert stored.token_hash != token['token']
        assert all(token['token'] not in str(a.after_json) for a in db.query(AuditLog))
    assert client.post('/partner/team/accept', headers=invited, json={'token': token['token']}).status_code == 410
    assert client.patch(f'/partner/team/members/{mid}', headers=invited, json={'role':'owner'}).status_code == 403
    assert client.delete(f'/partner/team/members/{mid}', headers=headers[1]).status_code == 404
    assert client.delete(f'/partner/team/members/{mid}', headers=headers[0]).status_code == 200
    assert client.get('/brand/profile', headers=invited).status_code == 403


@pytest.mark.parametrize('role,can_catalog,can_inventory,can_placement', [
    ('owner',True,True,True), ('manager',True,True,True), ('catalog_editor',False,False,False),
    ('staff',False,False,False), ('analyst',False,False,False)])
def test_permission_matrix(portal, role, can_catalog, can_inventory, can_placement):
    client, factory, h, brands = portal
    uid, ih = invitee(factory)
    inv = invitation(client,h[0],role=role)
    assert client.post('/partner/team/accept',headers=ih,json={'token':inv['token']}).status_code==200
    upload(client,h[0],[row()])
    with factory() as db:
        sku=db.query(ProductSKU).one();sid,pid=sku.id,sku.product_id
    r=upload(client,ih,[row(title='New',sku_code='NEW')])
    assert r.status_code==(202 if can_catalog else 403),r.text
    r=client.put(f'/brand/skus/{sid}',headers=ih,params={'stock_level':7})
    assert r.status_code==(200 if can_inventory else 403),r.text
    r=client.post('/partner/placements',headers=ih,json={'product_id':pid,'daily_budget':5,'bid_amount_per_click':1})
    assert r.status_code==(201 if can_placement else 403),r.text
    if role!='owner':
        assert client.post('/partner/team/invitations',headers=ih,json={'email':'other@example.com','role':'owner'}).status_code==403


@pytest.mark.parametrize('mode', ['expired','revoked','wrong_email','unverified'])
def test_invitation_rejection(portal, mode):
    client,factory,h,_=portal
    _,ih=invitee(factory,email='wrong@example.com' if mode=='wrong_email' else 'invitee@example.com',verified=mode!='unverified')
    inv=invitation(client,h[0])
    if mode=='expired':
        with factory() as db:
            db.get(BrandInvitation,inv['id']).expires_at=datetime.now(timezone.utc)-timedelta(seconds=1);db.commit()
    if mode=='revoked':
        assert client.delete(f"/partner/team/invitations/{inv['id']}",headers=h[0]).status_code==200
    r=client.post('/partner/team/accept',headers=ih,json={'token':inv['token']})
    assert r.status_code==(410 if mode in ('expired','revoked') else 403)


def test_tenant_and_last_owner_protection(portal):
    client,factory,h,b=portal
    members=client.get('/partner/team/members',headers=h[0]).json()['items'];mid=members[0]['id']
    assert client.delete(f'/partner/team/members/{mid}',headers=h[0]).status_code==409
    assert client.patch(f'/partner/team/members/{mid}',headers=h[0],json={'role':'staff'}).status_code==409
    assert client.patch(f'/partner/team/members/{mid}',headers=h[1],json={'role':'owner'}).status_code==404
    assert client.post('/partner/team/invitations',headers=h[0],json={'email':'invitee@example.com','role':'manager','brand_id':b[1]}).status_code==422
    inv=invitation(client,h[0])
    assert client.post('/partner/team/invitations',headers=h[0],json={'email':'invitee@example.com','role':'manager'}).status_code==409
    assert client.delete(f"/partner/team/invitations/{inv['id']}",headers=h[1]).status_code==404
    assert client.get('/brand/profile',headers=h[3]).status_code==403  # unassigned admin cannot impersonate tenant


def test_audit_failure_rolls_back_inventory(portal):
    client,factory,h,_=portal
    upload(client,h[0],[row()])
    with factory() as db:sid=db.query(ProductSKU).one().id
    def fail(mapper,connection,target):
        if target.action=='BRAND_INVENTORY_UPDATED':raise RuntimeError('injected audit storage failure')
    event.listen(AuditLog,'before_insert',fail)
    try:
        response=TestClient(app,raise_server_exceptions=False).put(f'/brand/skus/{sid}',headers=h[0],params={'stock_level':99})
        assert response.status_code==500
    finally:event.remove(AuditLog,'before_insert',fail)
    with factory() as db:assert db.get(ProductSKU,sid).stock_level==10


def test_partner_audit_is_scoped_paginated_and_correlated(portal):
    client,factory,h,b=portal
    upload(client,h[0],[row()]);upload(client,h[1],[row(sku_code='FOREIGN')])
    with factory() as db:sid=db.query(ProductSKU).filter_by(sku_code='COAT-M-NAVY').one().id
    assert client.put(f'/brand/skus/{sid}',headers=h[0],params={'stock_level':9}).status_code==200
    page=client.get('/partner/audit?limit=1',headers=h[0]).json()
    assert len(page['items'])==1 and page['next_cursor']
    nxt=client.get('/partner/audit',params={'after':page['next_cursor'],'limit':100},headers=h[0]).json()
    assert all(a['id']!=page['items'][0]['id'] for a in nxt['items'])
    with factory() as db:
        events=db.query(AuditLog).filter(AuditLog.brand_id==b[0]).all()
        assert events and all(a.request_id for a in events)
        assert not set(a['id'] for a in page['items']+nxt['items']) & set(a.id for a in db.query(AuditLog).filter(AuditLog.brand_id==b[1]))
