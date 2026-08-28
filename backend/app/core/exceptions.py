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


class BNPLRejectedError(ConfitException):
    def __init__(self, provider: str, reason: str):
        super().__init__(
            f"BNPL transaction rejected by {provider}: {reason}",
            code="BNPL_REJECTED",
            details={"provider": provider, "reason": reason},
            status_code=status.HTTP_400_BAD_REQUEST
        )
