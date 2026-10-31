"""IBM watsonx.ai provider (stylist text leg, eu-de)."""

from backend.app.providers.watsonx.client import (
    WatsonxAuthError,
    WatsonxClient,
    watsonx_client,
)

__all__ = ["WatsonxAuthError", "WatsonxClient", "watsonx_client"]
