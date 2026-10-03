"""Feature 07 — worker shell tests: image resolution + request validation.

These pin the HTTP boundary logic of modal_app.py (pure functions, no
models): data-URL decoding, mime allow-list, size ceiling, http(s) fetch
with error taxonomy. The full request/response contract against the REAL
models is validated by the live smoke of the deployed worker (same
discipline as the anthropometry worker).
"""
from __future__ import annotations

import base64
import sys
import urllib.request
from pathlib import Path
from unittest.mock import patch

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import modal_app  # noqa: E402
from fastapi import HTTPException  # noqa: E402

FIXTURES = HERE / "fixtures"


def _data_url(mime="image/jpeg") -> str:
    blob = (FIXTURES / "blazer_navy.jpg").read_bytes()
    return f"data:{mime};base64," + base64.b64encode(blob).decode()


class TestFetchImage:
    def test_none_returns_none(self):
        assert modal_app._fetch_image(None) is None
        assert modal_app._fetch_image("") is None

    def test_valid_data_url_decodes(self):
        blob = modal_app._fetch_image(_data_url())
        assert blob[:3] == b"\xff\xd8\xff"  # JPEG magic

    def test_bad_mime_is_422(self):
        with pytest.raises(HTTPException) as ei:
            modal_app._fetch_image(_data_url("image/gif"))
        assert ei.value.status_code == 422
        assert ei.value.detail["error"]["code"] == "INVALID_IMAGE"

    def test_bad_base64_is_422(self):
        with pytest.raises(HTTPException) as ei:
            modal_app._fetch_image("data:image/jpeg;base64,!!!not-base64!!!")
        assert ei.value.detail["error"]["code"] == "INVALID_IMAGE"

    def test_oversize_is_422(self):
        big = b"x" * (modal_app.MAX_IMAGE_BYTES + 1)
        url = "data:image/jpeg;base64," + base64.b64encode(big).decode()
        with pytest.raises(HTTPException) as ei:
            modal_app._fetch_image(url)
        assert ei.value.detail["error"]["code"] == "IMAGE_TOO_LARGE"

    def test_http_url_fetched(self):
        blob = (FIXTURES / "blazer_navy.jpg").read_bytes()
        with patch.object(urllib.request, "urlopen") as m:
            m.return_value.__enter__.return_value.read.return_value = blob
            assert modal_app._fetch_image("https://example.com/p.jpg") == blob
            req = m.call_args[0][0]
            assert req.headers["User-agent"] == "confit-tagging-worker/1.0"

    def test_http_fetch_failure_is_422(self):
        with patch.object(urllib.request, "urlopen", side_effect=OSError("boom")):
            with pytest.raises(HTTPException) as ei:
                modal_app._fetch_image("https://example.com/p.jpg")
            assert ei.value.detail["error"]["code"] == "IMAGE_FETCH_FAILED"

    def test_unknown_scheme_is_422(self):
        with pytest.raises(HTTPException) as ei:
            modal_app._fetch_image("ftp://example.com/p.jpg")
        assert ei.value.detail["error"]["code"] == "INVALID_IMAGE"


class TestRequestModel:
    def test_job_id_validation(self):
        from pydantic import ValidationError
        for bad in ("", "x" * 101, "bad job", "bad/job"):
            with pytest.raises(ValidationError):
                modal_app.TagRequest(job_id=bad)
        assert modal_app.TagRequest(job_id="ok_job-1").job_id == "ok_job-1"

    def test_all_optional_except_job_id(self):
        r = modal_app.TagRequest(job_id="j", title=None, description=None)
        assert r.image_base64_or_url is None
