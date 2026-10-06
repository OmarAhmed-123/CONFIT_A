"""Spec 15 — email template system: contract tests from every side.

What is pinned here:
  * registry completeness: ten message types, correct consent categories
  * every template × EN/AR renders all four parts; HTML parses; no <script>
  * direction: AR renders dir="rtl" lang="ar"; codes/prices/order numbers
    stay LTR inside the Arabic page (<bdi dir="ltr">)
  * exactly ONE CTA per message; its URL appears in the plain-text version
    (text parity), as does the unsubscribe link when one exists
  * honesty: missing payload fields raise — no placeholders, no fake
    numbers; relative URLs raise; fit confidence outside 0–100 raises;
    the fit caveat is ALWAYS present (fit is never a guarantee)
  * consent: marketing/engagement require an unsubscribe URL and expose a
    List-Unsubscribe value; transactional mail explains why it was sent
  * no emoji anywhere in production email content
  * outbox: idempotent dispatch (one event_key = at most one accepted
    send), honest failure recording, retry-after-failure allowed,
    suppressed → 'unsubscribed' without rendering or sending, bounce hook
  * admin endpoints: anonymous → 401, consumer → 403, admin can list and
    preview (sample data only)
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.services.email_templates import (
    CATEGORY_ENGAGEMENT,
    CATEGORY_MARKETING,
    CATEGORY_TRANSACTIONAL,
    EmailTemplateError,
    SUPPORTED_LOCALES,
    TEMPLATES,
    render_email,
    sample_payload,
)

BASE = "https://confit-a.vercel.app"

# Realistic payloads (values are inputs the CALLER measured; the renderer
# must show them verbatim).
PAYLOADS: dict[str, dict] = {
    "order_confirmation": {
        "order_number": "CNF-2026-1042",
        "items": [
            {"name": "Linen shirt", "qty": 2, "price": "1,250.00"},
            {"name": "Silk scarf", "qty": 1, "price": "900.00"},
        ],
        "total": "3,400.00", "currency": "EGP",
        "order_url": f"{BASE}/order/CNF-2026-1042",
    },
    "payment_failed": {
        "order_number": "CNF-2026-1042",
        "reason": "Card declined by issuer (code 05).",
        "retry_url": f"{BASE}/checkout?order=CNF-2026-1042",
    },
    "shipping_update": {
        "order_number": "CNF-2026-1042", "carrier": "Aramex",
        "tracking_code": "ARX998877",
        "tracking_url": f"{BASE}/order/CNF-2026-1042",
    },
    "saved_look": {
        "look_name": "Evening in Zamalek", "look_url": f"{BASE}/my-looks/77",
        "unsubscribe_url": f"{BASE}/profile",
    },
    "outfit_ready": {
        "outfit_name": "Friday brunch", "outfit_url": f"{BASE}/builder/31",
        "unsubscribe_url": f"{BASE}/profile",
    },
    "fit_result": {
        "product_name": "Tailored blazer", "size_label": "M",
        "confidence_pct": 82, "result_url": f"{BASE}/tryon/9",
        "unsubscribe_url": f"{BASE}/profile",
    },
    "price_drop": {
        "product_name": "Silk scarf", "old_price": "900.00",
        "new_price": "720.00", "currency": "EGP",
        "product_url": f"{BASE}/product/9", "unsubscribe_url": f"{BASE}/profile",
    },
    "partner_approval": {
        "partner_name": "Nile Thread Co.", "portal_url": f"{BASE}/b2b",
    },
    "admin_alert": {
        "alert_title": "Payment failure spike",
        "metric_name": "payment_failed_count", "metric_value": "17",
        "window_label": "last 24h",
        "dashboard_url": f"{BASE}/admin/analytics?days=30",
    },
    "newsletter": {
        "edition_title": "The linen edit",
        "intro_text": "Three looks built around one fabric.",
        "read_url": f"{BASE}/discover", "unsubscribe_url": f"{BASE}/profile",
    },
}

EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U00002700-\U000027BF\U0001F000-\U0001F02F\U0001F900-\U0001F9FF]"
)


class _Balanced(HTMLParser):
    """Minimal HTML lint: the document must parse and never contain script."""
    def __init__(self) -> None:
        super().__init__()
        self.scripts = 0

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self.scripts += 1


def _lint(html: str) -> _Balanced:
    parser = _Balanced()
    parser.feed(html)  # raises on grossly malformed markup
    return parser


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def test_registry_has_the_ten_spec_templates_with_correct_categories():
    assert set(TEMPLATES) == set(PAYLOADS)
    assert len(TEMPLATES) == 10
    assert TEMPLATES["order_confirmation"].category == CATEGORY_TRANSACTIONAL
    assert TEMPLATES["payment_failed"].category == CATEGORY_TRANSACTIONAL
    assert TEMPLATES["shipping_update"].category == CATEGORY_TRANSACTIONAL
    assert TEMPLATES["partner_approval"].category == CATEGORY_TRANSACTIONAL
    assert TEMPLATES["admin_alert"].category == CATEGORY_TRANSACTIONAL
    assert TEMPLATES["saved_look"].category == CATEGORY_ENGAGEMENT
    assert TEMPLATES["outfit_ready"].category == CATEGORY_ENGAGEMENT
    assert TEMPLATES["fit_result"].category == CATEGORY_ENGAGEMENT
    assert TEMPLATES["price_drop"].category == CATEGORY_MARKETING
    assert TEMPLATES["newsletter"].category == CATEGORY_MARKETING


# ---------------------------------------------------------------------------
# Every template × every locale
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("template", sorted(TEMPLATES))
@pytest.mark.parametrize("locale", SUPPORTED_LOCALES)
def test_renders_all_four_parts_with_parity(template: str, locale: str):
    content = render_email(template, locale, PAYLOADS[template])

    # All four parts exist and are non-trivial (§6.2).
    assert content.subject.strip()
    assert content.preheader.strip()
    assert len(content.html) > 500
    assert len(content.text) > 50

    # HTML lints: parses, no script, inline-styled table layout.
    parser = _lint(content.html)
    assert parser.scripts == 0
    assert 'role="presentation"' in content.html

    # Exactly ONE <style> block — progressive enhancement only. Layout and
    # colour must survive Gmail/Outlook stripping it (proved separately in
    # test_meaning_survives_style_stripping).
    assert content.html.count("<style") == 1

    # ALL animation lives inside prefers-reduced-motion:no-preference —
    # no keyframes/animation property may appear before that guard.
    style_block = content.html.split("<style>")[1].split("</style>")[0]
    guard = "@media (prefers-reduced-motion: no-preference)"
    assert guard in style_block
    before_guard = style_block.split(guard)[0]
    assert "@keyframes" not in before_guard
    assert "animation" not in before_guard
    # Dark-mode override block exists alongside the color-scheme meta.
    assert "@media (prefers-color-scheme: dark)" in style_block

    # Brand header: hosted logo image ABOVE the text wordmark, absolute
    # URL, meaningful alt — and the wordmark text survives image blocking.
    logo_at = content.html.index("/email/confit-logo.png")
    assert content.html[:logo_at].rsplit("src=", 1)[-1].lstrip('"').startswith("http")
    img_tag = content.html[content.html.rindex("<img", 0, logo_at):]
    img_tag = img_tag[: img_tag.index(">") + 1]
    assert 'alt="CONFIT"' in img_tag and 'width="56"' in img_tag
    assert logo_at < content.html.index(">CONFIT<", logo_at)  # image above word

    # Preheader is present and hidden.
    assert content.preheader in content.html
    assert "display:none" in content.html

    # Direction comes from the locale — never manual mirroring (§7).
    if locale == "ar":
        assert 'dir="rtl"' in content.html
        assert 'lang="ar"' in content.html
    else:
        assert 'dir="ltr"' in content.html

    # Exactly ONE CTA (§9): the bulletproof button pattern appears once.
    assert content.html.count("display:inline-block;padding:14px 30px") == 1

    # The text version is no second-class citizen: it carries the CTA link.
    urls_in_text = re.findall(r"https?://\S+", content.text)
    assert any(u.startswith(BASE) for u in urls_in_text)

    # Dark-mode hint present (§9).
    assert 'name="color-scheme" content="light dark"' in content.html

    # No emoji in production email content (§8).
    assert not EMOJI_RE.search(content.html)
    assert not EMOJI_RE.search(content.text)
    assert not EMOJI_RE.search(content.subject)


# ---------------------------------------------------------------------------
# Design system contract (post-spec-15 upgrade)
# ---------------------------------------------------------------------------

_STYLE_RE = re.compile(r"<style>.*?</style>", re.S)


@pytest.mark.parametrize("template", sorted(TEMPLATES))
@pytest.mark.parametrize("locale", SUPPORTED_LOCALES)
def test_meaning_survives_style_stripping(template: str, locale: str):
    """Gmail/Outlook-Windows discard <style>. Removing the entire block must
    leave every fact, the CTA, the unsubscribe link and the logo intact —
    the animation and dark mode are enhancements, never the meaning."""
    content = render_email(template, locale, PAYLOADS[template])
    stripped = _STYLE_RE.sub("", content.html)
    assert "<style" not in stripped
    # One CTA still present and clickable.
    assert stripped.count("display:inline-block;padding:14px 30px") == 1
    # Logo + wordmark + preheader still there.
    assert "/email/confit-logo.png" in stripped
    assert ">CONFIT<" in stripped
    assert content.preheader in stripped
    # Every absolute URL that was in the text version survives in HTML.
    for url in re.findall(r"https?://\S+", content.text):
        assert url.rstrip(".,)") in stripped
    # Layout/colour remained inline: body copy still carries inline ink colour.
    assert "color:#1B1F3B" in stripped


def test_palette_is_documented_with_measured_contrast():
    """The colour tokens actually used in the shell must be the documented,
    contrast-measured ones — no ad-hoc colours for text roles."""
    from backend.app.services.email_templates import CATEGORY_ACCENTS, EMAIL_COLORS

    content = render_email("order_confirmation", "en", PAYLOADS["order_confirmation"])
    for token in ("ink", "footer_text", "gold_wordmark", "hairline", "footer_bg"):
        assert EMAIL_COLORS[token] in content.html
    # Category accent is applied per registry category.
    assert CATEGORY_ACCENTS[TEMPLATES["order_confirmation"].category] in content.html
    assert CATEGORY_ACCENTS[TEMPLATES["newsletter"].category] in render_email(
        "newsletter", "en", PAYLOADS["newsletter"]
    ).html
    # Retired low-contrast greys must not reappear as text colours.
    assert "color:#7A7E92" not in content.html
    assert "color:#9A9EB2" not in content.html


def test_auth_shell_shares_logo_and_guarded_animation():
    """Password-reset/verification mail (separate shell) carries the same
    brand header: hosted logo above the wordmark, animation guarded."""
    from backend.app.services.email_service import render_password_reset_email

    _, html, text = render_password_reset_email(
        "Omar", "https://confit-a.vercel.app/reset?token=abc"
    )
    logo_at = html.index("/email/confit-logo.png")
    assert logo_at < html.index(">CONFIT<", logo_at)
    assert html.count("<style") == 1
    style_block = html.split("<style>")[1].split("</style>")[0]
    guard = "@media (prefers-reduced-motion: no-preference)"
    assert guard in style_block
    assert "@keyframes" not in style_block.split(guard)[0]
    assert "@media (prefers-color-scheme: dark)" in style_block
    assert "https://confit-a.vercel.app/reset?token=abc" in text


@pytest.mark.parametrize("template", sorted(TEMPLATES))
def test_consent_contract_per_category(template: str):
    spec = TEMPLATES[template]
    content = render_email(template, "en", PAYLOADS[template])
    if spec.category == CATEGORY_TRANSACTIONAL:
        # Service mail: explains why it was sent; no unsubscribe claim.
        assert content.list_unsubscribe is None
        assert "service message" in content.html
    else:
        # Engagement/marketing: unsubscribe is rendered AND exposed for the
        # List-Unsubscribe header, and appears in the text version too.
        assert content.list_unsubscribe == f'<{PAYLOADS[template]["unsubscribe_url"]}>'
        assert PAYLOADS[template]["unsubscribe_url"] in content.html
        assert PAYLOADS[template]["unsubscribe_url"] in content.text


def test_marketing_without_unsubscribe_is_refused():
    payload = dict(PAYLOADS["price_drop"])
    del payload["unsubscribe_url"]
    with pytest.raises(EmailTemplateError, match="unsubscribe_url"):
        render_email("price_drop", "en", payload)


# ---------------------------------------------------------------------------
# RTL + LTR codes
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("template,code", [
    ("order_confirmation", "CNF-2026-1042"),
    ("shipping_update", "ARX998877"),
    ("price_drop", "720.00 EGP"),
    ("admin_alert", "17"),
])
def test_codes_and_prices_stay_ltr_inside_arabic(template: str, code: str):
    html = render_email(template, "ar", PAYLOADS[template]).html
    assert 'dir="rtl"' in html
    assert re.search(r'<bdi dir="ltr"[^>]*>' + re.escape(code), html), (
        f"{code!r} must be wrapped in an LTR bdi inside the Arabic email"
    )


def test_arabic_copy_is_arabic_not_transliterated():
    html = render_email("order_confirmation", "ar", PAYLOADS["order_confirmation"]).html
    assert "تم استلام طلبك" in html
    assert "الإجمالي" in html


# ---------------------------------------------------------------------------
# Honesty: missing data fails loudly, URLs must be absolute
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("template", sorted(TEMPLATES))
def test_missing_required_field_raises_never_fakes(template: str):
    payload = dict(PAYLOADS[template])
    victim = next(k for k in payload if k != "unsubscribe_url")
    del payload[victim]
    with pytest.raises(EmailTemplateError, match=victim):
        render_email(template, "en", payload)


def test_relative_url_is_refused():
    payload = dict(PAYLOADS["shipping_update"])
    payload["tracking_url"] = "/order/CNF-2026-1042"
    with pytest.raises(EmailTemplateError, match="absolute"):
        render_email("shipping_update", "en", payload)


def test_unknown_template_and_locale_raise():
    with pytest.raises(EmailTemplateError, match="Unknown template"):
        render_email("spam_blast", "en", {})
    with pytest.raises(EmailTemplateError, match="Unsupported locale"):
        render_email("newsletter", "fr", PAYLOADS["newsletter"])


def test_payload_html_is_escaped_not_executed():
    payload = dict(PAYLOADS["saved_look"])
    payload["look_name"] = '<script>alert(1)</script>'
    content = render_email("saved_look", "en", payload)
    assert "<script>" not in content.html
    assert "&lt;script&gt;" in content.html


# ---------------------------------------------------------------------------
# Fit result: caveat always, confidence validated (§8)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("locale,caveat", [
    ("en", "not a guarantee of fit"),
    ("ar", "وليست ضماناً للمقاس"),
])
def test_fit_caveat_is_mandatory_in_html_and_text(locale: str, caveat: str):
    content = render_email("fit_result", locale, PAYLOADS["fit_result"])
    assert caveat in content.html
    assert caveat in content.text


@pytest.mark.parametrize("bad", [-1, 101, "high", None])
def test_fit_confidence_must_be_a_real_percentage(bad):
    payload = dict(PAYLOADS["fit_result"])
    payload["confidence_pct"] = bad
    with pytest.raises(EmailTemplateError):
        render_email("fit_result", "en", payload)


# ---------------------------------------------------------------------------
# Samples power the admin preview and must themselves be honest
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("template", sorted(TEMPLATES))
def test_sample_payloads_render_and_are_visibly_samples(template: str):
    content = render_email(template, "en", sample_payload(template))
    assert "sample" in (content.html + content.subject).lower()  # Sample/SAMPLE marker


# ---------------------------------------------------------------------------
# Outbox: idempotency + the five-state delivery contract
# ---------------------------------------------------------------------------

@pytest.fixture()
def outbox_db():
    from backend.app.core.database import Base
    import backend.app.models  # noqa: F401 — register all mappers

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _dispatch(db, monkeypatch, sends: list, *, fail=False, **overrides):
    from backend.app.services import email_outbox as outbox_mod
    from backend.app.services.email_service import EmailDeliveryError

    def fake_send(to, subject, html, text=None, headers=None):
        if fail:
            raise EmailDeliveryError("Relay rejected message: 525 5.7.1")
        sends.append({"to": to, "subject": subject, "headers": headers})
        return {"message_id": f"<msg-{len(sends)}@confit.test>"}

    monkeypatch.setattr(outbox_mod, "send_email", fake_send)
    kwargs = dict(
        event_key="order:1042:order_confirmation",
        template="order_confirmation", locale="en",
        recipient="shopper@confit.test",
        payload=PAYLOADS["order_confirmation"],
    )
    kwargs.update(overrides)
    return outbox_mod.dispatch(db, **kwargs)


def test_same_event_key_sends_exactly_once(outbox_db, monkeypatch):
    sends: list = []
    first = _dispatch(outbox_db, monkeypatch, sends)
    assert first.status == "sent"
    assert first.message_id
    assert len(sends) == 1

    replay = _dispatch(outbox_db, monkeypatch, sends)
    assert replay.id == first.id
    assert replay.status == "sent"
    assert len(sends) == 1  # idempotent: the replay did NOT send again


def test_transport_failure_is_recorded_honestly_and_retryable(outbox_db, monkeypatch):
    sends: list = []
    failed = _dispatch(outbox_db, monkeypatch, sends, fail=True)
    assert failed.status == "failed"
    assert "525" in failed.last_error
    assert failed.attempts == 1
    assert len(sends) == 0  # nothing pretended to be sent

    # A failed event MAY be retried with the same key — failure is the one
    # non-terminal outcome.
    recovered = _dispatch(outbox_db, monkeypatch, sends)
    assert recovered.id == failed.id
    assert recovered.status == "sent"
    assert recovered.attempts == 2
    assert recovered.last_error is None
    assert len(sends) == 1


def test_suppressed_recipient_is_recorded_not_sent(outbox_db, monkeypatch):
    sends: list = []
    row = _dispatch(
        outbox_db, monkeypatch, sends,
        event_key="newsletter:2026-10:u7", template="newsletter",
        payload={}, suppressed=True,
    )
    assert row.status == "unsubscribed"
    assert len(sends) == 0
    # Terminal: a later replay without suppression still does not send.
    replay = _dispatch(
        outbox_db, monkeypatch, sends,
        event_key="newsletter:2026-10:u7", template="newsletter",
        payload=PAYLOADS["newsletter"],
    )
    assert replay.status == "unsubscribed"
    assert len(sends) == 0


def test_bounce_webhook_hook_moves_sent_to_bounced(outbox_db, monkeypatch):
    from backend.app.services.email_outbox import record_bounce

    sends: list = []
    row = _dispatch(outbox_db, monkeypatch, sends)
    assert row.status == "sent"
    bounced = record_bounce(
        outbox_db, event_key=row.event_key, detail="550 mailbox unavailable"
    )
    assert bounced.status == "bounced"
    assert "550" in bounced.last_error


def test_bad_payload_fails_before_consuming_a_send(outbox_db, monkeypatch):
    sends: list = []
    with pytest.raises(EmailTemplateError):
        _dispatch(outbox_db, monkeypatch, sends, payload={"order_number": "X"})
    assert len(sends) == 0


# ---------------------------------------------------------------------------
# Admin endpoints — RBAC + sample-only preview
# ---------------------------------------------------------------------------

def _login(client: TestClient, email: str, password: str = "Password123!") -> str:
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def test_preview_requires_admin(client: TestClient):
    # Anonymous checks FIRST: login sets a session cookie on the shared
    # TestClient, so a later "anonymous" call would silently be a consumer.
    anon = client.get("/api/v1/admin/diagnostics/email/preview?template=newsletter")
    assert anon.status_code == 401
    anon_list = client.get("/api/v1/admin/diagnostics/email/templates")
    assert anon_list.status_code == 401
    consumer = client.get(
        "/api/v1/admin/diagnostics/email/preview?template=newsletter",
        headers={"Authorization": f"Bearer {_login(client, 'shopper@confit.io')}"},
    )
    assert consumer.status_code == 403


def test_admin_lists_and_previews_sample_only(client: TestClient):
    admin = {"Authorization": f"Bearer {_login(client, 'admin@confit.io')}"}

    listed = client.get("/api/v1/admin/diagnostics/email/templates", headers=admin)
    assert listed.status_code == 200
    body = listed.json()
    assert len(body["templates"]) == 10
    assert body["locales"] == ["en", "ar"]

    preview = client.get(
        "/api/v1/admin/diagnostics/email/preview?template=order_confirmation&locale=ar",
        headers=admin,
    )
    assert preview.status_code == 200
    data = preview.json()
    assert data["sample_data"] is True
    assert "SAMPLE-0001" in data["html"]
    assert 'dir="rtl"' in data["html"]
    assert data["text"]

    bogus = client.get(
        "/api/v1/admin/diagnostics/email/preview?template=spam_blast", headers=admin
    )
    assert bogus.status_code == 422
