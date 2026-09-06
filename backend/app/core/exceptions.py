from typing import Any, Dict, Optional
from fastapi import status


class ConfitException(Exception):
    """Base domain exception for CONFIT platform."""
    def __init__(
        self,
        message: str,
        code: str = "CONFIT_INTERNAL_ERROR",
        details: Optional[Dict[str, Any]] = None,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}
        self.status_code = status_code


class AuthenticationError(ConfitException):
    def __init__(self, message: str = "Authentication failed", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="AUTH_FAILED", details=details, status_code=status.HTTP_401_UNAUTHORIZED)


class AuthorizationError(ConfitException):
    def __init__(self, message: str = "Insufficient permissions", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="FORBIDDEN_ACCESS", details=details, status_code=status.HTTP_403_FORBIDDEN)


class ResourceNotFoundError(ConfitException):
    def __init__(self, resource: str, resource_id: Any):
        super().__init__(
            f"{resource} with id '{resource_id}' was not found",
            code="RESOURCE_NOT_FOUND",
            details={"resource": resource, "id": str(resource_id)},
            status_code=status.HTTP_404_NOT_FOUND
        )


class ValidationDomainError(ConfitException):
    def __init__(self, message: str, field_errors: Optional[Dict[str, Any]] = None):
        super().__init__(
            message,
            code="VALIDATION_ERROR",
            details={"fields": field_errors or {}},
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY
        )


class ProviderIntegrationError(ConfitException):
    def __init__(self, provider: str, message: str, retryable: bool = True):
        super().__init__(
            f"Provider '{provider}' error: {message}",
            code="PROVIDER_ERROR",
            details={"provider": provider, "retryable": retryable},
            status_code=status.HTTP_502_BAD_GATEWAY
        )


class TryOnEngineUnavailableError(ConfitException):
    """Raised when virtual try-on rendering cannot be performed.

    A generation feature must never convert a failed generation into a
    successful response: if the render backend did not run, the honest
    answer is a 503 with this error code — never a substitute image and
    never a fabricated metric.
    """
    def __init__(self, reason: str = "gpu_worker_not_configured"):
        super().__init__(
            "Virtual try-on rendering is temporarily unavailable.",
            code="VTON_ENGINE_UNAVAILABLE",
            details={"reason": reason},
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE
        )


class StylingEngineRuleError(ConfitException):
    def __init__(self, reason: str, incompatible_items: Optional[list] = None):
        super().__init__(
            f"Outfit generation rule violation: {reason}",
            code="STYLING_RULE_VIOLATION",
            details={"reason": reason, "items": incompatible_items or []},
            status_code=status.HTTP_400_BAD_REQUEST
        )


class InventoryUnavailableError(ConfitException):
    def __init__(self, sku: str, requested: int, available: int):
        super().__init__(
            f"Insufficient inventory for SKU {sku}. Requested: {requested}, Available: {available}",
            code="INSUFFICIENT_STOCK",
            details={"sku": sku, "requested": requested, "available": available},
            status_code=status.HTTP_409_CONFLICT
        )


class InvalidStateTransitionError(ConfitException):
    def __init__(self, current: str, attempted: str):
        super().__init__(
            f"Cannot transition order from '{current}' to '{attempted}'.",
            code="INVALID_STATE_TRANSITION",
            details={"current": current, "attempted": attempted},
            status_code=status.HTTP_409_CONFLICT,
        )


class FulfillmentBlockedError(ConfitException):
    """PAY-01: fulfilment gate — goods may only move for settled payment.

    Card/wallet orders must reach payment_status 'paid' (provider capture via
    webhook, or the explicit demo capture) before any fulfilment state;
    COD orders are payable at handover and are exempt until then.
    """

    def __init__(self, current: str, attempted: str, payment_status: str):
        super().__init__(
            f"Fulfillment '{current}' -> '{attempted}' is blocked: payment status is "
            f"'{payment_status}'. Capture the payment (provider webhook or demo capture) first.",
            code="FULFILLMENT_PAYMENT_REQUIRED",
            details={"current": current, "attempted": attempted, "payment_status": payment_status},
            status_code=status.HTTP_409_CONFLICT,
        )


