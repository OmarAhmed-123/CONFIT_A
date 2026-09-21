from backend.app.core.config import settings


def test_guided_stylist_accepts_structured_palette_and_reports_authority(client):
    res = client.post('/api/v1/stylist/chat', json={
        'prompt': 'I need a work outfit under 650',
        'occasion': 'Work',
        'budget_limit': 650,
        'recommendation_constraints': {'palette': 'navy', 'preferred_fit': 'regular'},
    })
    assert res.status_code == 200, res.text
    intent = res.json()['intent_detected']
    meta = intent['recommendation_constraints']
    assert meta['palette'] == 'navy'
    assert meta['palette_authority'] == 'catalog_color_family_and_sku_color'
    assert meta['ranking'] == 'deterministic_constraints_then_existing_styling_rules'
    assert res.json()['recommendations']


def test_guided_stylist_rejects_unknown_and_conflicting_palette(client):
    bad = client.post('/api/v1/stylist/chat', json={
        'prompt': 'work outfit',
        'recommendation_constraints': {'palette': 'ultraviolet laser'},
    })
    assert bad.status_code == 422
    conflict = client.post('/api/v1/stylist/chat', json={
        'prompt': 'work outfit',
        'recommendation_constraints': {'palette': 'navy', 'avoid_palette': 'navy'},
    })
    assert conflict.status_code == 422


def test_guided_fit_uses_size_profile_not_fake_confidence(client):
    res = client.post('/api/v1/stylist/chat', json={
        'prompt': 'business outfit with blazer',
        'recommendation_constraints': {'size_tops': 'M', 'size_bottoms': 'M', 'preferred_fit': 'slim'},
    })
    assert res.status_code == 200, res.text
    meta = res.json()['intent_detected']['recommendation_constraints']
    assert meta['fit_authority'] == 'sku_size_availability'
    assert 'confidence' not in meta


def test_vton_capability_registry_distinguishes_supported_and_unsupported(client, monkeypatch):
    """Category -> slot mapping is the backend's decision, never the client's.

    The worker verdict is stubbed to "ready" because engine availability is now
    a MEASURED property (live probe), not a consequence of VTON_WORKER_URL being
    set. Asserting engine_state == 'available' from configuration alone was the
    exact behaviour that let production advertise try-on while the GPU
    workspace was disabled and every job failed (2026-09-21).
    """
    from backend.app.services import vton_worker_observability as vwo

    monkeypatch.setattr(settings, 'VTON_WORKER_URL', 'https://worker.example/process', raising=False)
    monkeypatch.setattr(settings, 'VTON_WORKER_ADMIN_TOKEN', 'token', raising=False)
    monkeypatch.setattr(
        vwo, 'probe_worker_state',
        lambda force=False: {'verdict': 'ready', 'ok': True, 'status_code': 200, 'reason': None},
    )
    vwo.reset_worker_observability()
    try:
        res = client.get('/api/v1/try-on/capabilities?product_ids=1&product_ids=3&product_ids=999999')
        assert res.status_code == 200, res.text
        data = res.json()
        assert data['engine_state'] == 'available'
        assert data['engine']['verdict'] == 'ready'
        assert data['engine']['production_ready'] is True
        states = {p['product_id']: p['state'] for p in data['products']}
        assert states[1] == 'supported'
        assert states[3] in {'supported', 'unsupported', 'unknown'}
        assert states[999999] == 'unknown'
    finally:
        vwo.reset_worker_observability()


def test_vton_capability_reports_engine_offline_instead_of_supported(client, monkeypatch):
    """A supported CATEGORY on a dead ENGINE must not read 'supported'."""
    from backend.app.services import vton_worker_observability as vwo

    monkeypatch.setattr(settings, 'VTON_WORKER_URL', 'https://worker.example/process', raising=False)
    monkeypatch.setattr(settings, 'VTON_WORKER_ADMIN_TOKEN', 'token', raising=False)
    monkeypatch.setattr(
        vwo, 'probe_worker_state',
        lambda force=False: {
            'verdict': 'unavailable', 'ok': False, 'status_code': 404,
            'reason': 'HTTP 404: modal-http: workspace ac-x is disabled',
            'error_code': 'VTON_ENGINE_UNAVAILABLE', 'retryable': False,
        },
    )
    vwo.reset_worker_observability()
    try:
        body = client.get('/api/v1/try-on/capabilities?product_ids=1').json()
        assert body['engine_state'] == 'temporarily_unavailable'
        assert body['products'][0]['state'] == 'temporarily_unavailable'
        assert body['products'][0]['reason_code'] == 'VTON_ENGINE_UNAVAILABLE'
        assert body['user_message']
    finally:
        vwo.reset_worker_observability()


def test_vton_capability_misconfigured_is_not_supported(client, monkeypatch):
    monkeypatch.setattr(settings, 'VTON_WORKER_URL', '', raising=False)
    res = client.get('/api/v1/try-on/capabilities?product_ids=1')
    assert res.status_code == 200
    body = res.json()
    assert body['engine_state'] == 'misconfigured'
    assert body['products'][0]['state'] == 'misconfigured'


def test_partner_request_demo_persists_and_duplicates(client):
    payload = {
        'company_name': 'Integrity Brand',
        'contact_name': 'Amina Partner',
        'work_email': 'amina.partner@example.com',
        'website': 'https://example.com',
        'monthly_order_volume': '500_5000',
        'message': 'We want to evaluate fit and try-on readiness.',
    }
    first = client.post('/api/v1/brand/request-demo', json=payload)
    assert first.status_code == 201, first.text
    assert first.json()['status'] == 'received'
    second = client.post('/api/v1/brand/request-demo', json=payload)
    assert second.status_code == 201, second.text
    assert second.json()['duplicate'] is True


def test_partner_request_demo_validates_email(client):
    res = client.post('/api/v1/brand/request-demo', json={
        'company_name': 'Bad Email Co',
        'contact_name': 'Tester',
        'work_email': 'not-an-email',
    })
    assert res.status_code == 422
