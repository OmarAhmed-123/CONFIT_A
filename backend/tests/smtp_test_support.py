"""Shared SMTP test support (task 24): a real RFC 5321 sink + helpers.

Kept in a normal module — not inside a test file — so several suites can share
one implementation without one test module importing another by bare path
(the deployment dependency manifest gate treats `test_*` imports as third-party
packages, which is exactly the blind spot it should not have).
"""
from __future__ import annotations

import email
import re
import socket
import threading
from typing import List

import pytest

from backend.app.core.config import settings


class LocalSMTPSink:
    """Minimal, real SMTP server speaking enough of RFC 5321 for delivery."""

    def __init__(self) -> None:
        self.messages: List[bytes] = []
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind(("127.0.0.1", 0))
        self._server.listen(5)
        self.port = self._server.getsockname()[1]
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._stop = False
        self._thread.start()

    def _serve(self) -> None:
        while not self._stop:
            try:
                conn, _ = self._server.accept()
            except OSError:
                return
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, conn: socket.socket) -> None:
        with conn:
            conn.sendall(b"220 local-sink ESMTP\r\n")
            buffer = b""
            in_data = False
            message = b""
            while True:
                chunk = conn.recv(4096)
                if not chunk:
                    return
                buffer += chunk
                while b"\r\n" in buffer:
                    line, buffer = buffer.split(b"\r\n", 1)
                    if in_data:
                        if line == b".":
                            in_data = False
                            self.messages.append(message)
                            message = b""
                            conn.sendall(b"250 OK queued\r\n")
                        else:
                            message += line + b"\r\n"
                        continue
                    upper = line.upper()
                    if upper.startswith(b"EHLO") or upper.startswith(b"HELO"):
                        conn.sendall(b"250-local-sink\r\n250 SIZE 10485760\r\n")
                    elif upper.startswith(b"MAIL FROM") or upper.startswith(b"RCPT TO"):
                        conn.sendall(b"250 OK\r\n")
                    elif upper.startswith(b"DATA"):
                        in_data = True
                        conn.sendall(b"354 End data with <CR><LF>.<CR><LF>\r\n")
                    elif upper.startswith(b"QUIT"):
                        conn.sendall(b"221 Bye\r\n")
                        return
                    else:
                        conn.sendall(b"250 OK\r\n")

    def close(self) -> None:
        self._stop = True
        try:
            self._server.close()
        except OSError:
            pass


@pytest.fixture()
def smtp_sink(monkeypatch):
    sink = LocalSMTPSink()
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "smtp", raising=False)
    monkeypatch.setattr(settings, "SMTP_HOST", "127.0.0.1", raising=False)
    monkeypatch.setattr(settings, "SMTP_PORT", sink.port, raising=False)
    monkeypatch.setattr(settings, "SMTP_USERNAME", None, raising=False)
    monkeypatch.setattr(settings, "SMTP_PASSWORD", None, raising=False)
    # Cleartext is allowed ONLY outside production (the config gate refuses
    # `none` in production); a loopback test MTA has no TLS certificate.
    monkeypatch.setattr(settings, "SMTP_TLS_MODE", "none", raising=False)
    monkeypatch.setattr(settings, "EMAIL_FROM_ADDRESS", "CONFIT <no-reply@confit.test>", raising=False)
    monkeypatch.setattr(settings, "FRONTEND_BASE_URL", "https://confit-a.vercel.app", raising=False)
    yield sink
    sink.close()


def _plain_text(raw: bytes) -> str:
    msg = email.message_from_bytes(raw)
    for part in msg.walk():
        if part.get_content_type() == "text/plain":
            payload = part.get_payload(decode=True) or b""
            return payload.decode("utf-8", errors="replace")
    return ""


def _token_from(text: str) -> str:
    match = re.search(r"token=([A-Za-z0-9_\-]+)", text)
    assert match, f"no one-time link in the delivered message: {text[:200]!r}"
    return match.group(1)


def _csrf(client: TestClient) -> dict:
    token = client.cookies.get("confit_csrf")
    return {"X-CSRF-Token": token} if token else {}


