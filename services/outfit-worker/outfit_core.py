"""Feature 06 — CONFIT outfit compatibility engine core (OutfitTransformer).

Pure-logic part (this module's top section) is importable WITHOUT torch so
CI can unit-test category mapping, type-aware analysis and the TATTOO-style
axis math on any host. The model layer (`OutfitEngine`) imports the vendored
upstream code lazily and only exists where the checkpoints are mounted.

Models (both CPU, both commercial-safe, MIT):
  * OutfitCLIPTransformer — frozen FashionCLIP (patrickjohncyh/fashion-clip)
    item encoder + 6-layer transformer head, trained on Polyvore
    (bigohofone/outfit-transformer @ eef4be5; see
    vendor/outfit-transformer/UPSTREAM_PROVENANCE.txt).
    - compatibility checkpoint → CP (sigmoid score 0-1)
    - complementary checkpoint  → CIR/FITB (cosine retrieval)

Honesty contract (mirrors the other CONFIT workers):
  - refusals raise OutfitEngineRefused(code, message) → HTTP 422/503,
    never a fabricated score;
  - `aesthetic_axes` is a training-free CLIP text-anchor projection over the
    axes popularised by TATTOO (arXiv:2509.23242). It is NOT the paper's
    MLLM pipeline and says so in every response;
  - every response discloses models, licenses and the Polyvore training
    distribution.
"""
from __future__ import annotations

import math
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

# ──────────────────────────────────────────────────────────────────────
# Pure logic — torch-free, unit-tested in CI
# ──────────────────────────────────────────────────────────────────────

#: CONFIT slot vocabulary (SlotLayeringEngine / tryon_service) → the
#: Polyvore category vocabulary the model was trained with. The mapping is
#: many-to-one and lossy by design: accessories collapse to "accessories".
#: Unknown slots are NOT guessed — they pass through as "unknown" so the
#: caller can see the model received less signal, not invented signal.
SLOT_TO_POLYVORE = {
    "upper_inner": "tops",
    "upper_outer": "outerwear",
    "lower": "bottoms",
    "footwear": "shoes",
    "full_body": "all-body",
    "accessory_waist": "accessories",
    "accessory_neck": "accessories",
    "accessory_hand": "accessories",
    "accessory_head": "accessories",
    "accessory_light": "accessories",
    "accessory": "accessories",
    "bags": "bags",
}

#: Slots that must appear at most once for a coherent outfit (the same
#: exclusivity SlotLayeringEngine enforces upstream in the backend).
EXCLUSIVE_SLOTS = {
    "upper_inner", "upper_outer", "lower", "footwear", "full_body",
    "accessory_waist", "accessory_head",
}

#: Coverage essentials: what a "complete" look needs. Deliberately advisory —
#: the model scores whatever it is given; this block explains the score.
ESSENTIAL_SLOTS = ("upper_inner", "lower", "footwear")
FULL_BODY_ALTERNATIVE = "full_body"

MAX_COMPAT_ITEMS = 16
MAX_FITB_OUTFIT_ITEMS = 16
MAX_FITB_CANDIDATES = 64
MIN_COMPAT_ITEMS = 2
MIN_FITB_OUTFIT_ITEMS = 1


def normalize_slot(raw: Optional[str]) -> str:
    """Lowercase/trim a slot or category; '' stays '' (honest unknown)."""
    return (raw or "").strip().lower()


def slot_to_polyvore(slot: Optional[str]) -> str:
    """Map a CONFIT slot (or pass-through Polyvore category) to the model's
    training vocabulary."""
    s = normalize_slot(slot)
    if s in SLOT_TO_POLYVORE:
        return SLOT_TO_POLYVORE[s]
    if s in ("tops", "bottoms", "shoes", "outerwear", "all-body", "accessories", "bags"):
        return s
    return "unknown"


