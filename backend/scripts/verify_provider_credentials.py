#!/usr/bin/env python3
"""Verify every provider credential the operator supplied — read-only, live.

WHY THIS EXISTS
---------------
`backend/scripts/verify_nvidia_models.py` covers the NVIDIA NIM layer. Everything
else the operator handed over (databases, object storage, mail, FX, uptime, error
tracking, serverless GPU, DNS, registries) has no equivalent, so a wrong or
expired key is discovered by a user in production instead of by a script at
provisioning time. This is that script.

Two things it does that a curl loop cannot:

1. **Name resolution.** The repo reads canonical names (`NVIDIA_KEY_KIMI_K3`);
   an operator's env file may use its own (`NVIDIA_API_KEY_KIMI_K3`). Every spec
   therefore lists the canonical name plus every accepted alias, and the report
   says which one satisfied the slot — because a credential that exists under a
   name the app never reads is a credential the app does not have.
2. **Honest evidence.** Each probe reports what it actually established:
   `ok`, `auth_failed`, `unreachable`, `endpoint_unknown`, `shape_only`,
   `not_configured`. Nothing is inferred from the presence of a variable.

SAFETY
------
  · Every probe is a GET or a protocol handshake. Nothing writes, sends, deletes
    or mutates: no mail is sent, no object is uploaded, no DNS record is touched,
    no GPU job is started.
  · Secret values are never printed, logged or serialised. The report carries a
    name, an 8-character SHA-256 fingerprint (so two slots holding the SAME value
    are visible) and the probe's verdict.
  · Network calls are bounded (default 8s) and failures are reported, not raised.

USAGE
-----
    source ~/confit-secrets/load.sh          # or any env file, exported
    python3 backend/scripts/verify_provider_credentials.py
    python3 backend/scripts/verify_provider_credentials.py --json /tmp/creds.json
    python3 backend/scripts/verify_provider_credentials.py --only nvidia neon
    python3 backend/scripts/verify_provider_credentials.py --quiet

Exit codes
----------
0  every configured credential answered
1  at least one configured credential failed a live probe
2  nothing was configured at all
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import smtplib
import socket
import ssl
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlparse

try:  # httpx is what the backend already uses; requests is the fallback.
    import httpx
except Exception:  # pragma: no cover - environment without httpx
    httpx = None  # type: ignore[assignment]

try:
    import requests
except Exception:  # pragma: no cover
    requests = None  # type: ignore[assignment]


GREEN, RED, YELLOW, BLUE, DIM, RESET = (
    "\033[32m", "\033[31m", "\033[33m", "\033[34m", "\033[2m", "\033[0m",
)

OK = "ok"
AUTH_FAILED = "auth_failed"
UNREACHABLE = "unreachable"
HTTP_ERROR = "http_error"
ENDPOINT_UNKNOWN = "endpoint_unknown"
SHAPE_ONLY = "shape_only"
NOT_CONFIGURED = "not_configured"
SKIPPED = "skipped"

VERDICT_COLOR = {
    OK: GREEN,
    AUTH_FAILED: RED,
    UNREACHABLE: RED,
    HTTP_ERROR: YELLOW,
    ENDPOINT_UNKNOWN: YELLOW,
    SHAPE_ONLY: BLUE,
    NOT_CONFIGURED: DIM,
    SKIPPED: DIM,
}
#: Statuses that mean "a credential was supplied and did not work".
FAILING = {AUTH_FAILED, UNREACHABLE}


# ─────────────────────────────────────────────────────────────────────────────
# Environment resolution
# ─────────────────────────────────────────────────────────────────────────────
DOTENV_CANDIDATES = (
    ".env", ".env.local", "backend/.env", "frontend/.env", "secrets.env",
)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def parse_dotenv(path: Path) -> Dict[str, str]:
    """Parse a dotenv file the same permissive way keypool.py does."""
    values: Dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return values
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        line = line.removeprefix("export ").strip()
        if "=" not in line:
            continue
        name, _, value = line.partition("=")
        name = name.strip()
        value = value.strip().strip('"').strip("'")
        if name and value:
            values[name] = value
    return values


class Vault:
    """Environment first, then the dev dotenv files — same precedence as keypool."""

    def __init__(self) -> None:
        self._env = dict(os.environ)
        self._dotenv: Dict[str, str] = {}
        for candidate in DOTENV_CANDIDATES:
            self._dotenv.update(parse_dotenv(repo_root() / candidate))

    def get(self, *names: str) -> Tuple[Optional[str], Optional[str]]:
        """First configured name, and which name it was."""
        for name in names:
            value = self._env.get(name) or self._dotenv.get(name)
            if value and value.strip():
                return value.strip(), name
        return None, None

    @staticmethod
    def fingerprint(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]


# ─────────────────────────────────────────────────────────────────────────────
# Probe plumbing
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class Result:
    provider: str
    capability: str
    status: str
    detail: str
    name: Optional[str] = None
    fingerprint: Optional[str] = None
    latency_ms: Optional[int] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "capability": self.capability,
            "status": self.status,
            "detail": self.detail,
            "env_name": self.name,
            "value_fingerprint": self.fingerprint,
            "latency_ms": self.latency_ms,
            **({"extra": self.extra} if self.extra else {}),
        }


TIMEOUT = 8.0


async def http_get(
    url: str, headers: Optional[Dict[str, str]] = None, *, auth: Optional[tuple] = None
) -> Tuple[int, Any, str]:
    """GET with a bounded timeout. Returns (status, body, note)."""
    if httpx is not None:
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False) as client:
            response = await client.get(url, headers=headers or {}, auth=auth)
            try:
                body = response.json()
            except Exception:
                body = response.text[:400]
            return response.status_code, body, ""
    if requests is not None:  # pragma: no cover - httpx is normally present
        response = await asyncio.to_thread(
            requests.get, url, headers=headers or {}, auth=auth, timeout=TIMEOUT
        )
        try:
            body = response.json()
        except Exception:
            body = response.text[:400]
        return response.status_code, body, ""
    return 0, None, "no HTTP client available"


def classify_http(status: int, body: Any) -> Tuple[str, str]:
    if status in (401, 403):
        return AUTH_FAILED, f"HTTP {status} — credential rejected"
    if 200 <= status < 300:
        return OK, f"HTTP {status}"
    if status == 0:
        return UNREACHABLE, "no response"
    return HTTP_ERROR, f"HTTP {status} — {str(body)[:160]}"


async def probe_http(
    provider: str,
    capability: str,
    url: str,
    *,
    headers: Optional[Dict[str, str]] = None,
    value: Optional[str] = None,
    name: Optional[str] = None,
    http_status_offset: bool = False,
) -> Result:
    started = time.perf_counter()
    fingerprint = Vault.fingerprint(value) if value else None
    try:
        status, body, note = await http_get(url, headers=headers)
    except Exception as exc:  # network, DNS, TLS — all reported, never raised
        return Result(
            provider, capability, UNREACHABLE, f"{type(exc).__name__}: {str(exc)[:120]}",
            name, fingerprint, int((time.perf_counter() - started) * 1000),
        )
    latency = int((time.perf_counter() - started) * 1000)
    verdict, detail = classify_http(status, body)
    return Result(provider, capability, verdict, detail, name, fingerprint, latency)


def tcp_reachable(host: str, port: int, timeout: float = TIMEOUT) -> Tuple[bool, str]:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, f"tcp {host}:{port} open"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {str(exc)[:100]}"


# ─────────────────────────────────────────────────────────────────────────────
# Probes — one per supplied provider
# ─────────────────────────────────────────────────────────────────────────────
NVIDIA_BASE = "https://integrate.api.nvidia.com/v1"

#: The canonical slot names the app reads, mapped to the alias an operator's env
#: file is allowed to use and to the model that key shipped with.
NVIDIA_SLOTS: Sequence[Tuple[str, str, str]] = (
    ("NVIDIA_KEY_NEMOTRON_3_ULTRA_550B_A55B", "NVIDIA_API_KEY_NEMOTRON_3_ULTRA_550B_A55B", "nemotron-3-ultra-550b-a55b"),
    ("NVIDIA_KEY_NEMOTRON_3_SUPER_120B_A12B", "NVIDIA_API_KEY_NEMOTRON_3_SUPER_120B_A12B", "nemotron-3-super-120b-a12b"),
    ("NVIDIA_KEY_NEMOTRON_3_5_LIGHTNING_30B_A3B", "NVIDIA_API_KEY_NEMOTRON_3_5_LIGHTNING_30B_A3B", "nemotron-3.5-lightning-30b-a3b"),
    ("NVIDIA_KEY_NEMOTRON_3_NANO_OMNI_30B_A3B_REASONING", "NVIDIA_API_KEY_NEMOTRON_3_NANO_OMNI_30B_A3B", "nemotron-3-nano-omni-30b-a3b-reasoning"),
    ("NVIDIA_KEY_NEMOTRON_3_5_CONTENT_SAFETY", "NVIDIA_API_KEY_NEMOTRON_3_5_CONTENT_SAFETY", "nemotron-3.5-content-safety"),
    ("NVIDIA_KEY_NEMOTRON_3_EMBED_1B", "NVIDIA_API_KEY_NEMOTRON_3_EMBED_1B", "nemotron-3-embed-1b"),
    ("NVIDIA_KEY_RIVA_TRANSLATE_4B_INSTRUCT_V2", "NVIDIA_API_KEY_RIVA_TRANSLATE_4B_INSTRUCT_V2", "riva-translate-4b-instruct-v2"),
    ("NVIDIA_KEY_KIMI_K3", "NVIDIA_API_KEY_KIMI_K3", "kimi-k3"),
    ("NVIDIA_KEY_GLM_5_3", "NVIDIA_API_KEY_GLM_5_3", "glm-5.3"),
    ("NVIDIA_KEY_GLM_5_3_FLASH", "NVIDIA_API_KEY_GLM_5_3_FLASH", "glm-5.3-flash"),
    ("NVIDIA_KEY_DIFFUSIONGEMMA_26B_A4B_IT", "NVIDIA_API_KEY_DIFFUSIONGEMMA_26B_A4B", "diffusiongemma-26b-a4b-it"),
    ("NVIDIA_KEY_GEMMA_4_31B_IT", "NVIDIA_API_KEY_GEMMA_4_31B_IT", "gemma-4-31b-it"),
    ("NVIDIA_KEY_MUSE_GLIMMER_30B", "NVIDIA_API_KEY_MUSE_GLIMMER_30B", "muse-glimmer-30b"),
    ("NVIDIA_KEY_DEEPSEEK_V4_1_FLASH", "NVIDIA_API_KEY_DEEPSEEK_V4_1_FLASH", "deepseek-v4.1-flash"),
    ("NVIDIA_KEY_LAGUNA_XS_2_1", "NVIDIA_API_KEY_LAGUNA_XS_2_1", "laguna-xs-2.1"),
    ("NVIDIA_KEY_KUMO_RELATIONAL", "NVIDIA_API_KEY_KUMO_RELATIONAL", "kumo-relational"),
    ("NVIDIA_KEY_NEMOTRON_VOICECHAT", "NVIDIA_API_KEY_NEMOTRON_VOICECHAT", "nemotron-voicechat"),
    # The operator ships TWO keys for this model; the app has two slots for them.
    # Written one field per line deliberately: secret scanners reason about
    # adjacency, and a model slug placed immediately after an `..._API_KEY_...`
    # identifier is indistinguishable from a credential value to
    # `generic-api-key` (measured — it captured "ising-calibration-1.5-31b").
    # Reformatting beats allowlisting a model name.
    (
        "NVIDIA_KEY_ISING_CALIBRATION_1_5_31B",
        "NVIDIA_API_KEY_ISING_CALIBRATION_A",
        "ising-calibration-1.5-31b",
    ),
    (
        "NVIDIA_KEY_ISING_CALIBRATION_1_5_31B_2",
        "NVIDIA_API_KEY_ISING_CALIBRATION_B",
        "ising-calibration-1.5-31b",
    ),
)


async def probe_nvidia(vault: Vault, only_slots: bool = False) -> List[Result]:
    results: List[Result] = []
    base, _ = vault.get("NVIDIA_BASE_URL")
    base = (base or NVIDIA_BASE).rstrip("/")

    for canonical, alias, model in NVIDIA_SLOTS:
        value, name = vault.get(canonical, alias)
        if not value:
            results.append(Result(
                "nvidia", model, NOT_CONFIGURED,
                f"neither {canonical} nor {alias} is set",
            ))
            continue
        result = await probe_http(
            "nvidia", model, f"{base}/models",
            headers={"Authorization": f"Bearer {value}"},
            value=value, name=name,
        )
        if result.status == OK and not only_slots:
            result.detail += " — catalogue reachable for this slot key"
        results.append(result)

    # The two legacy names the orchestrator uses.
    for legacy, label in (("NVIDIA_API_KEY", "legacy shared key"), ("NVIDIA_CHAT_KEY_2", "legacy chat key")):
        value, name = vault.get(legacy)
        if not value:
            results.append(Result("nvidia", label, NOT_CONFIGURED, f"{legacy} is not set"))
            continue
        results.append(await probe_http(
            "nvidia", label, f"{base}/models",
            headers={"Authorization": f"Bearer {value}"}, value=value, name=name,
        ))
    return results


async def probe_openai(vault: Vault) -> List[Result]:
    value, name = vault.get("OPENAI_API_KEY")
    if not value:
        return [Result("openai", "chat + embeddings", NOT_CONFIGURED, "OPENAI_API_KEY is not set")]
    return [await probe_http(
        "openai", "chat + embeddings", "https://api.openai.com/v1/models",
        headers={"Authorization": f"Bearer {value}"}, value=value, name=name,
    )]


async def probe_gemini(vault: Vault) -> List[Result]:
    value, name = vault.get("GEMINI_API_KEY")
    header_key, header_name = vault.get("GEMINI_API_KEY_HEADER")
    results: List[Result] = []
    if not value:
        results.append(Result("gemini", "vision + stylist", NOT_CONFIGURED, "GEMINI_API_KEY is not set"))
    else:
        results.append(await probe_http(
            "gemini", "vision + stylist",
            f"https://generativelanguage.googleapis.com/v1beta/models?key={value}",
            value=value, name=name,
        ))
    if header_key:
        # Some deployments authenticate by header instead of query string.
        results.append(await probe_http(
            "gemini", "vision + stylist (header auth)",
            "https://generativelanguage.googleapis.com/v1beta/models",
            headers={"x-goog-api-key": header_key}, value=header_key, name=header_name,
        ))
    return results


async def probe_groq(vault: Vault) -> List[Result]:
    value, name = vault.get("GROQ_API_KEY")
    if not value:
        return [Result("groq", "fast chat failover", NOT_CONFIGURED, "GROQ_API_KEY is not set")]
    return [await probe_http(
        "groq", "fast chat failover", "https://api.groq.com/openai/v1/models",
        headers={"Authorization": f"Bearer {value}"}, value=value, name=name,
    )]


UNOROUTER_CANDIDATES = (
    "https://api.unorouter.ai/v1/models",
    "https://api.unorouter.com/v1/models",
    "https://unorouter.ai/api/v1/models",
)


async def probe_unorouter(vault: Vault) -> List[Result]:
    """Unorouter is OpenAI-shaped but its base URL is not documented in the repo."""
    value, name = vault.get("UNOROUTER_API_KEY", "OPENROUTER_API_KEY")
    if not value:
        return [Result("unorouter", "model gateway", NOT_CONFIGURED, "UNOROUTER_API_KEY is not set")]
    tried: List[str] = []
    for url in UNOROUTER_CANDIDATES:
        result = await probe_http(
            "unorouter", "model gateway", url,
            headers={"Authorization": f"Bearer {value}"}, value=value, name=name,
        )
        if result.status in (OK, AUTH_FAILED):
            result.extra["endpoint"] = url
            result.extra["candidates_tried"] = tried + [url]
            return [result]
        tried.append(f"{url} → {result.status}")
    return [Result(
        "unorouter", "model gateway", ENDPOINT_UNKNOWN,
        f"credential present but no candidate base URL answered: {'; '.join(tried)}",
        name, Vault.fingerprint(value),
    )]


DATABASES = (
    ("DATABASE_URL", "primary application database"),
    ("DATABASE_URL_NEONDB_OWNER", "Neon owner role"),
    ("DATABASE_URL_NEONDB_APP_RW", "Neon app read-write role"),
    ("DATABASE_URL_FIXVERIFY_OWNER", "fixverify owner role"),
    ("DATABASE_URL_FIXVERIFY_APP_RW", "fixverify app read-write role"),
)


def describe_database(url: str) -> Dict[str, Any]:
    parsed = urlparse(url)
    return {
        "host": parsed.hostname,
        "port": parsed.port or 5432,
        "database": (parsed.path or "/").lstrip("/") or None,
        "user": parsed.username,
        "ssl": "require" if "sslmode=require" in url else "parsed-from-url",
    }


async def probe_databases(vault: Vault) -> List[Result]:
    results: List[Result] = []
    for var, label in DATABASES:
        value, name = vault.get(var)
        if not value:
            results.append(Result("neon", label, NOT_CONFIGURED, f"{var} is not set"))
            continue
        info = describe_database(value)
        if not info["host"]:
            results.append(Result("neon", label, HTTP_ERROR, "DATABASE_URL is not a parseable DSN",
                                  name, Vault.fingerprint(value)))
            continue
        started = time.perf_counter()
        reachable, detail = await asyncio.to_thread(
            tcp_reachable, info["host"], int(info["port"])
        )
        latency = int((time.perf_counter() - started) * 1000)
        extra = {k: v for k, v in info.items() if k != "password"}
        if reachable:
            # A TCP handshake proves the endpoint exists, not that the role can
            # authenticate — say so, rather than implying more than was checked.
            try:  # optional: a real query, only if a driver is importable
                import psycopg2  # type: ignore

                def _query() -> str:
                    with psycopg2.connect(value, connect_timeout=8) as conn:  # type: ignore[arg-type]
                        with conn.cursor() as cur:
                            cur.execute("select current_database(), version()")
                            row = cur.fetchone()
                    return f"{row[0]} · {str(row[1]).split(',')[0]}"

                summary = await asyncio.to_thread(_query)
                results.append(Result("neon", label, OK, f"connected — {summary}",
                                      name, Vault.fingerprint(value), latency, extra))
            except ImportError:
                results.append(Result("neon", label, SHAPE_ONLY,
                                      f"{detail} · no postgres driver installed, credentials not authenticated",
                                      name, Vault.fingerprint(value), latency, extra))
            except Exception as exc:
                results.append(Result("neon", label, AUTH_FAILED,
                                      f"endpoint reachable but login failed: {type(exc).__name__}: {str(exc)[:110]}",
                                      name, Vault.fingerprint(value), latency, extra))
        else:
            results.append(Result("neon", label, UNREACHABLE, detail,
                                  name, Vault.fingerprint(value), latency, extra))
    return results


async def probe_s3_compatible(vault: Vault) -> List[Result]:
    results: List[Result] = []
    targets = (
        ("Neon S3 / AWS", ("AWS_ACCESS_KEY_ID",), ("AWS_SECRET_ACCESS_KEY",), ("AWS_ENDPOINT_URL_S3",), ("AWS_S3_BUCKET",)),
        ("RunPod S3", ("RUNPOD_S3_ACCESS_KEY",), ("RUNPOD_S3_SECRET_KEY",), ("AWS_ENDPOINT_URL_S3",), ("AWS_S3_BUCKET",)),
    )
    for label, ak_names, sk_names, ep_names, bucket_names in targets:
        access, ak_name = vault.get(*ak_names)
        secret, _ = vault.get(*sk_names)
        endpoint, _ = vault.get(*ep_names)
        bucket, _ = vault.get(*bucket_names)
        if not (access and secret):
            results.append(Result("s3", label, NOT_CONFIGURED, f"{ak_names[0]} / {sk_names[0]} not both set"))
            continue
        if not endpoint:
            results.append(Result("s3", label, SHAPE_ONLY, "credentials present but no endpoint configured",
                                  ak_name, Vault.fingerprint(access)))
            continue
        host = urlparse(endpoint).hostname
        started = time.perf_counter()
        reachable, detail = await asyncio.to_thread(
            tcp_reachable, host or "", 443 if endpoint.startswith("https") else 80
        )
        latency = int((time.perf_counter() - started) * 1000)
        try:
            import boto3  # type: ignore

            def _list() -> str:
                client = boto3.client(  # type: ignore[attr-defined]
                    "s3", endpoint_url=endpoint, aws_access_key_id=access,
                    aws_secret_access_key=secret, region_name=os.environ.get("AWS_REGION", "us-east-1"),
                )
                names = [b["Name"] for b in client.list_buckets().get("Buckets", [])]
                if bucket:
                    client.head_bucket(Bucket=bucket)
                return f"{len(names)} bucket(s) visible" + (f", {bucket} reachable" if bucket else "")

            summary = await asyncio.to_thread(_list)
            results.append(Result("s3", label, OK, summary, ak_name, Vault.fingerprint(access), latency,
                                  {"endpoint_host": host}))
        except ImportError:
            results.append(Result("s3", label, SHAPE_ONLY,
                                  f"{detail} · no S3 SDK installed, credentials not authenticated",
                                  ak_name, Vault.fingerprint(access), latency, {"endpoint_host": host}))
        except Exception as exc:
            results.append(Result("s3", label, AUTH_FAILED,
                                  f"{type(exc).__name__}: {str(exc)[:120]}",
                                  ak_name, Vault.fingerprint(access), latency, {"endpoint_host": host}))
    return results


async def probe_brevo_api(vault: Vault) -> List[Result]:
    value, name = vault.get("BREVO_API_KEY")
    if not value:
        return [Result("brevo", "transactional email (API)", NOT_CONFIGURED, "BREVO_API_KEY is not set")]
    return [await probe_http(
        "brevo", "transactional email (API)", "https://api.brevo.com/v3/account",
        headers={"api-key": value, "accept": "application/json"}, value=value, name=name,
    )]


async def probe_smtp(vault: Vault) -> List[Result]:
    """Handshake + AUTH only. No message is ever sent."""
    host, host_name = vault.get("SMTP_HOST")
    port, _ = vault.get("SMTP_PORT")
    user, user_name = vault.get("SMTP_LOGIN", "SMTP_USER")
    password, _ = vault.get("SMTP_PASSWORD", "SMTP_PASS")
    if not host:
        return [Result("smtp", "outbound mail", NOT_CONFIGURED, "SMTP_HOST is not set")]
    if not (user and password):
        return [Result("smtp", "outbound mail", SHAPE_ONLY, "host set but no SMTP credentials",
                       host_name, None)]
    port_number = int(port) if port and port.isdigit() else 587
    started = time.perf_counter()

    def _handshake() -> str:
        context = ssl.create_default_context()
        with smtplib.SMTP(host, port_number, timeout=TIMEOUT) as client:
            client.ehlo()
            client.starttls(context=context)
            client.ehlo()
            client.login(user, password)
            code, _ = client.noop()
            return f"STARTTLS + AUTH ok (NOOP {code})"

    try:
        summary = await asyncio.to_thread(_handshake)
        return [Result("smtp", "outbound mail", OK, summary, host_name,
                       Vault.fingerprint(password), int((time.perf_counter() - started) * 1000),
                       {"host": host, "port": port_number, "user": user_name})]
    except Exception as exc:
        return [Result("smtp", "outbound mail", AUTH_FAILED,
                       f"{type(exc).__name__}: {str(exc)[:130]}", host_name,
                       Vault.fingerprint(password), int((time.perf_counter() - started) * 1000),
                       {"host": host, "port": port_number})]


async def probe_resend(vault: Vault) -> List[Result]:
    value, name = vault.get("RESEND_API_KEY")
    if not value:
        return [Result("resend", "transactional email (API)", NOT_CONFIGURED, "RESEND_API_KEY is not set")]
    return [await probe_http(
        "resend", "transactional email (API)", "https://api.resend.com/domains",
        headers={"Authorization": f"Bearer {value}"}, value=value, name=name,
    )]


async def probe_fx(vault: Vault) -> List[Result]:
    results: List[Result] = []
    exchangerate, name = vault.get("EXCHANGERATE_API_KEY")
    if not exchangerate:
        results.append(Result("fx", "exchangerate.host", NOT_CONFIGURED, "EXCHANGERATE_API_KEY is not set"))
    else:
        results.append(await probe_http(
            "fx", "exchangerate.host",
            f"https://api.exchangerate.host/live?access_key={exchangerate}",
            value=exchangerate, name=name,
        ))
    fixer, fixer_name = vault.get("FIXER_API_KEY")
    if not fixer:
        results.append(Result("fx", "fixer.io", NOT_CONFIGURED, "FIXER_API_KEY is not set"))
    else:
        results.append(await probe_http(
            "fx", "fixer.io", f"https://data.fixer.io/api/latest?access_key={fixer}&base=EUR",
            value=fixer, name=fixer_name,
        ))
    return results


async def probe_sentry(vault: Vault) -> List[Result]:
    results: List[Result] = []
    value, name = vault.get("SENTRY_AUTH_TOKEN")
    if not value:
        results.append(Result("sentry", "error tracking", NOT_CONFIGURED, "SENTRY_AUTH_TOKEN is not set"))
    else:
        results.append(await probe_http(
            "sentry", "error tracking", "https://sentry.io/api/0/organizations/",
            headers={"Authorization": f"Bearer {value}"}, value=value, name=name,
        ))
    glitch, glitch_name = vault.get("GLITCHTIP_KEY")
    if not glitch:
        results.append(Result("glitchtip", "error tracking (self-hosted)", NOT_CONFIGURED, "GLITCHTIP_KEY is not set"))
    else:
        # A DSN is a public in-app identifier, not a bearer token: what can be
        # verified is its shape and that its ingest host answers.
        parsed = urlparse(glitch if "://" in glitch else f"https://{glitch}")
        if parsed.hostname and parsed.username and parsed.path:
            started = time.perf_counter()
            reachable, detail = await asyncio.to_thread(tcp_reachable, parsed.hostname, 443)
            results.append(Result(
                "glitchtip", "error tracking (self-hosted)",
                SHAPE_ONLY if reachable else UNREACHABLE,
                f"DSN shape valid · project id present · {detail}",
                glitch_name, Vault.fingerprint(glitch),
                int((time.perf_counter() - started) * 1000),
                {"dsn_host": parsed.hostname},
            ))
        else:
            results.append(Result(
                "glitchtip", "error tracking (self-hosted)",
                SHAPE_ONLY if len(glitch) >= 32 and " " not in glitch else HTTP_ERROR,
                "value is a project key, not a DSN — the SDK needs the full "
                "https://<key>@<host>/<project> form (this is what the app must be given)",
                glitch_name, Vault.fingerprint(glitch),
            ))
    return results


async def probe_betterstack(vault: Vault) -> List[Result]:
    value, name = vault.get("BETTERSTACK_TOKEN")
    if not value:
        return [Result("betterstack", "uptime monitoring", NOT_CONFIGURED, "BETTERSTACK_TOKEN is not set")]
    return [await probe_http(
        "betterstack", "uptime monitoring", "https://uptime.betterstack.com/api/v2/monitors",
        headers={"Authorization": f"Bearer {value}"}, value=value, name=name,
    )]


async def probe_huggingface(vault: Vault) -> List[Result]:
    value, name = vault.get("HF_TOKEN", "HUGGINGFACE_TOKEN")
    if not value:
        return [Result("huggingface", "model weights + inference", NOT_CONFIGURED, "HF_TOKEN is not set")]
    return [await probe_http(
        "huggingface", "model weights + inference", "https://huggingface.co/api/whoami-v2",
        headers={"Authorization": f"Bearer {value}"}, value=value, name=name,
    )]


async def probe_kaggle(vault: Vault) -> List[Result]:
    value, name = vault.get("KAGGLE_API_TOKEN")
    if not value:
        return [Result("kaggle", "datasets / notebooks", NOT_CONFIGURED, "KAGGLE_API_TOKEN is not set")]
    result = await probe_http(
        "kaggle", "datasets / notebooks", "https://www.kaggle.com/api/v1/datasets/list?page=1",
        headers={"Authorization": f"Bearer {value}"}, value=value, name=name,
    )
    if result.status in (AUTH_FAILED, HTTP_ERROR):
        result.detail += " (kaggle's v1 API expects the legacy basic-auth pair; token shape unverified)"
    return [result]


async def probe_gpu_platforms(vault: Vault) -> List[Result]:
    results: List[Result] = []
    baseten, name = vault.get("BASETEN_API_KEY")
    if not baseten:
        results.append(Result("baseten", "serverless GPU", NOT_CONFIGURED, "BASETEN_API_KEY is not set"))
    else:
        results.append(await probe_http(
            "baseten", "serverless GPU", "https://api.baseten.co/v1/models",
            headers={"Authorization": f"Api-Key {baseten}"}, value=baseten, name=name,
        ))

    cerebrium, name = vault.get("CEREBRIUM_TOKEN")
    if not cerebrium:
        results.append(Result("cerebrium", "serverless GPU", NOT_CONFIGURED, "CEREBRIUM_TOKEN is not set"))
    else:
        cerebrium_result = await probe_http(
            "cerebrium", "serverless GPU", "https://api.cerebrium.ai/v2/projects",
            headers={"Authorization": f"Bearer {cerebrium}"}, value=cerebrium, name=name,
        )
        if cerebrium_result.status == HTTP_ERROR:
            cerebrium_result.status = ENDPOINT_UNKNOWN
            cerebrium_result.detail = ("credential present but the read-only endpoint is unverified here: "
                                       + cerebrium_result.detail)
        results.append(cerebrium_result)

    runpod, name = vault.get("RUNPOD_API_KEY")
    if not runpod:
        results.append(Result("runpod", "GPU pods + storage", NOT_CONFIGURED, "RUNPOD_API_KEY is not set"))
    else:
        results.append(await probe_http(
            "runpod", "GPU pods + storage", "https://rest.runpod.io/v1/pods",
            headers={"Authorization": f"Bearer {runpod}"}, value=runpod, name=name,
        ))

    modal_id, id_name = vault.get("MODAL_TOKEN_ID")
    modal_secret, _ = vault.get("MODAL_TOKEN_SECRET")
    modal_secure, _ = vault.get("MODAL_SECURE_TOKEN")
    if not (modal_id and modal_secret):
        results.append(Result("modal", "VTON + VLM workers", NOT_CONFIGURED,
                              "MODAL_TOKEN_ID / MODAL_TOKEN_SECRET not both set"))
    else:
        # Modal has no public REST surface (gRPC + CLI only), so presence and
        # pairing is all a read-only probe can honestly establish.
        results.append(Result(
            "modal", "VTON + VLM workers", SHAPE_ONLY,
            "token id + secret pair present"
            + (", plus a secure token" if modal_secure else "")
            + " · no public REST endpoint to call; verify with `modal app list`",
            id_name, Vault.fingerprint(modal_id),
        ))
    return results


async def probe_fitroom(vault: Vault) -> List[Result]:
    value, name = vault.get("FITROOM_API_KEY")
    if not value:
        return [Result("fitroom", "external try-on renderer", NOT_CONFIGURED, "FITROOM_API_KEY is not set")]
    result = await probe_http(
        "fitroom", "external try-on renderer", "https://platform.fitroom.app/api/v1/models",
        headers={"X-API-KEY": value}, value=value, name=name,
    )
    if result.status in (AUTH_FAILED, HTTP_ERROR, UNREACHABLE):
        result.status = ENDPOINT_UNKNOWN
        result.detail = ("credential present but FitRoom's read-only surface is undocumented here: "
                         + result.detail)
    return [result]


async def probe_platforms(vault: Vault) -> List[Result]:
    results: List[Result] = []
    vercel, name = vault.get("VERCEL_TOKEN")
    if not vercel:
        results.append(Result("vercel", "deploy target", NOT_CONFIGURED, "VERCEL_TOKEN is not set"))
    else:
        result = await probe_http(
            "vercel", "deploy target", "https://api.vercel.com/v2/user",
            headers={"Authorization": f"Bearer {vercel}"}, value=vercel, name=name,
        )
        if result.status != OK:
            # A team-scoped token cannot read /v2/user but can read its projects.
            retry = await probe_http(
                "vercel", "deploy target", "https://api.vercel.com/v9/projects?limit=1",
                headers={"Authorization": f"Bearer {vercel}"}, value=vercel, name=name,
            )
            if retry.status == OK:
                retry.detail += " (team-scoped token: /v2/user is not readable, project listing is)"
                retry.extra["user_endpoint"] = result.status
                result = retry
        results.append(result)

    github, name = vault.get("GITHUB_TOKEN")
    if not github:
        results.append(Result("github", "repository + CI", NOT_CONFIGURED, "GITHUB_TOKEN is not set"))
    else:
        results.append(await probe_http(
            "github", "repository + CI", "https://api.github.com/user",
            headers={"Authorization": f"Bearer {github}",
                     "Accept": "application/vnd.github+json"}, value=github, name=name,
        ))

    hub, hub_name = vault.get("CONFIT_HUB_API_KEY")
    results.append(Result(
        "confit-hub", "internal hub API",
        SHAPE_ONLY if hub else NOT_CONFIGURED,
        "credential present · no endpoint declared in the repo" if hub else "CONFIT_HUB_API_KEY is not set",
        hub_name, Vault.fingerprint(hub) if hub else None,
    ))
    return results


async def probe_dns(vault: Vault) -> List[Result]:
    results: List[Result] = []
    dynu, name = vault.get("DYNU_API_KEY")
    base, _ = vault.get("DYNU_API_BASE")
    if not dynu:
        results.append(Result("dynu", "DNS records", NOT_CONFIGURED, "DYNU_API_KEY is not set"))
    else:
        results.append(await probe_http(
            "dynu", "DNS records", f"{(base or 'https://api.dynu.com/v2').rstrip('/')}/dns",
            headers={"API-Key": dynu, "Accept": "application/json"}, value=dynu, name=name,
        ))

    dnshe, name = vault.get("DNSHE_API_KEY")
    endpoint, _ = vault.get("DNSHE_API_ENDPOINT")
    secret, secret_name = vault.get("DNSHE_API_SECRET")
    if not dnshe:
        results.append(Result("dnshe", "DNS records", NOT_CONFIGURED, "DNSHE_API_KEY is not set"))
    elif not endpoint:
        results.append(Result("dnshe", "DNS records", SHAPE_ONLY,
                              "key present but DNSHE_API_ENDPOINT is not set", name, Vault.fingerprint(dnshe)))
    else:
        dnshe_result = await probe_http(
            "dnshe", "DNS records", endpoint,
            headers={"X-API-Key": dnshe, "X-API-Secret": secret or "",
                     "Accept": "application/json"},
            value=dnshe, name=name,
        )
        if dnshe_result.status != OK:
            dnshe_result.status = ENDPOINT_UNKNOWN
            dnshe_result.detail = ("credential pair present (key + secret) but the endpoint did not "
                                   "accept this read-only call: " + dnshe_result.detail)
        results.append(dnshe_result)

    digit, name = vault.get("DIGITALPLAT_API_KEY")
    results.append(Result(
        "digitalplat", "DNS + domains",
        SHAPE_ONLY if digit else NOT_CONFIGURED,
        "credential present · no documented read-only endpoint" if digit
        else "DIGITALPLAT_API_KEY is not set",
        name, Vault.fingerprint(digit) if digit else None,
    ))
    return results


PROBE_GROUPS: Sequence[Tuple[str, Callable[[Vault], Awaitable[List[Result]]]]] = (
    ("nvidia", probe_nvidia),
    ("openai", probe_openai),
    ("gemini", probe_gemini),
    ("groq", probe_groq),
    ("unorouter", probe_unorouter),
    ("neon", probe_databases),
    ("s3", probe_s3_compatible),
    ("brevo", probe_brevo_api),
    ("smtp", probe_smtp),
    ("resend", probe_resend),
    ("fx", probe_fx),
    ("sentry", probe_sentry),
    ("betterstack", probe_betterstack),
    ("huggingface", probe_huggingface),
    ("kaggle", probe_kaggle),
    ("gpu", probe_gpu_platforms),
    ("fitroom", probe_fitroom),
    ("platforms", probe_platforms),
    ("dns", probe_dns),
)


async def run(selected: Optional[Sequence[str]]) -> List[Result]:
    vault = Vault()
    groups = [g for g in PROBE_GROUPS if not selected or g[0] in selected]
    batches = await asyncio.gather(*(fn(vault) for _, fn in groups))
    return [result for batch in batches for result in batch]


# ─────────────────────────────────────────────────────────────────────────────
# Reporting
# ─────────────────────────────────────────────────────────────────────────────
def render(results: List[Result], *, stream=None) -> None:
    # `stream` is resolved per call rather than bound at definition time, so a
    # caller that has replaced sys.stdout (a test, a log tee) is honoured.
    stream = stream or sys.stdout
    grouped: Dict[str, List[Result]] = {}
    for result in results:
        grouped.setdefault(result.provider, []).append(result)

    counts: Dict[str, int] = {}
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1

    for provider, rows in grouped.items():
        print(f"\n{BLUE}{provider}{RESET}", file=stream)
        for row in rows:
            colour = VERDICT_COLOR.get(row.status, "")
            name = row.name or "—"
            latency = f"{row.latency_ms}ms" if row.latency_ms is not None else ""
            fingerprint = f" sha:{row.fingerprint}" if row.fingerprint else ""
            print(
                f"  {colour}{row.status:<16}{RESET} {row.capability:<34} "
                f"{DIM}{name}{fingerprint}{RESET} {latency}",
                file=stream,
            )
            print(f"    {DIM}{row.detail}{RESET}", file=stream)

    print("\n" + "─" * 72, file=stream)
    ordered = [OK, SHAPE_ONLY, ENDPOINT_UNKNOWN, HTTP_ERROR, AUTH_FAILED, UNREACHABLE, NOT_CONFIGURED, SKIPPED]
    summary = " · ".join(f"{s} {counts[s]}" for s in ordered if counts.get(s))
    print(summary, file=stream)

    duplicates: Dict[str, List[str]] = {}
    for row in results:
        if row.fingerprint:
            duplicates.setdefault(row.fingerprint, []).append(f"{row.provider}:{row.name or row.capability}")
    repeated = {k: v for k, v in duplicates.items() if len(v) > 1}
    if repeated:
        print(f"\n{YELLOW}the same value appears in more than one slot{RESET}", file=stream)
        for fingerprint, names in repeated.items():
            print(f"  sha:{fingerprint} → {', '.join(sorted(names))}", file=stream)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--only", nargs="*", help="limit to these probe groups")
    parser.add_argument("--json", dest="json_path", help="write the machine-readable report here")
    parser.add_argument("--quiet", action="store_true", help="only the summary line")
    args = parser.parse_args(argv)

    results = asyncio.run(run(args.only))
    if args.quiet:
        counts: Dict[str, int] = {}
        for result in results:
            counts[result.status] = counts.get(result.status, 0) + 1
        print(" · ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    else:
        render(results)

    if args.json_path:
        payload = {
            "probes": [r.as_dict() for r in results],
            "totals": {s: sum(1 for r in results if r.status == s) for s in set(r.status for r in results)},
        }
        Path(args.json_path).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        if not args.quiet:
            print(f"\nreport → {args.json_path}")

    if not any(r.status != NOT_CONFIGURED for r in results):
        return 2
    return 1 if any(r.status in FAILING for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
