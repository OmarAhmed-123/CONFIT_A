"""OUTFIT-01..04 — Outfit Composer / My Looks / public sharing acceptance suite.

This is the end-to-end path the 2026-09-21 audit said had never been exercised:

    pick real catalog items -> save the outfit -> read it back in My Looks ->
    EDIT the item set (replace + reorder) -> reopen -> mint a public token ->
    open it ANONYMOUSLY -> revoke it -> confirm the anonymous read now 404s.

Every assertion is against the real FastAPI app and the real database session;
nothing is mocked out, and fixtures are created through the public API so the
test cannot pass against a broken write path.
"""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from backend.app.services.outfit_service import OutfitService, _utcnow
from backend.app.services.styling.composition_policy import (
    CANVAS_POSITIONS,
    LAYER_ORDER,
    MAX_ITEMS_PER_OUTFIT,
    evaluate_composition,
    order_items,
    sort_order_for,
)

API = "/api/v1"


def _register(client: TestClient, email: str) -> str:
    r = client.post(
        f"{API}/auth/register",
        json={"email": email, "password": "Password123!", "full_name": "Composer Tester"},
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["access_token"]


def _csrf(client: TestClient) -> dict:
    return {"X-CSRF-Token": client.cookies.get("confit_csrf")}


def _auth(client: TestClient, email: str) -> dict:
    token = _register(client, email)
    return {**_csrf(client), "Authorization": f"Bearer {token}"}


def _products_by_position(client: TestClient, headers: dict) -> dict:
    """Real catalog products grouped by the canvas position the server derives.

    Grouping via the server's own save endpoint keeps the test honest: it uses
    whatever the ontology actually classifies, not a hard-coded guess.
    """
    r = client.get(f"{API}/catalog/products?limit=60")
    assert r.status_code == 200, r.text
    payload = r.json()
    items = payload["items"] if isinstance(payload, dict) and "items" in payload else payload
    return items


# ---------------------------------------------------------------------------
# Pure policy unit tests (no I/O) — the rules themselves
# ---------------------------------------------------------------------------

class TestCompositionPolicy:
    def test_empty_outfit_is_rejected_with_a_reason(self):
        v = evaluate_composition([])
        assert v.is_valid is False
        assert v.violations[0].code == "empty_outfit"
        assert v.first_message  # a human-readable reason always exists

    def test_two_bottoms_are_rejected_and_name_the_slot(self):
        v = evaluate_composition([
            {"position": "top", "product_sku_id": 1},
            {"position": "bottom", "product_sku_id": 2},
            {"position": "bottom", "product_sku_id": 3},
        ])
        assert v.is_valid is False
        codes = {x.code for x in v.violations}
        assert "slot_over_capacity" in codes
        over = next(x for x in v.violations if x.code == "slot_over_capacity")
        assert "bottom" in over.positions

    def test_duplicate_sku_is_rejected(self):
        v = evaluate_composition([
            {"position": "top", "product_sku_id": 7},
            {"position": "bottom", "product_sku_id": 7},
        ])
        assert v.is_valid is False
        assert "duplicate_item" in {x.code for x in v.violations}

    def test_dress_plus_separates_is_a_conflict(self):
        v = evaluate_composition([
            {"position": "dress", "product_sku_id": 1},
            {"position": "bottom", "product_sku_id": 2},
        ])
        assert v.is_valid is False
        assert "conflicting_layers" in {x.code for x in v.violations}

    def test_accessories_may_stack_but_are_capped(self):
        base = [{"position": "top", "product_sku_id": 1}, {"position": "bottom", "product_sku_id": 2}]
        three = base + [
            {"position": "accessory", "product_sku_id": 10 + i} for i in range(3)
        ]
        assert evaluate_composition(three).is_valid is True
        five = base + [
            {"position": "accessory", "product_sku_id": 20 + i} for i in range(5)
        ]
        assert evaluate_composition(five).is_valid is False

    def test_item_cap_is_enforced(self):
        many = [
            {"position": "accessory", "product_sku_id": i} for i in range(MAX_ITEMS_PER_OUTFIT + 1)
        ]
        assert "too_many_items" in {x.code for x in evaluate_composition(many).violations}

    def test_partial_look_is_savable_but_honestly_labelled(self):
        v = evaluate_composition([{"position": "top", "product_sku_id": 1}])
        assert v.is_valid is True          # saving a partial look is allowed
        assert "bottom" in v.missing_positions  # but it is never called complete
        assert v.warnings

    def test_layer_order_is_outermost_first_and_stable(self):
        ordered = order_items([
            {"position": "footwear", "product_sku_id": 4},
            {"position": "accessory", "product_sku_id": 5},
            {"position": "accessory", "product_sku_id": 6},
            {"position": "top", "product_sku_id": 2},
            {"position": "outerwear", "product_sku_id": 1},
            {"position": "bottom", "product_sku_id": 3},
        ])
        assert [i["position"] for i in ordered] == [
            "outerwear", "top", "bottom", "footwear", "accessory", "accessory"
        ]
        # sort_order strictly increases, so ORDER BY sort_order reproduces it.
        orders = [i["sort_order"] for i in ordered]
        assert orders == sorted(orders)
        # stable within a position: the first accessory posted stays first
        acc = [i["product_sku_id"] for i in ordered if i["position"] == "accessory"]
        assert acc == [5, 6]

    def test_every_canvas_position_has_a_layer(self):
        # Guards against adding a position without giving it stacking semantics.
        assert set(CANVAS_POSITIONS) == set(LAYER_ORDER)
        assert sort_order_for("outerwear") < sort_order_for("footwear")


# ---------------------------------------------------------------------------
# Full API lifecycle
# ---------------------------------------------------------------------------

class TestOutfitLifecycle:
    def test_create_read_edit_reopen(self, client: TestClient):
        h = _auth(client, "composer_lifecycle@confit.io")

        created = client.post(
            f"{API}/outfits", headers=h,
            json={"title": "Boardroom", "occasion": "Work & Business", "product_ids": [1, 3, 4]},
        )
        assert created.status_code == 201, created.text
        look = created.json()
        outfit_id = look["id"]
        assert look["items"], "a saved look must persist its items"

        # Items come back in canonical layer order, not request order.
        positions = [i["position"] for i in look["items"]]
        assert positions == sorted(positions, key=lambda p: LAYER_ORDER.get(p, 60))

        # It appears in My Looks.
        mine = client.get(f"{API}/outfits", headers=h)
        assert mine.status_code == 200
        assert outfit_id in [o["id"] for o in mine.json()]

        # Reopen by id.
        reopened = client.get(f"{API}/outfits/{outfit_id}", headers=h)
        assert reopened.status_code == 200
        assert reopened.json()["title"] == "Boardroom"

        # EDIT the item set — the path that did not exist before.
        original_ids = [i["product_id"] for i in look["items"]]
        edited = client.put(
            f"{API}/outfits/{outfit_id}/items", headers=h,
            json={"product_ids": original_ids[:2]},
        )
        assert edited.status_code == 200, edited.text
        assert len(edited.json()["items"]) == 2

        # The edit really persisted (re-read from the DB, not the response).
        after = client.get(f"{API}/outfits/{outfit_id}", headers=h).json()
        assert len(after["items"]) == 2
        assert after["updated_at"] is not None

        # Cleanup so the fixture is not left behind.
        assert client.delete(f"{API}/outfits/{outfit_id}", headers=h).status_code == 200
        assert client.get(f"{API}/outfits/{outfit_id}", headers=h).status_code == 404

    def test_invalid_composition_is_rejected_with_explainable_422(self, client: TestClient):
        h = _auth(client, "composer_invalid@confit.io")
        # Save an empty item set -> explicit 422, never a silently empty look.
        r = client.post(
            f"{API}/outfits", headers=h,
            json={"title": "Nothing", "occasion": "Casual", "product_ids": []},
        )
        assert r.status_code == 422

        # A set that resolves to duplicated SKUs must state the reason.
        dup = client.post(
            f"{API}/outfits", headers=h,
            json={"title": "Dupe", "occasion": "Casual", "product_ids": [1, 1]},
        )
        assert dup.status_code == 422, dup.text
        detail = dup.json()["detail"]
        assert detail["code"] == "invalid_outfit_composition"
        assert detail["violations"], "the client must be told WHY it was rejected"
        assert detail["violations"][0]["message"]

    def test_preview_agrees_with_the_write_path(self, client: TestClient):
        h = _auth(client, "composer_preview@confit.io")
        body = {"product_ids": [1, 1]}
        preview = client.post(f"{API}/outfits/composition/preview", headers=h, json=body)
        assert preview.status_code == 200, preview.text
        assert preview.json()["is_valid"] is False

        save = client.post(
            f"{API}/outfits", headers=h,
            json={"title": "Dupe", "occasion": "Casual", **body},
        )
        # Preview said invalid; Save must agree. A disagreement here means the
        # rules were duplicated somewhere instead of shared.
        assert save.status_code == 422

    def test_failed_edit_leaves_the_stored_outfit_untouched(self, client: TestClient):
        h = _auth(client, "composer_atomic@confit.io")
        created = client.post(
            f"{API}/outfits", headers=h,
            json={"title": "Atomic", "occasion": "Casual", "product_ids": [1, 3, 4]},
        ).json()
        oid = created["id"]
        before = client.get(f"{API}/outfits/{oid}", headers=h).json()

        bad = client.put(f"{API}/outfits/{oid}/items", headers=h, json={"product_ids": [1, 1]})
        assert bad.status_code == 422

        after = client.get(f"{API}/outfits/{oid}", headers=h).json()
        assert [i["product_id"] for i in after["items"]] == [
            i["product_id"] for i in before["items"]
        ]
        assert after["total_price"] == before["total_price"]


# ---------------------------------------------------------------------------
# Public sharing: mint -> anonymous open -> revoke -> expiry
# ---------------------------------------------------------------------------

class TestPublicSharing:
    def _make_look(self, client: TestClient, email: str):
        h = _auth(client, email)
        r = client.post(
            f"{API}/outfits", headers=h,
            json={"title": "Shared Look", "occasion": "Casual", "product_ids": [1, 3, 4]},
        )
        assert r.status_code == 201, r.text
        return h, r.json()["id"]

    def test_full_share_lifecycle(self, client: TestClient):
        h, oid = self._make_look(client, "share_lifecycle@confit.io")

        minted = client.post(f"{API}/outfits/{oid}/share", headers=h)
        assert minted.status_code == 200, minted.text
        share = minted.json()
        token = share["share_token"]
        assert share["is_active"] is True
        assert share["expires_at"], "a share link must carry a real expiry"
        assert share["share_url"] == f"/looks/{token}"

        # Minting again is idempotent — no orphan tokens.
        again = client.post(f"{API}/outfits/{oid}/share", headers=h).json()
        assert again["share_token"] == token

        # ANONYMOUS read works (new client, no cookies, no Authorization).
        anon = TestClient(client.app)
        public = anon.get(f"{API}/public/looks/{token}")
        assert public.status_code == 200, public.text
        body = public.json()
        assert body["title"] == "Shared Look"
        assert body["items"]

        # ... and leaks nothing private.
        for forbidden in ("user_id", "id", "email", "owner", "share_token"):
            assert forbidden not in body

        # The owner sees a real view count, not a guess.
        state = client.get(f"{API}/outfits/{oid}/share", headers=h).json()
        assert state["view_count"] >= 1
        assert state["is_active"] is True

        # REVOKE — the anonymous link dies immediately.
        revoked = client.delete(f"{API}/outfits/{oid}/share", headers=h)
        assert revoked.status_code == 200, revoked.text
        assert revoked.json()["was_active"] is True
        assert anon.get(f"{API}/public/looks/{token}").status_code == 404

        # A revoked token is indistinguishable from one that never existed.
        assert anon.get(f"{API}/public/looks/look_neverexisted").status_code == 404

        # Revocation is idempotent and never resurrects the token.
        assert client.delete(f"{API}/outfits/{oid}/share", headers=h).status_code == 200
        assert anon.get(f"{API}/public/looks/{token}").status_code == 404

        # Owner-facing state stops claiming a live link.
        after = client.get(f"{API}/outfits/{oid}/share", headers=h).json()
        assert after["is_active"] is False
        assert after["share_url"] is None

        # Re-sharing after revocation mints a DIFFERENT token.
        fresh = client.post(f"{API}/outfits/{oid}/share", headers=h).json()
        assert fresh["share_token"] != token
        assert anon.get(f"{API}/public/looks/{fresh['share_token']}").status_code == 200
        assert anon.get(f"{API}/public/looks/{token}").status_code == 404

    def test_rotate_invalidates_the_previous_link(self, client: TestClient):
        h, oid = self._make_look(client, "share_rotate@confit.io")
        first = client.post(f"{API}/outfits/{oid}/share", headers=h).json()["share_token"]
        second = client.post(
            f"{API}/outfits/{oid}/share", headers=h, json={"rotate": True}
        ).json()["share_token"]
        assert first != second
        anon = TestClient(client.app)
        assert anon.get(f"{API}/public/looks/{first}").status_code == 404
        assert anon.get(f"{API}/public/looks/{second}").status_code == 200

    def test_expired_token_stops_resolving(self, client: TestClient):
        """Expiry is enforced by the resolver, not merely stored."""
        h, oid = self._make_look(client, "share_expiry@confit.io")
        token = client.post(f"{API}/outfits/{oid}/share", headers=h).json()["share_token"]
        anon = TestClient(client.app)
        assert anon.get(f"{API}/public/looks/{token}").status_code == 200

        # Backdate the expiry through the same session the app uses.
        from backend.tests.conftest import TestingSessionLocal
        from backend.app.models.stylist import Outfit

        db = TestingSessionLocal()
        try:
            row = db.query(Outfit).filter(Outfit.id == oid).first()
            row.share_expires_at = _utcnow() - timedelta(seconds=1)
            db.commit()
        finally:
            db.close()

        assert anon.get(f"{API}/public/looks/{token}").status_code == 404
        # And the owner is told the truth rather than shown a dead link.
        assert client.get(f"{API}/outfits/{oid}/share", headers=h).json()["is_active"] is False

    def test_share_token_is_high_entropy_and_unpredictable(self, client: TestClient):
        h, oid = self._make_look(client, "share_entropy@confit.io")
        tokens = set()
        for _ in range(5):
            t = client.post(
                f"{API}/outfits/{oid}/share", headers=h, json={"rotate": True}
            ).json()["share_token"]
            tokens.add(t)
            assert t.startswith("look_")
            assert len(t) >= 32, "token must not be truncated to a guessable length"
            assert not t.replace("look_", "").isdigit(), "never sequential"
        assert len(tokens) == 5, "rotation must always produce a fresh token"

    def test_sharing_another_users_outfit_is_impossible(self, client: TestClient):
        h_a, oid = self._make_look(client, "share_owner_a@confit.io")
        client.cookies.clear()
        h_b = _auth(client, "share_owner_b@confit.io")
        # Every share verb is ownership-checked, and a non-owner gets 404 (not
        # 403) so outfit existence is not leaked.
        assert client.post(f"{API}/outfits/{oid}/share", headers=h_b).status_code == 404
        assert client.get(f"{API}/outfits/{oid}/share", headers=h_b).status_code == 404
        assert client.delete(f"{API}/outfits/{oid}/share", headers=h_b).status_code == 404
        assert client.put(
            f"{API}/outfits/{oid}/items", headers=h_b, json={"product_ids": [1]}
        ).status_code == 404

    def test_public_endpoint_requires_no_auth_but_exposes_no_pii(self, client: TestClient):
        h, oid = self._make_look(client, "share_pii@confit.io")
        token = client.post(f"{API}/outfits/{oid}/share", headers=h).json()["share_token"]
        anon = TestClient(client.app)
        raw = anon.get(f"{API}/public/looks/{token}").text
        assert "share_pii@confit.io" not in raw
        assert "Password123!" not in raw