class AdminReauthRequiredError(ConfitException):
    """ADMIN-01: step-up/re-auth policy for sensitive admin mutations.

    The admin token is too old (issued earlier than the freshness window), so
    the action is refused with 401 until the admin signs in again. 401 (not
    403): the identity is known but this specific authorization has lapsed.
    """

    def __init__(self, age_minutes: int, max_age_minutes: int):
        super().__init__(
            f"Admin session is {age_minutes} minutes old (policy: at most "
            f"{max_age_minutes}). Sign in again to perform this action.",
            code="ADMIN_REAUTH_REQUIRED",
            details={"token_age_minutes": age_minutes, "max_age_minutes": max_age_minutes},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )


class PromoIneligibleError(ConfitException):
    def __init__(self, code: str, reason: str):
        super().__init__(
            f"Promotion '{code}' cannot be applied: {reason}",
            code="PROMO_INELIGIBLE",
            details={"promo_code": code, "reason": reason},
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )


class ReturnIneligibleError(ConfitException):
    def __init__(self, reason: str):
        super().__init__(
            reason,
            code="RETURN_INELIGIBLE",
            details={"reason": reason},
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )


class PaymentFailedError(ConfitException):
    def __init__(self, provider: str, reason: str):
        super().__init__(
            f"Payment was not confirmed by {provider}: {reason}",
            code="PAYMENT_FAILED",
            details={"provider": provider, "reason": reason},
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
        )


class BNPLRejectedError(ConfitException):
    def __init__(self, provider: str, reason: str):
        super().__init__(
            f"BNPL transaction rejected by {provider}: {reason}",
            code="BNPL_REJECTED",
            details={"provider": provider, "reason": reason},
            status_code=status.HTTP_400_BAD_REQUEST
        )


class EncryptionError(ConfitException):
    """Raised when a Fernet decrypt (or encrypt) operation fails.

    Fixes the audit finding G1.BODY-02: `decrypt_sensitive_data` used to
    silently return the ciphertext on failure, so a key rotation would
    have leaked raw base64 ciphertext into API responses as if it were
    the decrypted body_attributes payload. Now the failure is surfaced
    as a controlled 500 with a diagnostic reason (no ciphertext content
    ever included in the response body or the logs).
    """
    def __init__(self, reason: str = "cipher_operation_failed"):
        super().__init__(
            "Encrypted profile field could not be read. Contact support.",
            code="ENCRYPTION_ERROR",
            details={"reason": reason},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


class FeatureNotConfiguredError(ConfitException):
    """Raised when a real production dependency (email provider, live OAuth
    client secrets, etc.) is not configured, so an operation cannot honestly
    complete. Never faked — see spec §12 password reset & §7 OAuth.
    """
    def __init__(self, feature: str, hint: str = ""):
        super().__init__(
            f"Feature '{feature}' is not configured in this environment.",
            code="FEATURE_NOT_CONFIGURED",
            details={"feature": feature, "hint": hint},
            status_code=status.HTTP_501_NOT_IMPLEMENTED
        )


class DeliveryGoneError(ConfitException):
    """Raised when a temporary VTON result can no longer be delivered.

    The generated image is never stored durably (product requirement); the
    only copy lives in a process-local, TTL-bounded, one-shot cache. This
    error is the honest answer when the copy was already claimed, expired,
    revoked, or was never staged on THIS function instance (serverless
    instance affinity). Status 410 GONE — the resource existed and is now
    gone; it is never resurrected and never faked.
    """
    def __init__(self, reason: str = "expired_or_delivered"):
        super().__init__(
            "The generated try-on result is no longer available for download. "
            "It was already delivered, expired, or was not staged on this instance. "
            "Submit a new try-on job to generate a fresh result.",
            code="VTON_RESULT_GONE",
            details={"reason": reason},
            status_code=status.HTTP_410_GONE
        )
