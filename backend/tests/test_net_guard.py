"""The guard on server-side image fetching.

The catalogue import now accepts first-party image URLs (behind an owner flag).
That turns a string typed into a spreadsheet into an outbound HTTP request made
by the API process, which is the textbook setup for SSRF: point the "image" at
`169.254.169.254` and the response body is the instance's credentials, stored as
a product photo. These tests pin the refusal, including the redirect hop that a
naive `follow_redirects=True` would have taken for us.
"""
from __future__ import annotations

import socket

import pytest

from backend.app.core import net_guard
from backend.app.core.net_guard import UnsafeURLError, assert_public_http_url, safe_get


@pytest.fixture()
def public_dns(monkeypatch):
    def fake_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(net_guard.socket, "getaddrinfo", fake_getaddrinfo)


@pytest.mark.parametrize("url", [
    "http://169.254.169.254/latest/meta-data/iam/security-credentials/",
    "http://127.0.0.1/",
    "http://127.0.0.1:80/x.jpg",
    "http://10.0.0.5/internal.png",
    "http://192.168.1.10/x.png",
    "http://172.16.4.4/x.png",
    "http://[::1]/x.png",
    "http://[::ffff:127.0.0.1]/x.png",
    "http://0.0.0.0/x.png",
    "http://localhost/x.png",
    "http://redis.internal/x.png",
    "http://metadata.google.internal/computeMetadata/v1/",
    "file:///etc/passwd",
    "gopher://example.com/",
    "https://user:pass@example.com/x.jpg",
    "http://example.com:6379/",
    "",
])
def test_internal_and_malformed_urls_are_refused(url):
    with pytest.raises(UnsafeURLError):
        assert_public_http_url(url)


def test_a_name_resolving_to_a_private_address_is_refused(monkeypatch):
    """Split-horizon DNS: the name is public-looking, the answer is not."""
    def fake_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.1.2.3", 0))]

    monkeypatch.setattr(net_guard.socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(UnsafeURLError):
        assert_public_http_url("https://images.example.com/a.jpg")


def test_one_private_answer_among_public_ones_is_enough_to_refuse(monkeypatch):
    def fake_getaddrinfo(host, port, *args, **kwargs):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 0)),
        ]

    monkeypatch.setattr(net_guard.socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(UnsafeURLError):
        assert_public_http_url("https://mixed.example.com/a.jpg")


def test_an_unresolvable_host_is_refused_rather_than_allowed(monkeypatch):
    def boom(*args, **kwargs):
        raise socket.gaierror("no such host")

    monkeypatch.setattr(net_guard.socket, "getaddrinfo", boom)
    with pytest.raises(UnsafeURLError):
        assert_public_http_url("https://nothing.example.com/a.jpg")


def test_a_public_https_url_passes(public_dns):
    assert assert_public_http_url("https://images.pexels.com/photos/1/a.jpeg") == \
        "https://images.pexels.com/photos/1/a.jpeg"


def test_ipv4_mapped_ipv6_is_unwrapped_before_classification():
    # ::ffff:8.8.8.8 is public; the wrapper must not be what gets classified.
    with pytest.raises(UnsafeURLError):
        assert_public_http_url("http://[::ffff:169.254.169.254]/x")


class _Response:
    def __init__(self, status_code=200, content=b"", location=None):
        self.status_code = status_code
        self.content = content
        self.headers = {"location": location} if location else {}


def test_safe_get_follows_a_public_redirect(public_dns):
    seen = []

    def fetch(url):
        seen.append(url)
        if len(seen) == 1:
            return _Response(302, location="https://images.example.com/real.jpg")
        return _Response(200, content=b"\xff\xd8jpeg")

    assert safe_get("https://images.example.com/start.jpg", fetch=fetch) == b"\xff\xd8jpeg"
    assert seen == ["https://images.example.com/start.jpg",
                    "https://images.example.com/real.jpg"]


def test_safe_get_refuses_a_redirect_into_the_private_network(public_dns):
    """The hop httpx would have taken silently with follow_redirects=True."""
    calls = []

    def fetch(url):
        calls.append(url)
        return _Response(302, location="http://169.254.169.254/latest/meta-data/")

    with pytest.raises(UnsafeURLError):
        safe_get("https://images.example.com/start.jpg", fetch=fetch)
    assert calls == ["https://images.example.com/start.jpg"], (
        "the private address was requested before it was checked"
    )


def test_safe_get_gives_up_on_a_redirect_loop(public_dns):
    def fetch(url):
        return _Response(302, location="/again")

    with pytest.raises(UnsafeURLError):
        safe_get("https://images.example.com/loop.jpg", fetch=fetch)


def test_safe_get_reports_an_upstream_error(public_dns):
    with pytest.raises(UnsafeURLError):
        safe_get("https://images.example.com/missing.jpg",
                 fetch=lambda url: _Response(404))
