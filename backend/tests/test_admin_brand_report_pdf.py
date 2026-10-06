"""Admin brand-report PDF export — the spec-12 export gap, closed for real.

The command center documented "no export endpoint exists server-side" and
honestly showed no export UI. This surface is the real contract that replaces
that gap: an ADMIN downloads, per brand, the exact product/sales dataset the
brand owner gets (same service, same SQL), rendered by the same reportlab
renderer — permissioned server-side and audited BEFORE the bytes leave.

What these tests pin:
  * admin gets real PDF bytes (magic number, attachment filename) — not an
    empty 200;
  * every generation writes an ADMIN_BRAND_REPORT_PDF_GENERATED audit row
    carrying brand_id + row count;
  * a consumer gets 403 from the server, not from a frontend guard;
  * an unknown brand is a plain 404 — never a blank report;
  * junk dates are refused with 422 before any query runs.
"""
from fastapi.testclient import TestClient

from backend.app.models.user import AuditLog
from backend.tests.conftest import TestingSessionLocal


def _login(client: TestClient, email: str) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def _headers(client: TestClient, email: str) -> dict:
    return {"Authorization": f"Bearer {_login(client, email)}"}


def _any_brand_id(client: TestClient, headers: dict) -> int:
    brands = client.get("/api/v1/admin/catalog/brands", headers=headers)
    assert brands.status_code == 200, brands.text
    rows = brands.json()
    assert rows, "seeded database must expose at least one brand"
    return max(rows, key=lambda row: row["product_count"])["id"]


def test_admin_downloads_real_pdf_and_the_export_is_audited(client: TestClient):
    headers = _headers(client, "admin@confit.io")
    brand_id = _any_brand_id(client, headers)

    response = client.get(
        f"/api/v1/admin/catalog/brands/{brand_id}/reports/product-sales.pdf",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF"), "payload must be real PDF bytes"
    assert len(response.content) > 500, "a rendered report is never a stub"
    disposition = response.headers.get("content-disposition", "")
    assert disposition.startswith('attachment; filename="confit-')
    assert disposition.endswith('.pdf"')

    with TestingSessionLocal() as db:
        row = (
            db.query(AuditLog)
            .filter(AuditLog.action == "ADMIN_BRAND_REPORT_PDF_GENERATED")
            .order_by(AuditLog.id.desc())
            .first()
        )
        assert row is not None, "export must write an audit row"
        assert row.resource_type == "BrandProfile"
        import json as _json
        after = _json.loads(row.after_json or "{}")
        assert after.get("brand_id") == brand_id
        assert "rows" in after and "period" in after


def test_consumer_is_refused_by_the_server_not_the_frontend(client: TestClient):
    headers = _headers(client, "shopper@confit.io")
    response = client.get(
        "/api/v1/admin/catalog/brands/1/reports/product-sales.pdf",
        headers=headers,
    )
    assert response.status_code == 403


def test_unknown_brand_is_a_plain_404_never_a_blank_report(client: TestClient):
    headers = _headers(client, "admin@confit.io")
    response = client.get(
        "/api/v1/admin/catalog/brands/999999/reports/product-sales.pdf",
        headers=headers,
    )
    assert response.status_code == 404


def test_junk_dates_are_refused_with_422(client: TestClient):
    headers = _headers(client, "admin@confit.io")
    brand_id = _any_brand_id(client, headers)
    base = f"/api/v1/admin/catalog/brands/{brand_id}/reports/product-sales.pdf"

    junk = client.get(f"{base}?date_from=not-a-date", headers=headers)
    assert junk.status_code == 422

    inverted = client.get(
        f"{base}?date_from=2026-02-01&date_to=2026-01-01", headers=headers
    )
    assert inverted.status_code == 422
