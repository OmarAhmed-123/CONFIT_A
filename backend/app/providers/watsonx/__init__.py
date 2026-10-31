"""IBM watsonx.ai integration (Granite stylist tutorial alignment).

Modules
-------
client   – IAM token exchange + ``POST /ml/v1/text/chat`` with bounded retries.
prompts  – version-controlled system prompts for vision tagging and styling.
vision   – wardrobe image analysis returning the platform's analysis envelope.

The SDK the IBM tutorial uses (``ibm_watsonx_ai.foundation_models.
ModelInference.chat``) is a thin wrapper over the same REST contract this
package calls directly with ``httpx`` (already a declared runtime dependency;
the serverless import-closure gate forbids undeclared packages). Request and
response shapes are identical: ``{model_id, project_id, messages, max_tokens,
temperature}`` → ``choices[0].message.content``.
"""
from backend.app.providers.watsonx.client import (  # noqa: F401
    WatsonxChatResult,
    WatsonxClient,
    WatsonxError,
    WatsonxNotConfiguredError,
    get_watsonx_client,
    watsonx_configured,
)
