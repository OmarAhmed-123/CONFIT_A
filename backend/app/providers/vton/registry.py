"""Virtual try-on engine registry: capability, licence tier and fallback order.

WHY A REGISTRY AND NOT AN `if` IN THE SERVICE
---------------------------------------------
Try-on has three independent axes that were previously entangled in
`VTON_ENGINE` (a single string) plus an unset `VTON_WORKER_URL`:

  1. CAN this engine render the garment category being asked for?
  2. MAY we use it, given where the product is in its life (pilot vs trading)?
  3. Is it UP right now?

Answering those in the service meant the answer to (2) — a licensing question
with legal consequences — was decided by whichever branch happened to run.
They are separated here so the licence gate is a data property that cannot be
skipped by taking a different code path.

THE LICENCE TIER IS THE POINT
-----------------------------
`backend/app/core/config.py` already records, honestly, that most open
virtual-try-on weights are CC BY-NC-SA — non-commercial — and that the project
forked FASHN specifically to strip a restricted human-parser so that ONE
engine (`fashn_vton_segfee`) is commercially clean.

CONFIT is currently in a pilot: no custom domain, no trading. Non-commercial
research weights are therefore appropriate *now* and must become unavailable
the moment the platform trades. That switch is `VTON_LICENSE_TIER`:

    pilot       -> every engine whose licence permits research/evaluation
    commercial  -> ONLY engines with commercial=True

Flipping one environment variable retires every non-commercial engine from the
chain. No code change, no redeploy of application logic, and — because
`resolve_chain` filters rather than reorders — no way to accidentally keep a
research engine as a "temporary" fallback.

MEASURED, NOT ASSUMED
---------------------
`verified` records whether THIS project has actually rendered an image with
the engine, with the date and the observation. An engine that has never been
run is not promoted to primary on the strength of its paper.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple


class GarmentCategory(str, Enum):
    """What is being put on the person.

    Deliberately coarse: these are the distinctions the available engines
    actually make. A finer taxonomy would imply routing precision that no
    current model delivers.
    """

    UPPER = "upper_body"
    LOWER = "lower_body"
    DRESS = "dress"
    OUTERWEAR = "outerwear"
    #: Bags, jewellery, eyewear, shoes. NO garment-VTON model handles these —
    #: they are trained on upper/lower/dress only. Kept as an explicit member
    #: so the router can REFUSE rather than silently render nonsense.
    ACCESSORY = "accessory"


class LicenseTier(str, Enum):
    PILOT = "pilot"
    COMMERCIAL = "commercial"


@dataclass(frozen=True)
class VtonEngineSpec:
    """One renderer, with the three facts needed to decide whether to call it."""

    key: str
    transport: str  # "hf_space" | "gpu_worker"
    #: Space id or worker route, depending on transport.
    endpoint: str
    #: Gradio api_name for hf_space engines.
    api_name: str
    license: str
    #: True only when the licence permits commercial use of the WHOLE chain.
    commercial: bool
    categories: Tuple[GarmentCategory, ...]
    #: Lower runs first.
    priority: int
    verified: Optional[str] = None
    notes: str = ""
    #: Engines needing an isolated garment cut-out rather than a lifestyle
    #: photo. CONFIT's catalogue is on-model photography, so this matters.
    requires_flatlay: bool = False
    extra: Dict[str, object] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# The engines. Every `verified` line below is an observation from this repo,
# not a citation.
# ---------------------------------------------------------------------------

_ENGINES: Tuple[VtonEngineSpec, ...] = (
    VtonEngineSpec(
        key="idm_vton_hf",
        transport="hf_space",
        endpoint="yisol/IDM-VTON",
        api_name="/tryon",
        license="CC BY-NC-SA 4.0 (weights + repo)",
        commercial=False,
        categories=(
            GarmentCategory.UPPER,
            GarmentCategory.DRESS,
            GarmentCategory.OUTERWEAR,
        ),
        priority=10,
        verified=(
            "2026-09-27: rendered in 24.0s from this workspace. Real CONFIT "
            "garment (product #5, silk slip dress) onto a stock person photo. "
            "Output inspected: face, hair, pose and background preserved; the "
            "person's black top was genuinely replaced. Tolerated an ON-MODEL "
            "garment photo with a background, which OOTDiffusion did not."
        ),
        notes=(
            "Primary pilot engine. Its built-in auto-masking is why it copes "
            "with lifestyle catalogue photography."
        ),
        extra={"denoise_steps": 30, "auto_mask": True},
    ),
    VtonEngineSpec(
        key="ootd_hf",
        transport="hf_space",
        endpoint="levihsu/OOTDiffusion",
        api_name="/process_dc",
        license="CC BY-NC-SA 4.0",
        commercial=False,
        categories=(
            GarmentCategory.UPPER,
            GarmentCategory.LOWER,
            GarmentCategory.DRESS,
        ),
        priority=30,
        verified=(
            "2026-09-27: responded in 15.4s but the OUTPUT WAS WRONG. Given "
            "the same on-model catalogue photo it baked the garment image's "
            "BACKGROUND — foliage and stonework — onto the person as fabric. "
            "Demoted below Leffa for that reason, and flagged requires_flatlay."
        ),
        notes=(
            "Only engine here that takes an explicit category, which makes it "
            "the natural fit for lower-body. Unusable on CONFIT's current "
            "imagery until garment cut-outs exist."
        ),
        requires_flatlay=True,
        extra={"n_steps": 20, "image_scale": 2.0},
    ),
    VtonEngineSpec(
        key="leffa_hf",
        transport="hf_space",
        endpoint="franciszzj/Leffa",
        api_name="/leffa_predict_vt",
        license="MIT (repo); SCHP / DensePose / Detectron2 chain unverified",
        commercial=False,  # conservative: unverified != permitted
        categories=(
            GarmentCategory.UPPER,
            GarmentCategory.LOWER,
            GarmentCategory.DRESS,
        ),
        priority=20,
        verified="2026-09-27: space reachable, endpoints enumerated. NOT yet rendered.",
        notes=(
            "Treated as non-commercial until the dependency chain is verified "
            "at checkout level. 'Unverified' is not 'permitted'."
        ),
    ),
    VtonEngineSpec(
        key="fashn_vton_segfee",
        transport="gpu_worker",
        endpoint="",  # resolved from VTON_WORKER_URL at call time
        api_name="",
        license="Apache-2.0 fork; NVIDIA non-commercial parser removed from runtime",
        commercial=True,
        categories=(
            GarmentCategory.UPPER,
            GarmentCategory.LOWER,
            GarmentCategory.DRESS,
            GarmentCategory.OUTERWEAR,
        ),
        priority=1,
        verified=(
            "Verified on a real A10 GPU in docs/VTON_COMMERCIAL_MIGRATION_REPORT: "
            "generated a real try-on image with parser_pre_import and "
            "parser_in_runtime both false."
        ),
        notes=(
            "The ONLY commercially clean engine. Highest priority whenever "
            "VTON_WORKER_URL is set; the sole engine surviving the commercial "
            "tier filter."
        ),
        requires_flatlay=True,
    ),
)

ENGINES: Dict[str, VtonEngineSpec] = {e.key: e for e in _ENGINES}


def resolve_chain(
    category: GarmentCategory,
    tier: LicenseTier,
    *,
    worker_configured: bool = False,
    allow_flatlay_only: bool = False,
) -> List[VtonEngineSpec]:
    """Ordered engines that may render `category` under `tier`.

    Filters, never reorders around, the licence gate: an engine excluded by
    tier cannot reappear lower down as a fallback.

    Args:
        category: what is being worn.
        tier: pilot (research weights allowed) or commercial (clean only).
        worker_configured: whether VTON_WORKER_URL is set. Without it the GPU
            engine cannot run, so it is dropped rather than returned and failed.
        allow_flatlay_only: include engines that need an isolated garment
            cut-out. Default False because the live catalogue is on-model
            photography and those engines demonstrably produce artefacts on it.

    Returns:
        Engines in priority order. EMPTY when nothing may serve — the caller
        must surface that honestly rather than substitute another category.
    """
    if category is GarmentCategory.ACCESSORY:
        # No garment-VTON model is trained on bags, jewellery or eyewear.
        # Returning an empty chain forces an honest refusal; routing an
        # accessory to a clothing model produces confident nonsense.
        return []

    out: List[VtonEngineSpec] = []
    for spec in _ENGINES:
        if category not in spec.categories:
            continue
        if tier is LicenseTier.COMMERCIAL and not spec.commercial:
            continue
        if spec.transport == "gpu_worker" and not worker_configured:
            continue
        if spec.requires_flatlay and not allow_flatlay_only:
            continue
        out.append(spec)
    return sorted(out, key=lambda s: s.priority)


def describe_chain(
    tier: LicenseTier, *, worker_configured: bool = False
) -> Dict[str, object]:
    """Operator-facing summary. Never used to make a routing decision."""
    return {
        "tier": tier.value,
        "worker_configured": worker_configured,
        "categories": {
            cat.value: [
                {
                    "engine": s.key,
                    "commercial": s.commercial,
                    "priority": s.priority,
                    "verified": bool(s.verified),
                }
                for s in resolve_chain(
                    cat, tier, worker_configured=worker_configured,
                    allow_flatlay_only=True,
                )
            ]
            for cat in GarmentCategory
        },
    }


#: Category inference from a product's own taxonomy. Conservative: anything
#: unrecognised becomes ACCESSORY, which REFUSES rather than guessing a body
#: region and rendering a garment onto the wrong part of the person.
_CATEGORY_HINTS: Sequence[Tuple[GarmentCategory, Tuple[str, ...]]] = (
    (GarmentCategory.DRESS, ("dress", "gown", "kaftan", "abaya", "jumpsuit")),
    (GarmentCategory.OUTERWEAR, ("coat", "jacket", "blazer", "trench", "tuxedo", "overcoat")),
    (GarmentCategory.LOWER, ("trouser", "pant", "jean", "skirt", "short", "chino", "legging")),
    (GarmentCategory.UPPER, ("shirt", "top", "tee", "t-shirt", "blouse", "knit",
                             "sweater", "jumper", "hoodie", "polo", "cardigan")),
    (GarmentCategory.ACCESSORY, ("bag", "clutch", "tie", "necktie", "shoe", "oxford",
                                 "sneaker", "boot", "belt", "scarf", "watch",
                                 "sunglass", "jewel", "earring", "necklace", "hat")),
)


#: The project's OWN canonical VTON slots (tryon_service.CATEGORY_TO_VTON_SLOT)
#: mapped onto engine categories.
#:
#: This is the authoritative signal and must be preferred over text inference.
#: The service builds garment dicts as
#: ``{"product_id", "slot_type", "image_base64"}`` — with NO title and NO
#: category name — so inferring from text saw only `None` and fell through to
#: the ACCESSORY default, which refuses. Production therefore declined to
#: render a DRESS with "no engine may render 'accessory'", while the same
#: garment rendered fine locally because the test harness passed titles.
#:
#: Deriving a category that the pipeline already computed was the mistake;
#: this maps it instead.
SLOT_TO_CATEGORY: Dict[str, GarmentCategory] = {
    "upper_inner": GarmentCategory.UPPER,
    "upper_outer": GarmentCategory.OUTERWEAR,
    "lower": GarmentCategory.LOWER,
    "dress": GarmentCategory.DRESS,
    "footwear": GarmentCategory.ACCESSORY,
    "accessory": GarmentCategory.ACCESSORY,
}


def category_from_slot(slot: Optional[str]) -> Optional[GarmentCategory]:
    """Map a canonical VTON slot to an engine category, or None if unknown.

    Returns None rather than a default so the caller can fall back to text
    inference deliberately, instead of silently treating an unrecognised slot
    as an accessory.
    """
    if not slot:
        return None
    return SLOT_TO_CATEGORY.get(str(slot).strip().lower())


def infer_category(*texts: Optional[str]) -> GarmentCategory:
    """Best-effort category from a product title / category name / tags.

    Checked most-specific-first: "tuxedo dinner jacket" must resolve to
    OUTERWEAR, not match "dress" inside some other word. Unknown input returns
    ACCESSORY so the pipeline declines instead of inventing a body region.
    """
    haystack = " ".join(t.lower() for t in texts if t)
    if not haystack.strip():
        return GarmentCategory.ACCESSORY
    for category, keywords in _CATEGORY_HINTS:
        if any(k in haystack for k in keywords):
            return category
    return GarmentCategory.ACCESSORY