def analyze_types(slots: List[str]) -> Dict[str, Any]:
    """Type-aware structural analysis over normalized CONFIT slots.

    Deterministic, rule-based, honest: this is the practical 'type-aware'
    companion to the model score (TATTOO evaluation philosophy — a score
    must be explainable by type consistency). It never fabricates a model
    output; it describes the outfit's slot structure.
    """
    normalized = [normalize_slot(s) for s in slots]
    counts: Dict[str, int] = {}
    for s in normalized:
        if s:
            counts[s] = counts.get(s, 0) + 1

    duplicate_slots = sorted(s for s, n in counts.items() if n > 1 and s in EXCLUSIVE_SLOTS)

    has_full_body = FULL_BODY_ALTERNATIVE in counts
    has_upper = "upper_inner" in counts or "upper_outer" in counts
    has_lower = "lower" in counts
    has_footwear = "footwear" in counts

    # Coverage: full-body garments replace the top+bottom pair.
    if has_full_body:
        missing_essentials = [] if has_footwear else ["footwear"]
    else:
        missing_essentials = [s for s in ESSENTIAL_SLOTS if s not in counts]

    warnings: List[str] = []
    for s in duplicate_slots:
        warnings.append(
            f"Two items compete for the same slot ('{s}'); layering conflicts "
            f"usually lower real-world compatibility."
        )
    if has_full_body and (has_upper and has_lower):
        warnings.append(
            "A full-body garment is combined with separate top and bottom "
            "pieces; verify this is intentional layering."
        )
    if not normalized or all(not s for s in normalized):
        warnings.append(
            "No recognisable garment slots were supplied; the structural "
            "analysis could not run."
        )

    return {
        "slots": normalized,
        "polyvore_categories": [slot_to_polyvore(s) for s in normalized],
        "duplicate_slots": duplicate_slots,
        "coverage": {
            "has_upper": has_upper,
            "has_lower_or_full_body": has_lower or has_full_body,
            "has_footwear": has_footwear,
            "missing_essentials": missing_essentials,
        },
        "warnings": warnings,
    }


# ── TATTOO-style aesthetic axes (training-free, deterministic) ─────────

#: Anchor phrases per TATTOO axis (arXiv:2509.23242 popularised color /
#: style / occasion / season / material / balance). Phrases carry a garment
#: suffix because bare single words sit in poorly-calibrated regions of
#: CLIP text space.
AXIS_ANCHORS: Dict[str, List[str]] = {
    "color": [
        "black garment", "white garment", "grey garment", "navy blue garment",
        "beige garment", "brown garment", "red garment", "green garment",
        "blue garment", "yellow garment", "pink garment", "purple garment",
    ],
    "style": [
        "minimalist outfit", "streetwear outfit", "classic tailored outfit",
        "bohemian outfit", "sporty athleisure outfit", "vintage outfit",
        "smart casual outfit", "glamorous evening outfit",
    ],
    "season": [
        "spring outfit", "summer outfit", "autumn outfit", "winter outfit",
    ],
    "occasion": [
        "office workwear outfit", "casual weekend outfit",
        "evening party outfit", "beach resort outfit", "formal event outfit",
        "outdoor sport outfit",
    ],
    "material": [
        "cotton garment", "wool knit garment", "denim garment",
        "leather garment", "silk satin garment", "linen garment",
        "synthetic technical fabric garment",
    ],
    "balance": [
        "fitted silhouette", "relaxed loose fit", "oversized layered fit",
        "structured tailored fit", "flowing draped fit",
    ],
}

AXES_METHOD = "clip_text_anchor_projection"
AXES_INSPIRED_BY = (
    "TATTOO (arXiv:2509.23242) aesthetic axes — training-free profiling. "
    "This is a CLIP-anchor adaptation, NOT the paper's MLLM pipeline."
)

#: CLIP's own logit scale (exp(100·cos)) — standard CLIP softmax temperature.
_CLIP_LOGIT_SCALE = 100.0


