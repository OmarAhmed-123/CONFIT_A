"""Deterministic, reproducible model specification for the CONFIT Qwen2.5-VL worker.

Single source of truth for WHAT is acquired and WHERE, so the model can be
reconstructed on any deployment (a Modal Volume) without a developer's laptop,
an untracked cache, or /tmp.

License gate (VERIFIED 2026-09-07 from the authoritative Hugging Face model card
and the model's own LICENSE file):

* ``Qwen/Qwen2.5-VL-7B-Instruct`` -> **Apache-2.0** (commercially usable)   [SELECTED]
* ``Qwen/Qwen2.5-VL-3B-Instruct`` -> **Qwen RESEARCH LICENSE** ("NON-COMMERCIAL
  PURPOSES ONLY"; commercial use requires a separate license from Alibaba Cloud)
  -> **BLOCKED** for this commercial product.

The 3B is deliberately NOT used. The 7B is both the only commercially-safe variant
in the target set and the stronger of the two for structured attribute extraction.
"""
from __future__ import annotations

from typing import Tuple

MODEL_REPO_ID = "Qwen/Qwen2.5-VL-7B-Instruct"

# Pinned to the model-repo HEAD observed at integration time. Acquisition is
# deterministic because the revision is pinned (never floats to 'main').
MODEL_REVISION = "cc594898137f460bfe9f0759e9844b3ce807cfb5"

LICENSE = "apache-2.0"
UPSTREAM_REPO = "https://github.com/QwenLM/Qwen2.5-VL"
HF_URL = "https://huggingface.co/Qwen/Qwen2.5-VL-7B-Instruct"

# Exact file set the inference requires (matches the model card 'siblings'),
# plus LICENSE so the Apache-2.0 evidence is carried with the weights.
REQUIRED_FILES: Tuple[str, ...] = (
    "LICENSE",
    "config.json",
    "generation_config.json",
    "chat_template.json",
    "preprocessor_config.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "vocab.json",
    "merges.txt",
    "model-00001-of-00005.safetensors",
    "model-00002-of-00005.safetensors",
    "model-00003-of-00005.safetensors",
    "model-00004-of-00005.safetensors",
    "model-00005-of-00005.safetensors",
    "model.safetensors.index.json",
)

# BF16 weights ~16.58 GB. Require at least this much on disk so a truncated or
# corrupted acquisition is caught (never half-loaded).
MIN_TOTAL_BYTES = 16_000_000_000  # ~16 GB
# Expected total (BF16), for observability / audit.
EXPECTED_TOTAL_BYTES = 16_584_414_560  # ~16.58 GB (HF 'usedStorage')
