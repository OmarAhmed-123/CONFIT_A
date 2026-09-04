"""Enqueueing must fail FAST when the broker is unreachable.

Root cause of the ~120s local test timeout (section 12 of the audit brief).

WardrobeService.bulk_upload calls auto_tag_wardrobe_task.delay(), which is
synchronous. With Redis down, kombu's default ensure/retry policy retried 20
times at 1s intervals before raising, so every upload blocked its HTTP request
for ~20 seconds and several upload tests each paid that cost.

This is a production latency defect, not just a slow test: the code already has
an inline-analysis fallback for an unavailable broker, it simply took 20s to
discover it.

The subtlety worth pinning: the redis result backend ignores max_retries at the
top level of result_backend_transport_options. RedisBackend.retry_policy merges
only a NESTED "retry_policy" key over Backend.retry_policy (max_retries=20).
A top-level setting looks correct and does nothing.
"""

import time

import pytest

from backend.app.workers.celery_app import celery_app


class TestBrokerRetryPolicyIsBounded:
    def test_result_backend_retry_policy_is_nested_and_bounded(self):
        opts = celery_app.conf.result_backend_transport_options or {}
        policy = opts.get("retry_policy")
        assert policy is not None, (
            "retry_policy must be NESTED inside result_backend_transport_options; "
            "top-level max_retries is silently ignored by RedisBackend")
        assert policy["max_retries"] <= 3, policy

    def test_broker_and_publish_retries_are_bounded(self):
        bto = celery_app.conf.broker_transport_options or {}
        assert bto.get("max_retries", 20) <= 3, bto
        pub = celery_app.conf.task_publish_retry_policy or {}
        assert pub.get("max_retries", 20) <= 3, pub

    def test_effective_backend_policy_is_not_the_20x_default(self):
        """Assert against the resolved policy, not just our config dict."""
        policy = celery_app.backend.retry_policy
        assert policy["max_retries"] <= 3, (
            f"effective backend retry_policy still {policy} — the 20x1s "
            "'Connection to Redis lost' storm would recur")

    def test_enqueue_against_dead_broker_fails_in_seconds(self):
        """End-to-end timing: no Redis in the test environment."""
        from backend.app.workers.tasks import auto_tag_wardrobe_task

        start = time.time()
        try:
            auto_tag_wardrobe_task.delay(1)
        except Exception:
            pass
        elapsed = time.time() - start
        assert elapsed < 8.0, (
            f"enqueue took {elapsed:.1f}s with the broker down; it must fail "
            "fast so the caller can fall back to inline analysis")
