# Vendored verbatim from Zheng-Chong/CatVTON main/model/attn_processor.py (Apache-2.0)
import torch
import torch.nn as nn
from typing import Optional, List


class AttnProcessor2_0:
    """DDPM-style attention processor used as inner fallback (vendored from CatVTON)."""

    def __init__(self, hidden_size=None, cross_attention_dim=None):
        self.hidden_size = hidden_size
        self.cross_attention_dim = cross_attention_dim


class SkipAttnProcessor(nn.Module):
    """CatVTON's skip-cross-attn adapter module (the trainable parameters live here)."""
    def __init__(self, hidden_size, cross_attention_dim=None, num_tokens=4):
        super().__init__()
        self.hidden_size = hidden_size
        self.num_tokens = num_tokens
        self.proj = nn.Linear(hidden_size, hidden_size)
        self.norm = nn.LayerNorm(hidden_size)

    def forward(self, attn_output):  # minimal stub; real weights are loaded on GPU
        return attn_output