def axis_profiles_to_coherence(profiles: List[List[float]]) -> Optional[float]:
    """Mean pairwise cosine similarity of per-item anchor profiles → [0, 1].

    Pure numpy-free math so it is testable everywhere. Returns None when
    there are fewer than 2 items (pairwise agreement is undefined — reported
    as null, never as a fake 0 or 1).
    """
    if len(profiles) < 2:
        return None
    vecs = []
    for p in profiles:
        norm = math.sqrt(sum(x * x for x in p))
        if norm == 0:
            return None
        vecs.append([x / norm for x in p])
    total = 0.0
    pairs = 0
    for i in range(len(vecs)):
        for j in range(i + 1, len(vecs)):
            total += sum(a * b for a, b in zip(vecs[i], vecs[j]))
            pairs += 1
    if pairs == 0:
        return None
    # Cosine of non-negative distributions is in [0, 1]; clamp for safety.
    return max(0.0, min(1.0, total / pairs))


def summarize_axes(axis_scores: Dict[str, Optional[float]]) -> Dict[str, Any]:
    """Round axis coherences into the response block (0-100 ints or null)."""
    rendered = {}
    known: List[int] = []
    for axis, value in axis_scores.items():
        if value is None:
            rendered[axis] = None
        else:
            score = int(round(value * 100))
            rendered[axis] = score
            known.append(score)
    return {
        "method": AXES_METHOD,
        "inspired_by": AXES_INSPIRED_BY,
        "axes": rendered,
        "overall": (int(round(sum(known) / len(known))) if known else None),
        "disclaimer": (
            "Advisory aesthetic-consistency signals derived from the model's "
            "own FashionCLIP encoder. They do not enter the compatibility "
            "score and are not the TATTOO MLLM pipeline."
        ),
    }


# ──────────────────────────────────────────────────────────────────────
# Refusals
# ──────────────────────────────────────────────────────────────────────


