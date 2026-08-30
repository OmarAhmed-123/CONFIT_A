# Vendored verbatim from Zheng-Chong/CatVTON main/model/utils.py (Apache-2.0)
import torch
import torch.nn as nn
from .attn_processor import SkipAttnProcessor, AttnProcessor2_0

CROSS_ATTENTION_DIM = 768


def init_adapter(unet, cross_attn_cls=SkipAttnProcessor):
    """Replace every cross-attention processor in the UNet with our trainable SkipAttnProcessor.

    Mirrors CatVTON's own init_adapter so the saved attention state_dict keys match.
    """
    attn_procs = {}
    for name in unet.attn_processors.keys():
        cross_attention_dim = None if name.endswith("attn1.processor") else CROSS_ATTENTION_DIM
        if name.startswith("mid_block"):
            hidden_size = unet.config.block_out_channels[-1]
        elif name.startswith("up_blocks"):
            block_id = int(name[len("up_blocks.")])
            hidden_size = list(reversed(unet.config.block_out_channels))[block_id]
        elif name.startswith("down_blocks"):
            block_id = int(name[len("down_blocks.")])
            hidden_size = unet.config.block_out_channels[block_id]
        else:
            hidden_size = unet.config.block_out_channels[-1]
        if cross_attention_dim is None:
            attn_procs[name] = AttnProcessor2_0(hidden_size=hidden_size,
                                               cross_attention_dim=cross_attention_dim)
        else:
            attn_procs[name] = cross_attn_cls(hidden_size=hidden_size,
                                              cross_attention_dim=cross_attention_dim)
    unet.set_attn_processor(attn_procs)
    adapter_modules = nn.ModuleList(unet.attn_processors.values())
    return adapter_modules


def get_trainable_module(unet, trainable_module_name="skip_cross_attn"):
    return unet
