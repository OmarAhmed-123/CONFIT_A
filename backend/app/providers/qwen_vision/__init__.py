"""CONFIT_A self-hosted Qwen2.5-VL vision provider.

A LIGHTWEIGHT client only. It never imports torch/transformers and never touches
model weights — the model lives and runs on a separate self-hosted inference
worker (services/vlm-worker, Modal) that this client talks to over HTTP.

Role: local vision FALLBACK for Visual Search and Wardrobe Auto-Tagging, used ONLY
when the Gemini vision provider is exhausted/unavailable. When the worker is not
configured (QWEN_VL_WORKER_URL unset), is_configured() is False and the existing
Gemini-only behaviour is completely unchanged.
"""
from .errors import QwenVisionError
from .provider import QwenVisionProvider

__all__ = ["QwenVisionProvider", "QwenVisionError"]