class OutfitEngineRefused(Exception):
    """Honest refusal — maps to HTTP 422 with {error: {code, message}}."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _validate_item_counts(outfit_len: int, candidates_len: Optional[int],
                          mode: str) -> None:
    if mode == "compatibility":
        if outfit_len < MIN_COMPAT_ITEMS:
            raise OutfitEngineRefused(
                "INVALID_OUTFIT",
                f"Compatibility needs at least {MIN_COMPAT_ITEMS} items; "
                f"got {outfit_len}.")
        if outfit_len > MAX_COMPAT_ITEMS:
            raise OutfitEngineRefused(
                "TOO_MANY_ITEMS",
                f"Compatibility accepts at most {MAX_COMPAT_ITEMS} items; "
                f"got {outfit_len}.")
    else:  # fill-in-the-blank
        if outfit_len < MIN_FITB_OUTFIT_ITEMS:
            raise OutfitEngineRefused(
                "INVALID_OUTFIT",
                f"Fill-in-the-blank needs at least {MIN_FITB_OUTFIT_ITEMS} "
                f"outfit item; got {outfit_len}.")
        if outfit_len > MAX_FITB_OUTFIT_ITEMS:
            raise OutfitEngineRefused(
                "TOO_MANY_ITEMS",
                f"Fill-in-the-blank accepts at most {MAX_FITB_OUTFIT_ITEMS} "
                f"outfit items; got {outfit_len}.")
        if candidates_len is None or candidates_len < 1:
            raise OutfitEngineRefused(
                "NO_CANDIDATES",
                "Fill-in-the-blank needs at least one candidate item.")
        if candidates_len > MAX_FITB_CANDIDATES:
            raise OutfitEngineRefused(
                "TOO_MANY_CANDIDATES",
                f"Fill-in-the-blank accepts at most {MAX_FITB_CANDIDATES} "
                f"candidates; got {candidates_len}.")


# ──────────────────────────────────────────────────────────────────────
# Model layer (torch + vendored upstream — imported lazily)
# ──────────────────────────────────────────────────────────────────────

import os as _os

#: Weights come from the Modal volume `confit-outfit-weights` (uploaded
#: 2026-10-03, sha256s in vendor/outfit-transformer/UPSTREAM_PROVENANCE.txt)
#: mounted read-only at /volume — no runtime downloads, no Google Drive
#: quota games at container start.
_CKPT_DIR = _os.environ.get("OUTFIT_WEIGHTS_DIR", "/volume")
_COMPAT_CKPT = f"{_CKPT_DIR}/checkpoints/compatibility_clip_best.pth"
_COMPLEMENTARY_CKPT = f"{_CKPT_DIR}/checkpoints/complementary_clip_best.pth"

_MODELS_DISCLOSURE = {
    "outfit_transformer": {
        "implementation": "bigohofone/outfit-transformer @ eef4be5 (MIT)",
        "architecture": "OutfitCLIPTransformer: frozen FashionCLIP item "
                        "encoder + 6-layer transformer (Polyvore-trained)",
        "paper": "OutfitTransformer (Sarkar et al., CVPRW'22 / WACV'23)",
        "reported_performance": {
            "compatibility_auc": 0.95,
            "fitb_accuracy": 0.6924,
            "note": "+CLIP variant, Polyvore; upstream-reported",
        },
        "license": "mit",
        "commercial": True,
    },
    "fashionclip": {
        "model": "patrickjohncyh/fashion-clip (MIT)",
        "role": "item encoder inside OutfitCLIPTransformer (same model "
                "family as confit-tagging-worker; no new embedding stack)",
        "bias_note": "trained on Farfetch white-background product photos; "
                     "non-product photos score less reliably",
        "license": "mit",
        "commercial": True,
    },
}

_TRAINING_NOTE = (
    "Scores are compatibility in the sense of the Polyvore dataset the "
    "model was trained on (curated fashion outfits), not a guarantee of "
    "taste. Use as guidance."
)


class OutfitEngine:
    """Loads both OutfitTransformer checkpoints and answers CP + FITB.

    Compatibility model loads eagerly (hot path); the complementary model
    loads lazily on the first FITB call under a lock — a container that only
    ever scores outfits never pays the second 769MB load.
    """

    def __init__(self, device: str = "cpu"):
        self.device = device
        self.compat_model = None
        self.complementary_model = None
        self._compat_lock = threading.Lock()
        self._complementary_lock = threading.Lock()
        self._anchor_cache: Dict[str, Any] = {}

    # ── loading ────────────────────────────────────────────────────────

    def _load_upstream(self, checkpoint: str):
        import torch
        from src.models.load import load_model

        # Upstream load_model ends with `model.to(rank)` where rank is an
        # INT (0). torch interprets Module.to(int) as cuda:<int>, which
        # explodes on CPU-only containers ("Cannot access accelerator
        # device when none is available"). The vendor tree stays pristine,
        # so the worker applies a scoped shim: int device args are remapped
        # to the CPU device for the duration of the load call only.
        _orig_to = torch.nn.Module.to

        def _cpu_safe_to(self, *args, **kwargs):
            args = tuple("cpu" if isinstance(a, int) else a for a in args)
            if isinstance(kwargs.get("device"), int):
                kwargs["device"] = "cpu"
            return _orig_to(self, *args, **kwargs)

        torch.nn.Module.to = _cpu_safe_to
        try:
            model = load_model("clip", checkpoint=checkpoint)
        finally:
            torch.nn.Module.to = _orig_to
        model.to(self.device)
        model.eval()
        torch.set_grad_enabled(False)
        return model

    def load_compat(self) -> None:
        with self._compat_lock:
            if self.compat_model is not None:
                return
            if not self._checkpoint_present(_COMPAT_CKPT):
                raise OutfitEngineRefused(
                    "CHECKPOINT_MISSING",
                    "Compatibility checkpoint is not mounted at "
                    f"{_COMPAT_CKPT}.")
            self.compat_model = self._load_upstream(_COMPAT_CKPT)

    def load_complementary(self) -> None:
        with self._complementary_lock:
            if self.complementary_model is not None:
                return
            if not self._checkpoint_present(_COMPLEMENTARY_CKPT):
                raise OutfitEngineRefused(
                    "CHECKPOINT_MISSING",
                    "Complementary checkpoint is not mounted at "
                    f"{_COMPLEMENTARY_CKPT}.")
            self.complementary_model = self._load_upstream(_COMPLEMENTARY_CKPT)

    @staticmethod
    def _checkpoint_present(path: str) -> bool:
        import os
        return os.path.exists(path)

    @property
    def compat_loaded(self) -> bool:
        return self.compat_model is not None

    @property
    def complementary_loaded(self) -> bool:
        return self.complementary_model is not None

    # ── item construction ──────────────────────────────────────────────

    @staticmethod
    def _build_item(payload: Dict[str, Any], image) -> Any:
        """API item dict + decoded PIL image → upstream FashionItem.

        The description fed to the text encoder is the real product title
        plus the mapped Polyvore category — never invented text.
        """
        from src.data.datatypes import FashionItem

        slot = normalize_slot(payload.get("slot") or payload.get("category"))
        category = slot_to_polyvore(slot)
        title = (payload.get("title") or "").strip()
        description = " ".join(x for x in (category, title) if x and x != "unknown")
        return FashionItem(
            category=category,
            image=image,
            description=description,
        )

    # ── compatibility ──────────────────────────────────────────────────

    def score_compatibility(
        self, items: List[Dict[str, Any]], images: List[Any],
        include_axes: bool = True,
    ) -> Dict[str, Any]:
        """Score one outfit (sigmoid 0-1) + type-aware block + advisory axes."""
        import numpy as np
        import torch

        _validate_item_counts(len(items), None, mode="compatibility")
        self.load_compat()

        from src.data.datatypes import FashionCompatibilityQuery

        fashion_items = [
            self._build_item(p, img) for p, img in zip(items, images)
        ]

        t0 = time.time()
        query = [FashionCompatibilityQuery(outfit=fashion_items)]
        logits = self.compat_model.predict_score(query)
        score = float(torch.sigmoid(logits)[0].item())
        model_seconds = round(time.time() - t0, 2)

        slots = [normalize_slot(p.get("slot") or p.get("category"))
                 for p in items]
        type_aware = analyze_types(slots)

        axes_block: Optional[Dict[str, Any]] = None
        if include_axes and len(fashion_items) >= 2:
            t1 = time.time()
            axis_scores = self._compute_axes(images)
            axes_block = summarize_axes(axis_scores)
            axes_block["compute_seconds"] = round(time.time() - t1, 2)

        return {
            "status": "ok",
            "engine": "outfit_transformer_clip_cpu",
            "compatibility_score": round(score, 4),
            "compatibility_score_0_100": int(round(score * 100)),
            "score_interpretation": (
                "Probability the outfit reads as a coherent Polyvore-style "
                "look, per the compatibility model."
            ),
            "items_count": len(fashion_items),
            "type_aware": type_aware,
            "aesthetic_axes": axes_block,
            "models": _MODELS_DISCLOSURE,
            "training_data_note": _TRAINING_NOTE,
            "timings": {"model_seconds": model_seconds},
        }

    # ── fill in the blank ──────────────────────────────────────────────

    def fill_in_the_blank(
        self,
        outfit: List[Dict[str, Any]], outfit_images: List[Any],
        candidates: List[Dict[str, Any]], candidate_images: List[Any],
        target_slot: Optional[str] = None,
        top_k: int = 5,
    ) -> Dict[str, Any]:
        """Complete an outfit: embed the partial look + target category,
        rank candidates by cosine similarity to the query embedding."""
        import numpy as np
        import torch

        _validate_item_counts(len(outfit), len(candidates), mode="fitb")
        self.load_complementary()

        from src.data.datatypes import FashionComplementaryQuery, FashionItem

        t0 = time.time()
        outfit_items = [
            self._build_item(p, img) for p, img in zip(outfit, outfit_images)
        ]
        target_category = slot_to_polyvore(target_slot)
        query = [FashionComplementaryQuery(
            outfit=outfit_items, category=target_category)]
        query_emb = self.complementary_model.embed_query(query)[0]

        cand_items = [
            self._build_item(p, img) for p, img in zip(candidates, candidate_images)
        ]
        # embed_item batch-embeds through the complementary model's own
        # encoder — the exact space its training contrastive objective used.
        item_embs = self.complementary_model.embed_item(cand_items)
        sims = torch.nn.functional.cosine_similarity(
            query_emb.unsqueeze(0), item_embs, dim=-1)
        order = torch.argsort(sims, descending=True)

        top_k = max(1, min(int(top_k), len(candidates)))
        ranked = []
        for rank_pos, idx in enumerate(order[:top_k].tolist(), start=1):
            cand = candidates[idx]
            ranked.append({
                "id": cand.get("id"),
                "rank": rank_pos,
                "similarity": round(float(sims[idx].item()), 4),
            })

        return {
            "status": "ok",
            "engine": "outfit_transformer_clip_cpu",
            "target_category_used": target_category,
            "outfit_items_count": len(outfit_items),
            "candidates_count": len(candidates),
            "ranked": ranked,
            "models": _MODELS_DISCLOSURE,
            "training_data_note": _TRAINING_NOTE,
            "disclaimer": (
                "Ranking is single-step complementary retrieval (CIR): "
                "cosine similarity in the model's learned space, not a "
                "guarantee of taste."
            ),
            "timings": {"model_seconds": round(time.time() - t0, 2)},
        }

    # ── TATTOO-style axes via the compat model's own encoder ───────────

    def _anchor_embeddings(self, axis: str):
        """Cache normalized text embeddings for one axis's anchors."""
        if axis in self._anchor_cache:
            return self._anchor_cache[axis]
        import torch

        model = self.compat_model
        texts = [[a] for a in AXIS_ANCHORS[axis]]  # List[List[str]]
        # text_enc returns [K, 1, D] (K single-text "outfits"); squeeze the
        # sequence dim -> [K, D] in CLIP's contrastive text space.
        emb = model.item_enc.text_enc(texts, normalize=True)[:, 0, :]
        emb = torch.nn.functional.normalize(emb, p=2, dim=-1)
        self._anchor_cache[axis] = emb
        return emb

    def _compute_axes(self, images: List[Any]) -> Dict[str, Optional[float]]:
        """Per-axis coherence: softmax anchor profile per item, then mean
        pairwise cosine of profiles. Deterministic; no randomness."""
        import numpy as np
        import torch

        model = self.compat_model
        # Image embeddings through the same frozen encoder the score used.
        img_embs = model.item_enc.image_enc(
            [[np.asarray(img.convert("RGB"))] for img in images],
            normalize=True,
        )[:, 0, :]  # [N, D]
        img_embs = torch.nn.functional.normalize(img_embs, p=2, dim=-1)

        axis_scores: Dict[str, Optional[float]] = {}
        for axis in AXIS_ANCHORS:
            anchor_emb = self._anchor_embeddings(axis)  # [K, D]
            logits = img_embs @ anchor_emb.T * _CLIP_LOGIT_SCALE  # [N, K]
            profiles = torch.softmax(logits, dim=-1).cpu().numpy()
            axis_scores[axis] = axis_profiles_to_coherence(
                [profiles[i].tolist() for i in range(profiles.shape[0])]
            )
        return axis_scores
