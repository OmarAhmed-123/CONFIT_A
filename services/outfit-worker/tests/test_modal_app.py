"""Feature 06 — worker shell tests: image resolution + request validation.

Pins the HTTP boundary logic of modal_app.py (pure functions, no models):
data-URL decoding, mime allow-list, per-image and TOTAL payload ceilings,
multi-image decode for outfit+candidate lists, request-model validation.
The full request/response contract against the REAL checkpoints is pinned
by the live validation of the deployed worker
(test_deployed_type_aware_eval.py).
"""
from __future__ import annotations

import base64
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import modal_app  # noqa: E402

FIXTURES = HERE / "fixtures"


def _data_url(name: str = "blazer_navy.jpg", mime: str = "image/jpeg") -> str:
    blob = (FIXTURES / name).read_bytes()
    return f"data:{mime};base64," + base64.b64encode(blob).decode()


def _http_error_code(excinfo) -> str:
    return excinfo.value.detail["error"]["code"]


class TestFetchImage:
    def test_valid_data_url_decodes(self):
        blob = modal_app._fetch_image(_data_url())
        assert blob[:3] == b"\xff\xd8\xff"  # JPEG magic

    def test_wrong_mime_refused(self):
        with pytest.raises(HTTPException) as e:
            modal_app._fetch_image(_data_url(mime="image/gif"))
        assert _http_error_code(e) == "INVALID_IMAGE"

    def test_bad_base64_refused(self):
        with pytest.raises(HTTPException) as e:
            modal_app._fetch_image("data:image/jpeg;base64,%%%not-b64")
        assert _http_error_code(e) == "INVALID_IMAGE"

    def test_non_url_refused(self):
        with pytest.raises(HTTPException) as e:
            modal_app._fetch_image("ftp://example.com/img.jpg")
        assert _http_error_code(e) == "INVALID_IMAGE"

    def test_oversized_data_url_refused(self):
        big = b"x" * (modal_app.MAX_IMAGE_BYTES + 1)
        url = "data:image/jpeg;base64," + base64.b64encode(big).decode()
        with pytest.raises(HTTPException) as e:
            modal_app._fetch_image(url)
        assert _http_error_code(e) == "IMAGE_TOO_LARGE"

    def test_dead_http_url_refused(self):
        with pytest.raises(HTTPException) as e:
            modal_app._fetch_image("http://127.0.0.1:9/never.jpg")
        assert _http_error_code(e) == "IMAGE_FETCH_FAILED"


class TestDecodeImages:
    def _items(self, *names):
        return [
            type("Spec", (), {"image_base64_or_url": _data_url(n)})()
            for n in names
        ]

    def test_multi_image_decode(self):
        images = modal_app._decode_images(
            self._items("blazer_navy.jpg", "wool_trousers.jpg",
                        "leather_oxford_shoes.jpg"))
        assert len(images) == 3
        assert all(img.size[0] > 0 for img in images)

    def test_empty_list_is_empty(self):
        assert modal_app._decode_images([]) == []

    def test_one_bad_image_fails_whole_request(self):
        class Bad:
            image_base64_or_url = "data:image/gif;base64,R0lGOD"
        with pytest.raises(HTTPException) as e:
            modal_app._decode_images(
                self._items("blazer_navy.jpg") + [Bad()])
        assert _http_error_code(e) == "INVALID_IMAGE"

    def test_total_payload_budget_enforced(self, monkeypatch):
        monkeypatch.setattr(modal_app, "MAX_TOTAL_IMAGE_BYTES", 100_000)
        with pytest.raises(HTTPException) as e:
            modal_app._decode_images(
                self._items("blazer_navy.jpg", "silk_maxi_dress.jpg"))
        assert _http_error_code(e) == "PAYLOAD_TOO_LARGE"

    def test_undecodable_bytes_refused(self, monkeypatch):
        junk = "data:image/jpeg;base64," + base64.b64encode(b"not an image").decode()
        monkeypatch.setattr(modal_app, "_fetch_image", lambda s: b"not an image")
        spec = type("Spec", (), {"image_base64_or_url": junk})()
        with pytest.raises(HTTPException) as e:
            modal_app._decode_images([spec])
        assert _http_error_code(e) == "INVALID_IMAGE"


class TestRequestModels:
    def test_job_id_charset(self):
        with pytest.raises(ValueError):
            modal_app.CompatibilityRequest(job_id="bad id!", items=[])
        modal_app.CompatibilityRequest(
            job_id="job-123_OK", items=[
                modal_app.ItemSpec(image_base64_or_url=_data_url())])

    def test_item_requires_image(self):
        with pytest.raises(ValueError):
            modal_app.ItemSpec(image_base64_or_url="")

    def test_top_k_bounds(self):
        with pytest.raises(ValueError):
            modal_app.FillInTheBlankRequest(
                job_id="j", outfit=[], candidates=[], top_k=0)
        with pytest.raises(ValueError):
            modal_app.FillInTheBlankRequest(
                job_id="j", outfit=[], candidates=[], top_k=21)
        modal_app.FillInTheBlankRequest(
            job_id="j", outfit=[], candidates=[], top_k=20)

    def test_candidate_requires_id(self):
        with pytest.raises(ValueError):
            modal_app.CandidateSpec(image_base64_or_url=_data_url())
        c = modal_app.CandidateSpec(
            id="42", image_base64_or_url=_data_url(), slot="footwear")
        assert c.id == "42" and c.slot == "footwear"


class TestContractConstants:
    def test_limits_are_consistent_with_core(self):
        import outfit_core as oc
        assert modal_app is not None
        assert oc.MAX_COMPAT_ITEMS == 16
        assert oc.MAX_FITB_CANDIDATES == 64
        assert oc.MIN_COMPAT_ITEMS == 2

    def test_auth_env_name_matches_secret_contract(self):
        # The Modal secret `confit-outfit-admin-token` must inject the env
        # var the code reads — a mismatch would silently 401 every call.
        import re
        src = Path(modal_app.__file__).read_text()
        assert 'modal.Secret.from_name("confit-outfit-admin-token")' in src
        assert 'OUTFIT_WORKER_ADMIN_TOKEN' in src
        assert 'X-VTON-Admin' in src
