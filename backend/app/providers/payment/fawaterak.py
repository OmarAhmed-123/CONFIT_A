"""Production payment gateway adapter for Fawaterak (فواتيرك — Egypt & MENA).

Implements :class:`BasePaymentAdapter` against Fawaterak's official specifications:

* **API v3 (Primary — OAuth 2.0 `client_credentials` + `refresh_token`):**
  - `POST /oauth/token`
  - `GET  /api/v3/getTrPaymentmethods`
  - `POST /api/v3/createTransaction`
  - `POST /api/v3/getTransactionData`
  - `POST /api/v3/payment/capture`
  - `POST /api/v3/payment/void`
  - `POST /api/v3/refund/create`
* **API v2 (Seamless vendor-token compatibility prior to OAuth client creation):**
  - `GET  /api/v2/getPaymentmethods`
  - `POST /api/v2/createInvoiceLink`
  - `GET  /api/v2/getInvoiceData/{invoice_id}`
* **Cryptographic HMAC-SHA256 Webhook Verification (Constant-Time `hmac.compare_digest`):**
  - Paid / pending (`transactionHashKey` over `TransactionId=...&TransactionKey=...&PaymentMethod=...`,
    plus legacy invoice `hashKey` over `InvoiceId=...&InvoiceKey=...&PaymentMethod=...`)
  - Failed (`hashKey` over `TransactionId=...&TransactionKey=...&PaymentMethod=...` or `InvoiceId=...`)
  - Cancel / expired reference (`hashKey` over `referenceId=...&PaymentMethod=...`)
  - Refund approved (`hashKey` over `transactionId=...&amount=...&currency=...`)

Security invariants:
* Carries NO `.is_live` attribute anywhere (see `test_payment_adapter_liveness_owner.py`).
* Fixed origin allowlist (`https://app.fawaterk.com`, `https://staging.fawaterk.com`), `follow_redirects=False`
  so Bearer tokens are never forwarded off-origin.
* Never logs raw request/response bodies, OAuth secrets, vendor API keys, or customer PII.
* Converts all amounts using integer minor units with currency-specific scale
  (2 decimal places for EGP/SAR/AED/QAR/USD; 3 decimal places for KWD/BHD/OMR).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import threading
import time
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse

import httpx

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.providers.payment.base import BasePaymentAdapter

FAWATERAK_PRODUCTION_BASE_URL = "https://app.fawaterk.com"
FAWATERAK_STAGING_BASE_URL = "https://staging.fawaterk.com"
ALLOWED_FAWATERAK_HOSTS = frozenset({"app.fawaterk.com", "staging.fawaterk.com"})

# Currency minor-unit exponents across Egypt + all 6 GCC markets + USD/EUR.
# KWD (Kuwaiti Dinar), BHD (Bahraini Dinar), and OMR (Omani Rial) subdivide into
# 1000 minor units (3dp); EGP, SAR, AED, QAR, USD, EUR subdivide into 100 (2dp).
CURRENCY_MINOR_EXPONENTS: Dict[str, int] = {
    "EGP": 2,
    "SAR": 2,
    "AED": 2,
    "QAR": 2,
    "USD": 2,
    "EUR": 2,
    "GBP": 2,
    "KWD": 3,
    "BHD": 3,
    "OMR": 3,
}


def currency_exponent(currency_code: str) -> int:
    code = (currency_code or "EGP").strip().upper()
    return CURRENCY_MINOR_EXPONENTS.get(code, 2)


def minor_scale(currency_code: str) -> Decimal:
    return Decimal(10) ** currency_exponent(currency_code)


def to_minor_units(amount: Decimal | str | int | float, currency_code: str) -> int:
    dec = amount if isinstance(amount, Decimal) else Decimal(str(amount))
    scale = minor_scale(currency_code)
    return int((dec * scale).to_integral_value(rounding=ROUND_HALF_UP))


def from_minor_units(amount_minor: int, currency_code: str) -> Decimal:
    exp = currency_exponent(currency_code)
    quant = Decimal(10) ** (-exp)
    return (Decimal(int(amount_minor)) / minor_scale(currency_code)).quantize(
        quant, rounding=ROUND_HALF_UP
    )


def format_major_amount(amount_minor: int, currency_code: str) -> str:
    return str(from_minor_units(amount_minor, currency_code))


def resolve_fawaterak_base_url() -> str:
    explicit = (getattr(settings, "FAWATERAK_BASE_URL", None) or "").strip().rstrip("/")
    if explicit:
        parsed = urlparse(explicit)
        if parsed.scheme != "https" or parsed.hostname not in ALLOWED_FAWATERAK_HOSTS:
            raise ValueError(
                f"FAWATERAK_BASE_URL host {parsed.hostname!r} is not allowlisted; "
                f"expected one of {sorted(ALLOWED_FAWATERAK_HOSTS)}"
            )
        return explicit
    env_mode = (getattr(settings, "FAWATERAK_ENV", "production") or "production").strip().lower()
    if env_mode in ("staging", "sandbox", "test"):
        return FAWATERAK_STAGING_BASE_URL
    return FAWATERAK_PRODUCTION_BASE_URL


def compute_iframe_domain_hash(
    domain: str, provider_key: str, vendor_api_key: str
) -> str:
    """Compute Fawaterak domain-bound HMAC-SHA256 for hosted iframe checkout."""
    clean_domain = (domain or "").strip()
    clean_provider = (provider_key or "").strip()
    if not clean_domain or not clean_provider or not vendor_api_key:
        raise ValueError("domain, provider_key, and vendor_api_key are all required")
    string_to_sign = f"Domain={clean_domain}&ProviderKey={clean_provider}"
    return hmac.new(
        vendor_api_key.encode("utf-8"),
        string_to_sign.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


class _OAuthTokenCache:
    """Thread-safe expiry-aware cache for Fawaterak OAuth 2.0 client tokens."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._access_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._expires_at_monotonic: float = 0.0
        self._cache_identity: Optional[tuple[str, str]] = None

    def clear(self) -> None:
        with self._lock:
            self._access_token = None
            self._refresh_token = None
            self._expires_at_monotonic = 0.0
            self._cache_identity = None

    def get_cached(self, base_url: str, client_id: str) -> Optional[str]:
        with self._lock:
            if (
                self._cache_identity == (base_url, client_id)
                and self._access_token
                and time.monotonic() < (self._expires_at_monotonic - 60.0)
            ):
                return self._access_token
            return None

    def get_refresh_token(self, base_url: str, client_id: str) -> Optional[str]:
        with self._lock:
            if self._cache_identity == (base_url, client_id):
                return self._refresh_token
            return None

    def store(
        self,
        base_url: str,
        client_id: str,
        access_token: str,
        expires_in: int = 3600,
        refresh_token: Optional[str] = None,
    ) -> None:
        with self._lock:
            self._cache_identity = (base_url, client_id)
            self._access_token = access_token
            if refresh_token:
                self._refresh_token = refresh_token
            self._expires_at_monotonic = time.monotonic() + max(int(expires_in), 120)


