"""The authz harness must be able to FAIL before its PASS is worth anything.

Section 30 of the brief asks for instrument positive controls; a control that
cannot fire is decoration. The harness aborts on a broken target before its own
controls run (schema guard, auth setup), so the control branches are exercised
here directly against a stub client instead of via a fake API:

* a target that does not serve the public read  -> positive control must abort;
* a target that answers a PROTECTED route 200 to an anonymous caller
  -> negative control must abort (the harness's premise is false there);
* a target that answers something neither 2xx nor 401/403
  -> must abort (cannot tell "denied" from "broken");
* a correct target -> controls pass and are recorded in the results.
"""

from __future__ import annotations

import importlib.util
import pathlib

import pytest

SRC = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "consumer_authz_matrix.py"
_spec = importlib.util.spec_from_file_location("consumer_authz_matrix", SRC)
matrix = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(matrix)


class StubClient:
    """Answers the two control requests with the statuses a case needs."""

    def __init__(self, public: int, protected: int):
        self.public = public
        self.protected = protected
        self.calls = []

    def call(self, method, path, *a, **kw):
        self.calls.append((method, path))
        if path == "/catalog/capabilities":
            return self.public, {}
        if path == "/wardrobe/items":
            return self.protected, {}
        raise AssertionError(f"unexpected control request {method} {path}")


def test_healthy_target_passes_controls_and_records_them():
    results = {}
    client = StubClient(public=200, protected=401)
    matrix.instrument_controls(client, results)
    ctrl = results["instrument_controls"]
    assert ctrl["positive"]["status"] == 200
    assert ctrl["negative"]["status"] == 401
    assert "verified" in ctrl["fail_propagation"]
    assert sorted(p for _, p in client.calls) == ["/catalog/capabilities", "/wardrobe/items"]


def test_public_read_not_serving_aborts():
    with pytest.raises(matrix.Loud) as exc:
        matrix.instrument_controls(StubClient(public=500, protected=401), {})
    assert "positive control" in str(exc.value)


def test_protected_route_answering_200_aborts():
    with pytest.raises(matrix.Loud) as exc:
        matrix.instrument_controls(StubClient(public=200, protected=200), {})
    # Target the DIAGNOSIS, not the word "negative control": both refusal
    # branches mention it, so asserting on the word let a mutation that deleted
    # the leak-specific branch survive (found by mutation run, not by reading).
    # A leaking route must be reported as a leak, not merely as an odd status.
    assert "answered an unauthenticated caller" in str(exc.value)


def test_ambiguous_denial_status_aborts():
    with pytest.raises(matrix.Loud) as exc:
        matrix.instrument_controls(StubClient(public=200, protected=404), {})
    assert "negative control" in str(exc.value)


def test_controls_use_the_same_transport_as_the_matrix():
    """The controls must exercise the harness's own client path, not a shortcut."""
    client = StubClient(public=200, protected=403)
    matrix.instrument_controls(client, {})
    assert [m for m, _ in client.calls] == ["GET", "GET"]
