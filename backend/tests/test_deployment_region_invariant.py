"""Deployment invariant: the API must execute in the same region as the database.

WHY THIS TEST EXISTS
The audit measured /brand/analytics at 4.8s and /partner/analytics/conversion at
6.1s. Two rounds of query optimisation reduced the hop COUNT and helped, but the
endpoints stayed above the 2.0s SLO. The actual dominant cause was not in the
application at all: vercel.json pinned no region, so the Python function ran in
Vercel's default iad1 (Washington DC) while the Neon database lives in
eu-central-1 (Frankfurt). Every SQL statement crossed the Atlantic, which is why
the per-statement cost was flat (~150ms) regardless of how little data it
touched. Pinning regions:["fra1"] took those endpoints to 0.37s and 0.28s.

That fix is ONE LINE OF CONFIGURATION and nothing protected it. Deleting the
"regions" key is a silent, plausible-looking edit that would restore a ~13x
latency regression while every unit test, type check and query-budget test kept
passing -- because none of them can observe geography.

Query-budget tests explicitly DO NOT cover this. They pin how many round trips
are made, not how far each one travels. This file covers the other half.

It is a plain pytest module so it runs inside the existing required `backend`
CI job, with no new workflow or infrastructure dependency.
"""
import json
import os
import re

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
VERCEL_JSON = os.path.join(REPO_ROOT, "vercel.json")

# Vercel region -> the cloud region it physically sits in.
VERCEL_REGION_TO_CLOUD = {
    "fra1": "eu-central-1",   # Frankfurt
    "iad1": "us-east-1",      # Washington DC
    "sfo1": "us-west-1",
    "cdg1": "eu-west-3",
    "lhr1": "eu-west-2",
    "dub1": "eu-west-1",
    "arn1": "eu-north-1",
    "hnd1": "ap-northeast-1",
    "sin1": "ap-southeast-1",
    "syd1": "ap-southeast-2",
    "gru1": "sa-east-1",
    "bom1": "ap-south-1",
    "icn1": "ap-northeast-2",
    "pdx1": "us-west-2",
    "cle1": "us-east-2",
}

# The database's cloud region, as recorded in the deployment runbook. Changing
# this constant is a deliberate act and should accompany an actual database move.
EXPECTED_DB_CLOUD_REGION = "eu-central-1"


@pytest.fixture(scope="module")
def vercel_config():
    assert os.path.exists(VERCEL_JSON), f"vercel.json not found at {VERCEL_JSON}"
    with open(VERCEL_JSON) as fh:
        return json.load(fh)


class TestExecutionRegionIsPinned:
    def test_regions_key_is_present(self, vercel_config):
        """Without this key Vercel silently defaults to iad1 (Washington DC)."""
        assert "regions" in vercel_config, (
            "vercel.json has no 'regions' key. Vercel then defaults to iad1 "
            "(Washington DC) while the database is in eu-central-1 (Frankfurt), so "
            "every SQL statement crosses the Atlantic. That is the configuration "
            "that caused the 4.8s/6.1s analytics latency in the audit; pinning the "
            "region took the same endpoints to 0.37s/0.28s."
        )

    def test_exactly_one_region_is_pinned(self, vercel_config):
        regions = vercel_config["regions"]
        assert isinstance(regions, list) and regions, "regions must be a non-empty list"
        assert len(regions) == 1, (
            f"expected exactly one execution region, found {regions}. Multiple "
            f"regions means some invocations are far from the single-region "
            f"database, reintroducing the transatlantic penalty for a subset of "
            f"traffic -- which is harder to diagnose than a uniform regression."
        )

    def test_execution_region_matches_the_database_region(self, vercel_config):
        region = vercel_config["regions"][0]
        assert region in VERCEL_REGION_TO_CLOUD, (
            f"unknown Vercel region {region!r}. Add it to VERCEL_REGION_TO_CLOUD "
            f"with its cloud region so this invariant can still be checked."
        )
        cloud = VERCEL_REGION_TO_CLOUD[region]
        assert cloud == EXPECTED_DB_CLOUD_REGION, (
            f"the API is configured to execute in {region} ({cloud}) while the "
            f"database is in {EXPECTED_DB_CLOUD_REGION}. Co-location is what keeps "
            f"the brand-portal reads inside the 2.0s SLO; splitting them adds a "
            f"round trip of network latency to EVERY statement.\n"
            f"If the database genuinely moved, update EXPECTED_DB_CLOUD_REGION in "
            f"this file as part of that change."
        )


class TestDatabaseRegionMatchesWhenObservable:
    """When a DSN is present, verify the constant against reality rather than trusting it."""

    def test_configured_dsn_agrees_with_the_expected_region(self):
        dsn = os.getenv("DATABASE_URL") or ""
        host_match = re.search(r"@([^/?]+)", dsn)
        if not host_match:
            pytest.skip("no DATABASE_URL in this environment (normal for CI unit runs)")
        host = host_match.group(1)
        found = re.findall(r"\b((?:eu|us|ap|sa|ca|me|af)-[a-z]+-\d)\b", host)
        if not found:
            pytest.skip(f"host {host.split('@')[-1][:40]} carries no parseable region token")
        assert EXPECTED_DB_CLOUD_REGION in found, (
            f"EXPECTED_DB_CLOUD_REGION is {EXPECTED_DB_CLOUD_REGION!r} but the "
            f"configured database host reports {found}. The invariant in this file "
            f"has drifted from the real deployment -- fix the constant or the DSN."
        )


class TestServerlessRuntimeAssumptions:
    """The pre-ping trade-off is only safe while these hold."""

    def test_max_duration_is_configured_for_the_api_function(self, vercel_config):
        fns = vercel_config.get("functions", {})
        assert "api/index.py" in fns, (
            "the Python API function is not declared in vercel.json 'functions'; "
            "its runtime limits would fall back to platform defaults"
        )
        assert fns["api/index.py"].get("maxDuration"), (
            "maxDuration is unset for api/index.py"
        )
