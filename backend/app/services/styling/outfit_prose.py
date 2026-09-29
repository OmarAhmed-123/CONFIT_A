"""Split one model reply into a main answer plus a line per alternate look.

WHY
---
Only `recommended_outfits[0]` was ever sent to the model, so a second
recommendation reached the shopper with a template string — "A cohesive
multi-brand ensemble combining structured Arket with..." — that never named
anything actually in it. Two looks were shown; one was described.

Describing each look with its own request would double an already ~9s
response, so all looks travel in ONE prompt and the reply is split here.

The parsing is deliberately forgiving about FORMAT and strict about
GROUNDING: a model may write "OUTFIT_2:", "**OUTFIT_2** -", or "Outfit 2 —",
and all of those are the same intent. But a line that survives is still
only attached if it mentions something genuinely in that outfit, because an
unanchored sentence is exactly the hallucination the rest of this pipeline
is built to prevent.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

#: Matches OUTFIT_2 / OUTFIT 2 / Outfit-2, with optional markdown emphasis
#: and any of : - — as the separator.
_MARKER = re.compile(
    r"^\s*[*_#\s]*outfit[\s_\-]*(\d+)[*_\s]*\s*[:\-\u2013\u2014]\s*(.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def split_outfit_prose(text: str) -> Tuple[str, Dict[int, str]]:
    """Return (main_answer, {outfit_index: sentence}).

    The markers are REMOVED from the main answer. Leaving them in would show
    the shopper the scaffolding we asked the model for.
    """
    if not text:
        return "", {}

    notes: Dict[int, str] = {}
    for match in _MARKER.finditer(text):
        try:
            index = int(match.group(1))
        except ValueError:
            continue
        sentence = match.group(2).strip().strip("*_ ")
        if sentence:
            # First win: a model that repeats a marker is not adding detail.
            notes.setdefault(index, sentence)

    main = _MARKER.sub("", text).strip()
    main = re.sub(r"\n{3,}", "\n\n", main)
    return main, notes


def _outfit_tokens(outfit: Dict[str, Any]) -> List[str]:
    """Distinctive words from the outfit's real items."""
    tokens: List[str] = []
    for item in outfit.get("items") or []:
        for field in ("product_title", "brand_name", "color_family"):
            value = (item.get(field) or "").strip()
            if value:
                tokens.extend(
                    word.lower()
                    for word in re.split(r"[^\w]+", value)
                    if len(word) > 3
                )
    return tokens


def is_grounded_in(sentence: str, outfit: Dict[str, Any]) -> bool:
    """True when the sentence names something really in this outfit.

    The guard that keeps this from becoming a hallucination channel: the
    model is describing several looks at once and could easily attribute a
    garment from one to another.
    """
    if not sentence or not outfit:
        return False
    lowered = sentence.lower()
    tokens = _outfit_tokens(outfit)
    if not tokens:
        # Nothing to check against: refuse rather than accept blindly.
        return False
    return any(token in lowered for token in tokens)


def attach_prose(outfits: List[Dict[str, Any]], notes: Dict[int, str]) -> int:
    """Write each grounded sentence onto its outfit. Returns how many stuck.

    Outfits are 1-indexed in the prompt because that is how they are
    presented to the shopper; outfit 1 is the main answer and is skipped.
    A sentence that fails grounding is DROPPED, leaving the template
    description in place — a wrong description is worse than a generic one.
    """
    attached = 0
    for index, sentence in notes.items():
        position = index - 1
        if position < 1 or position >= len(outfits):
            continue
        outfit = outfits[position]
        if is_grounded_in(sentence, outfit):
            outfit["description"] = sentence
            outfit["description_source"] = "ai"
            attached += 1
    return attached