_OAUTH_CACHE = _OAuthTokenCache()


class _MethodsReadinessCache:
    """TTL cache for enabled payment methods on the Fawaterak vendor account."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._snapshot: Optional[Dict[str, Any]] = None
        self._checked_at: float = 0.0

    def clear(self) -> None:
        with self._lock:
            self._snapshot = None
            self._checked_at = 0.0

    def get(self, ttl_seconds: float = 120.0) -> Optional[Dict[str, Any]]:
        with self._lock:
            if self._snapshot is not None and (time.monotonic() - self._checked_at) < ttl_seconds:
                return dict(self._snapshot)
            return None

    def set(self, snapshot: Dict[str, Any]) -> None:
        with self._lock:
            self._snapshot = dict(snapshot)
            self._checked_at = time.monotonic()


_METHODS_CACHE = _MethodsReadinessCache()


class FawaterakGatewayError(RuntimeError):
    """Structured error from Fawaterak HTTP or protocol interaction."""

    def __init__(self, reason: str, detail: str = "", status_code: Optional[int] = None):
        super().__init__(detail or reason)
        self.reason = reason
        self.detail = detail
        self.status_code = status_code


class FawaterakAdapter(BasePaymentAdapter):
    """Production PSP adapter for Fawaterak API v3 (OAuth2) and API v2 (Vendor Token)."""

    def __init__(
        self,
        transport_factory: Optional[Callable[[], httpx.AsyncBaseTransport]] = None,
    ) -> None:
        super().__init__(name="fawaterak")
        self._transport_factory = transport_factory

    def _client(self) -> httpx.AsyncClient:
        timeout = float(getattr(settings, "FAWATERAK_TIMEOUT_SECONDS", 20.0) or 20.0)
        transport = self._transport_factory() if self._transport_factory is not None else None
        return httpx.AsyncClient(
            base_url=resolve_fawaterak_base_url(),
            timeout=httpx.Timeout(timeout, connect=min(5.0, timeout)),
            follow_redirects=False,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "CONFIT-Commerce/1.0",
            },
            transport=transport,
        )

    @staticmethod
    def _has_oauth_credentials() -> bool:
        return bool(
            (getattr(settings, "FAWATERAK_CLIENT_ID", None) or "").strip()
            and (getattr(settings, "FAWATERAK_CLIENT_SECRET", None) or "").strip()
        )

    @staticmethod
    def _vendor_api_key() -> Optional[str]:
        val = (getattr(settings, "FAWATERAK_VENDOR_API_KEY", None) or "").strip()
        return val or None

    async def obtain_bearer_token(self, client: httpx.AsyncClient) -> tuple[str, str]:
        """Return `(bearer_token, api_version)` where `api_version` is `'v3'` or `'v2'`."""
        base_url = str(client.base_url).rstrip("/")
        if self._has_oauth_credentials():
            client_id = settings.FAWATERAK_CLIENT_ID.strip()
            client_secret = settings.FAWATERAK_CLIENT_SECRET.strip()
            cached = _OAUTH_CACHE.get_cached(base_url, client_id)
            if cached:
                return cached, "v3"

            refresh_tok = _OAUTH_CACHE.get_refresh_token(base_url, client_id)
            if refresh_tok:
                resp = await client.post(
                    "/oauth/token",
                    json={
                        "grant_type": "refresh_token",
                        "refresh_token": refresh_tok,
                        "client_id": client_id,
                        "client_secret": client_secret,
                    },
                )
                if resp.status_code == 200:
                    tok_data = resp.json()
                    access = tok_data.get("access_token")
                    if access:
                        _OAUTH_CACHE.store(
                            base_url,
                            client_id,
                            access,
                            expires_in=int(tok_data.get("expires_in") or 3600),
                            refresh_token=tok_data.get("refresh_token"),
                        )
                        return access, "v3"

            resp = await client.post(
                "/oauth/token",
                json={
                    "grant_type": "client_credentials",
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
            )
            if resp.status_code != 200:
                raise FawaterakGatewayError(
                    "oauth_token_exchange_failed",
                    f"Fawaterak OAuth token endpoint answered HTTP {resp.status_code}",
                    status_code=resp.status_code,
                )
            tok_data = resp.json()
            access = tok_data.get("access_token")
            if not access:
                raise FawaterakGatewayError(
                    "oauth_token_missing",
                    "Fawaterak OAuth response omitted access_token",
                )
            _OAUTH_CACHE.store(
                base_url,
                client_id,
                access,
                expires_in=int(tok_data.get("expires_in") or 3600),
                refresh_token=tok_data.get("refresh_token"),
            )
            return access, "v3"

        vendor_key = self._vendor_api_key()
        if vendor_key:
            return vendor_key, "v2"

        raise FawaterakGatewayError(
            "live_credentials_missing",
            "Neither Fawaterak OAuth credentials nor vendor API key are configured",
        )

    async def list_payment_methods(self) -> List[Dict[str, Any]]:
        """Return integration-enabled payment methods from Fawaterak (`v3` or `v2`)."""
        async with self._client() as client:
            token, api_ver = await self.obtain_bearer_token(client)
            path = "/api/v3/getTrPaymentmethods" if api_ver == "v3" else "/api/v2/getPaymentmethods"
            resp = await client.get(path, headers={"Authorization": f"Bearer {token}"})
            if resp.status_code != 200:
                raise FawaterakGatewayError(
                    "provider_unavailable",
                    f"Fawaterak payment-methods check returned HTTP {resp.status_code}",
                    status_code=resp.status_code,
                )
            body = resp.json()
            methods = body.get("data") or []
            result = methods if isinstance(methods, list) else []
            _METHODS_CACHE.set({
                "ok": True,
                "api_version": api_ver,
                "methods_count": len(result),
                "method_names": [
                    str(m.get("name_en") or m.get("payment_method") or m.get("paymentId") or "")
                    for m in result
                ],
            })
            return result

    async def create_payment_intent(
        self,
        amount_minor: int,
        currency_code: str,
        customer_email: str,
        customer_phone: Optional[str] = None,
        order_number: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a hosted/direct checkout transaction on Fawaterak."""
        meta = metadata or {}
        if amount_minor <= 0:
            raise FawaterakGatewayError("invalid_amount", "Payment amount must be positive")

        currency = (currency_code or "EGP").strip().upper()
        major_amount_dec = from_minor_units(amount_minor, currency)
        major_amount_str = str(major_amount_dec)

        full_name = str(meta.get("recipient_name") or "CONFIT Customer").strip()
        parts = full_name.split(None, 1)
        first_name = parts[0] if parts else "CONFIT"
        last_name = parts[1] if len(parts) > 1 else "Customer"
        phone = (customer_phone or meta.get("phone") or "01000000000").strip() or "01000000000"
        email = (customer_email or "guest@confit.example").strip()
        address = str(meta.get("address") or "Cairo, Egypt").strip()

        base_front = (getattr(settings, "FRONTEND_BASE_URL", "") or "https://confit-a.vercel.app").rstrip("/")
        ord_ref = str(order_number or "")
        redirection_urls = {
            "successUrl": f"{base_front}/orders/{ord_ref}?payment=return" if ord_ref else f"{base_front}/orders",
            "failUrl": f"{base_front}/checkout?payment=failed&order={ord_ref}",
            "pendingUrl": f"{base_front}/orders/{ord_ref}?payment=pending" if ord_ref else f"{base_front}/orders",
            "webhookUrl": f"{base_front}/api/v1/payments/webhooks/fawaterak/paid_json",
        }
        cart_items = meta.get("cart_items") or [
            {
                "name": f"CONFIT Order {ord_ref or 'Checkout'}",
                "price": float(major_amount_dec) if currency_exponent(currency) == 2 else major_amount_str,
                "quantity": 1,
            }
        ]
        pay_load = {"order_number": ord_ref, "currency": currency, "amount_minor": int(amount_minor)}

        try:
            async with self._client() as client:
                token, api_ver = await self.obtain_bearer_token(client)
                # Verify merchant account actually has enabled checkout rails before
                # redirecting a real shopper onto an empty checkout screen.
                if not meta.get("skip_methods_precheck"):
                    methods_path = (
                        "/api/v3/getTrPaymentmethods" if api_ver == "v3" else "/api/v2/getPaymentmethods"
                    )
                    m_resp = await client.get(methods_path, headers={"Authorization": f"Bearer {token}"})
                    if m_resp.status_code != 200:
                        return {
                            "transaction_id": f"fwk_err_{ord_ref}",
                            "provider": "fawaterak",
                            "status": "failed",
                            "mode": "live",
                            "reason": "provider_unavailable",
                        }
                    enabled_methods = (m_resp.json() or {}).get("data") or []
                    _METHODS_CACHE.set({
                        "ok": True,
                        "api_version": api_ver,
                        "methods_count": len(enabled_methods),
                    })
                    if not enabled_methods:
                        logger.error(
                            "fawaterak_no_payment_methods_enabled",
                            order_number=ord_ref,
                            api_version=api_ver,
                        )
                        return {
                            "transaction_id": f"fwk_unconfigured_{ord_ref}",
                            "provider": "fawaterak",
                            "status": "failed",
                            "mode": "live",
                            "reason": "merchant_payment_methods_not_enabled",
                        }

                if api_ver == "v3":
                    req_body: Dict[str, Any] = {
                        "currency": currency,
                        "cartTotal": float(major_amount_dec),
                        "customer": {
                            "first_name": first_name,
                            "last_name": last_name,
                            "email": email,
                            "phone": phone,
                            "address": address,
                        },
                        "cartItems": cart_items,
                        "pay_load": pay_load,
                        "redirectionUrls": redirection_urls,
                        "tr_number": ord_ref or None,
                        "list_style": "h",
                        "lang": str(meta.get("lang") or "en"),
                    }
                    if meta.get("payment_method_id") is not None:
                        req_body["payment_method_id"] = int(meta["payment_method_id"])
                    resp = await client.post(
                        "/api/v3/createTransaction",
                        headers={"Authorization": f"Bearer {token}"},
                        json=req_body,
                    )
                    if resp.status_code not in (200, 201):
                        logger.error(
                            "fawaterak_v3_create_failed",
                            order_number=ord_ref,
                            status_code=resp.status_code,
                        )
                        return {
                            "transaction_id": f"fwk_err_{ord_ref}",
                            "provider": "fawaterak",
                            "status": "failed",
                            "mode": "live",
                            "reason": "provider_rejected_payment",
                        }
                    data = (resp.json() or {}).get("data") or {}
                    intent_key = str(data.get("intent_key") or "")
                    checkout_url = data.get("url") or data.get("short_url")
                    return {
                        "transaction_id": f"tr:{intent_key}",
                        "provider": "fawaterak",
                        "status": "pending",
                        "redirect_url": checkout_url,
                        "requires_redirect": bool(checkout_url),
                        "payment_data": data.get("payment_data"),
                        "mode": "live",
                    }

                # API v2 invoice link path (authenticated by FAWATERAK_VENDOR_API_KEY)
                v2_body = {
                    "cartTotal": major_amount_str,
                    "currency": currency,
                    "customer": {
                        "first_name": first_name,
                        "last_name": last_name,
                        "email": email,
                        "phone": phone,
                        "address": address,
                    },
                    "redirectionUrls": {
                        "successUrl": redirection_urls["successUrl"],
                        "failUrl": redirection_urls["failUrl"],
                        "pendingUrl": redirection_urls["pendingUrl"],
                    },
                    "cartItems": [
                        {
                            "name": str(item.get("name") or f"Order {ord_ref}"),
                            "price": str(item.get("price")),
                            "quantity": int(item.get("quantity") or 1),
                        }
                        for item in cart_items
                    ],
                    "payLoad": pay_load,
                }
                resp = await client.post(
                    "/api/v2/createInvoiceLink",
                    headers={"Authorization": f"Bearer {token}"},
                    json=v2_body,
                )
                if resp.status_code not in (200, 201):
                    logger.error(
                        "fawaterak_v2_create_failed",
                        order_number=ord_ref,
                        status_code=resp.status_code,
                    )
                    return {
                        "transaction_id": f"fwk_err_{ord_ref}",
                        "provider": "fawaterak",
                        "status": "failed",
                        "mode": "live",
                        "reason": "provider_rejected_payment",
                    }
                data = (resp.json() or {}).get("data") or {}
                inv_id = data.get("invoiceId") or data.get("invoice_id")
                inv_key = data.get("invoiceKey") or data.get("invoice_key")
                checkout_url = data.get("url")
                return {
                    "transaction_id": f"inv:{inv_id}:{inv_key}" if inv_key else f"inv:{inv_id}",
                    "provider": "fawaterak",
                    "status": "pending",
                    "redirect_url": checkout_url,
                    "requires_redirect": bool(checkout_url),
                    "mode": "live",
                }
        except FawaterakGatewayError as exc:
            logger.error("fawaterak_gateway_error", order_number=ord_ref, reason=exc.reason)
            return {
                "transaction_id": f"fwk_err_{ord_ref}",
                "provider": "fawaterak",
                "status": "failed",
                "mode": "live",
                "reason": exc.reason,
            }
        except httpx.HTTPError as exc:
            logger.error(
                "fawaterak_network_error",
                order_number=ord_ref,
                error_type=type(exc).__name__,
            )
            return {
                "transaction_id": f"fwk_net_{ord_ref}",
                "provider": "fawaterak",
                "status": "failed",
                "mode": "live",
                "reason": "provider_connection_error",
            }

    async def get_transaction_status(self, provider_tx_id: str) -> Dict[str, Any]:
        """Re-read authoritative settlement status, amount, and currency from Fawaterak."""
        raw_id = (provider_tx_id or "").strip()
        async with self._client() as client:
            token, api_ver = await self.obtain_bearer_token(client)
            if raw_id.startswith("tr:") or (api_ver == "v3" and not raw_id.startswith("inv:")):
                intent_key = raw_id.split("tr:", 1)[1] if raw_id.startswith("tr:") else raw_id
                resp = await client.post(
                    "/api/v3/getTransactionData",
                    headers={"Authorization": f"Bearer {token}"},
                    json={"intent_key": intent_key},
                )
                if resp.status_code != 200:
                    raise FawaterakGatewayError(
                        "provider_status_lookup_failed",
                        f"getTransactionData returned HTTP {resp.status_code}",
                        status_code=resp.status_code,
                    )
                data = (resp.json() or {}).get("data") or {}
                paid_flag = str(data.get("paid") if "paid" in data else data.get("status") or "").lower()
                is_paid = paid_flag in ("1", "true", "paid", "captured", "succeeded")
                status_text = str(data.get("status") or data.get("status_text") or "").lower()
                normalized_status = (
                    "paid" if is_paid
                    else "cancelled" if status_text in ("cancelled", "canceled", "expired")
                    else "failed" if status_text in ("failed", "declined", "error")
                    else "pending"
                )
                currency = str(data.get("currency") or data.get("paidCurrency") or "EGP").upper()
                total_raw = data.get("paidAmount") if data.get("paidAmount") is not None else data.get("total", data.get("cartTotal", 0))
                return {
                    "provider": "fawaterak",
                    "provider_tx_id": raw_id,
                    "status": normalized_status,
                    "currency": currency,
                    "amount": Decimal(str(total_raw)),
                    "amount_minor": to_minor_units(Decimal(str(total_raw)), currency),
                    "transaction_id": data.get("id") or data.get("transaction_id"),
                }

            # API v2 invoice lookup: `inv:{invoice_id}:{invoice_key}` or plain `{invoice_id}`
            parts = raw_id.split(":")
            invoice_id = parts[1] if raw_id.startswith("inv:") and len(parts) >= 2 else raw_id
            resp = await client.get(
                f"/api/v2/getInvoiceData/{invoice_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code != 200:
                raise FawaterakGatewayError(
                    "provider_status_lookup_failed",
                    f"getInvoiceData returned HTTP {resp.status_code}",
                    status_code=resp.status_code,
                )
            data = (resp.json() or {}).get("data") or {}
            paid_flag = str(data.get("paid") if "paid" in data else "").lower()
            status_text = str(data.get("status_text") or "").lower()
            is_paid = paid_flag in ("1", "true", "paid") or status_text == "paid"
            normalized_status = (
                "paid" if is_paid
                else "cancelled" if status_text in ("cancelled", "canceled", "expired")
                else "failed" if status_text in ("failed", "declined")
                else "pending"
            )
            currency = str(data.get("currency") or "EGP").upper()
            total_raw = data.get("total", 0)
            return {
                "provider": "fawaterak",
                "provider_tx_id": raw_id,
                "status": normalized_status,
                "currency": currency,
                "amount": Decimal(str(total_raw)),
                "amount_minor": to_minor_units(Decimal(str(total_raw)), currency),
                "invoice_id": data.get("invoice_id") or invoice_id,
                "invoice_key": data.get("invoice_key"),
            }

    async def refund(
        self,
        provider_tx_id: str,
        amount: Decimal | float | str,
        reason: str = "Customer return",
    ) -> Dict[str, Any]:
        """Submit a full or partial refund via Fawaterak API v3 `/api/v3/refund/create`."""
        raw_id = (provider_tx_id or "").strip()
        amount_dec = amount if isinstance(amount, Decimal) else Decimal(str(amount))
        try:
            async with self._client() as client:
                token, api_ver = await self.obtain_bearer_token(client)
                if api_ver != "v3":
                    return {
                        "status": "failed",
                        "reason": "oauth_v3_credentials_required_for_refund",
                        "provider_tx_id": raw_id,
                    }
                refund_type = "0" if raw_id.startswith("inv:") else "3"
                numeric_id: Optional[int] = None
                if raw_id.startswith("inv:"):
                    seg = raw_id.split(":")[1]
                    numeric_id = int(seg) if seg.isdigit() else None
                elif raw_id.isdigit():
                    numeric_id = int(raw_id)
                else:
                    status_info = await self.get_transaction_status(raw_id)
                    if status_info.get("transaction_id") is not None:
                        numeric_id = int(status_info["transaction_id"])
                if numeric_id is None:
                    return {
                        "status": "failed",
                        "reason": "provider_refund_id_unresolvable",
                        "provider_tx_id": raw_id,
                    }
                resp = await client.post(
                    "/api/v3/refund/create",
                    headers={"Authorization": f"Bearer {token}"},
                    json={
                        "refund_type": refund_type,
                        "refund_id": numeric_id,
                        "reason": reason,
                        "refundable_amount": float(amount_dec),
                    },
                )
                if resp.status_code not in (200, 201):
                    return {
                        "status": "failed",
                        "reason": f"provider_refund_http_{resp.status_code}",
                        "provider_tx_id": raw_id,
                    }
                body = resp.json() or {}
                r_data = body.get("data") or {}
                approved = str(r_data.get("status") or "").lower() in ("1", "approved", "refunded")
                return {
                    "status": "refunded" if approved else "refund_pending",
                    "provider_tx_id": raw_id,
                    "refund_request_id": r_data.get("id") or r_data.get("refund_id"),
                    "amount": float(amount_dec),
                    "mode": "live",
                }
        except FawaterakGatewayError as exc:
            return {"status": "failed", "reason": exc.reason, "provider_tx_id": raw_id}
        except httpx.HTTPError:
            return {"status": "failed", "reason": "provider_connection_error", "provider_tx_id": raw_id}

    async def verify_webhook_signature(
        self,
        payload_bytes: bytes,
        signature_header: str,
        secret: str,
    ) -> bool:
        """Verify either raw-body `X-Signature` OR canonical Fawaterak HMAC `hashKey` / `transactionHashKey`."""
        return self.verify_webhook_payload_sync(payload_bytes, signature_header, secret)

    @staticmethod
    def verify_webhook_payload_sync(
        payload_bytes: bytes,
        signature_header: str,
        secret: str,
        parsed_payload: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Constant-time verification covering all 4 official Fawaterak webhook schemas:

        1. Paid / pending (`transactionHashKey` or legacy `hashKey`):
           `TransactionId={id}&TransactionKey={key}&PaymentMethod={method}`
           or `InvoiceId={id}&InvoiceKey={key}&PaymentMethod={method}`
        2. Failed (`hashKey`):
           `TransactionId={id}&TransactionKey={key}&PaymentMethod={method}`
           or `InvoiceId={id}&InvoiceKey={key}&PaymentMethod={method}`
        3. Cancel / expired reference (`hashKey`):
           `referenceId={referenceId}&PaymentMethod={paymentMethod}`
        4. Refund approved (`hashKey`):
           `transactionId={transactionId}&amount={amount}&currency={currency}`
        5. Standard raw-body `X-Signature` header (`HMAC-SHA256(raw_body, secret)`).
        """
        if not secret:
            return False

        key_bytes = secret.encode("utf-8")

        if signature_header:
            raw_expected = hmac.new(key_bytes, payload_bytes, hashlib.sha256).hexdigest()
            if hmac.compare_digest(raw_expected.lower(), signature_header.strip().lower()):
                return True

        data = parsed_payload
        if data is None:
            try:
                data = json.loads(payload_bytes.decode("utf-8") or "{}")
            except (UnicodeDecodeError, ValueError):
                return False
        if not isinstance(data, dict):
            return False

        provided_hash = str(
            data.get("transactionHashKey") or data.get("hashKey") or ""
        ).strip().lower()
        if not provided_hash:
            return False

        candidate_strings: List[str] = []
        tx_id = data.get("transaction_id")
        tx_key = data.get("transaction_key")
        inv_id = data.get("invoice_id")
        inv_key = data.get("invoice_key")
        pm = data.get("payment_method")
        if tx_id is not None and tx_key is not None and pm is not None:
            candidate_strings.append(
                f"TransactionId={tx_id}&TransactionKey={tx_key}&PaymentMethod={pm}"
            )
        if inv_id is not None and inv_key is not None and pm is not None:
            candidate_strings.append(
                f"InvoiceId={inv_id}&InvoiceKey={inv_key}&PaymentMethod={pm}"
            )
        ref_id = data.get("referenceId")
        pm_camel = data.get("paymentMethod")
        if ref_id is not None and pm_camel is not None:
            candidate_strings.append(f"referenceId={ref_id}&PaymentMethod={pm_camel}")
        r_tx_id = data.get("transactionId")
        r_amt = data.get("amount")
        r_ccy = data.get("currency")
        if r_tx_id is not None and r_amt is not None and r_ccy is not None:
            candidate_strings.append(
                f"transactionId={r_tx_id}&amount={r_amt}&currency={r_ccy}"
            )

        for canonical in candidate_strings:
            expected = hmac.new(
                key_bytes, canonical.encode("utf-8"), hashlib.sha256
            ).hexdigest().lower()
            if hmac.compare_digest(expected, provided_hash):
                return True
        return False


def fawaterak_credentials_present() -> bool:
    """True when server-side Fawaterak credentials exist (OAuth v3 or Vendor API key)."""
    has_oauth = bool(
        (getattr(settings, "FAWATERAK_CLIENT_ID", None) or "").strip()
        and (getattr(settings, "FAWATERAK_CLIENT_SECRET", None) or "").strip()
    )
    has_vendor = bool((getattr(settings, "FAWATERAK_VENDOR_API_KEY", None) or "").strip())
    return has_oauth or has_vendor


def fawaterak_portal_ready_from_cache() -> Optional[bool]:
    """Return cached boolean if we have already measured vendor methods (`None` if unprobed)."""
    snap = _METHODS_CACHE.get()
    if snap is None:
        return None
    return bool(snap.get("ok")) and int(snap.get("methods_count") or 0) > 0
