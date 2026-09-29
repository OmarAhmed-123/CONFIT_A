"""NVIDIA NIM model registry — CONFIT role -> verified model binding.

WHY THIS FILE EXISTS
--------------------
On 2026-09-27 a live probe of ``integrate.api.nvidia.com`` proved that BOTH
NVIDIA models hardcoded in ``providers/orchestrator.py`` are dead::

    meta/llama-3.1-70b-instruct    -> HTTP 410 Gone (EOL 2026-08-26T09:00:00Z)
    nvidia/nemotron-nano-12b-v2-vl -> HTTP 410 Gone (EOL 2026-08-26T09:00:00Z)

That means the "NVIDIA" leg of the multi-provider failover chain has been a
guaranteed no-op since 2026-08-26 — every stylist request silently paid a
round-trip and then fell through to Groq/Gemini. Pinning model ids inline is
what allowed that to rot unnoticed, so model selection now lives HERE, in one
reviewable table, keyed by the CONFIT capability that consumes it.

HONESTY CONTRACT (matches MODEL_REGISTRY.json)
----------------------------------------------
Every ``evidence`` string below is a MEASURED observation from the 2026-09-27
probe against the real endpoint — not a vendor claim, not an estimate. A model
with no measurement does not get a production role; it goes to
``UNROUTED_MODELS`` with the reason. ``scripts/verify_nvidia_models.py``
re-runs the probe and fails when reality and this table disagree.

ROLE != MODEL. Callers ask for a ROLE (``ModelRole.STYLIST_CHAT``); the
registry answers with an ordered chain of candidates. Swapping a model is a
one-line change here and needs no edit in any service.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional, Tuple

CHAT_COMPLETIONS_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
EMBEDDINGS_URL = "https://integrate.api.nvidia.com/v1/embeddings"
MODELS_URL = "https://integrate.api.nvidia.com/v1/models"


class ModelRole(str, Enum):
    """The CONFIT capabilities that are allowed to consume an NVIDIA model.

    A role is a PRODUCT surface, not a model family. If a new role is needed,
    it is added here with a measured candidate chain — services never name a
    raw model id.
    """

    #: G2-02 Conversational AI Stylist — user-facing prose, latency-critical.
    STYLIST_CHAT = "stylist_chat"
    #: Wardrobe auto-tagging + Visual Search attribute extraction (vision->JSON).
    GARMENT_VISION = "garment_vision"
    #: Upload / chat moderation before anything is persisted or shown.
    CONTENT_SAFETY = "content_safety"
    #: Arabic <-> English product & stylist localisation (MENA market).
    TRANSLATION = "translation"
    #: Dense vectors for semantic catalogue / wardrobe retrieval.
    EMBEDDING = "embedding"
    #: Offline/Celery analytics prose: brand reports, gap analysis. Not online.
    BATCH_REASONING = "batch_reasoning"
    #: Offline marketing / mood-board copy. Not online.
    CREATIVE_COPY = "creative_copy"
    #: Cheap deterministic structured helpers (normalise, classify, extract).
    UTILITY_JSON = "utility_json"


@dataclass(frozen=True)
class ModelSpec:
    """One verified model binding.

    Attributes
    ----------
    model_id:
        The exact string sent as ``"model"``. Must exist in ``GET /v1/models``.
    endpoint:
        Full URL. Embeddings do NOT share the chat endpoint.
    params:
        Request parameters proven necessary for CORRECT output. These are not
        cosmetic defaults — see ``notes`` for the failure each one prevents.
    supports_vision:
        Measured with a real image URL, not read off a model card.
    measured_latency_s:
        (best, worst) wall-clock seconds observed on 2026-09-27.
    evidence:
        What was actually run and what came back.
    slot_key_env:
        The env var holding the key that shipped with this model. Used as the
        PREFERRED key; the pool supplies overflow keys on 429/503.
    """

    model_id: str
    endpoint: str
    params: Mapping[str, Any] = field(default_factory=dict)
    supports_vision: bool = False
    measured_latency_s: Tuple[float, float] = (0.0, 0.0)
    evidence: str = ""
    slot_key_env: Optional[str] = None
    notes: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# Shared parameter fragments
# ─────────────────────────────────────────────────────────────────────────────

# Nemotron-3 reasoning models emit chain-of-thought into `reasoning_content`.
# Left enabled with a small max_tokens they burn the whole budget thinking and
# return EMPTY content — the exact `ai_provider_empty_response` incident the
# orchestrator already logs for Gemini. Measured: nemotron-3.5-lightning with
# thinking ON returned 3000 tokens of leaked "Here is a thinking:" prose in
# 98.0s; with `enable_thinking: false` it returned clean prose in 3.6s.
_NO_THINKING = {"chat_template_kwargs": {"enable_thinking": False}}


# ─────────────────────────────────────────────────────────────────────────────
# ROLE -> ordered candidate chain (index 0 = primary, rest = failover)
# ─────────────────────────────────────────────────────────────────────────────

ROLE_CHAINS: Dict[ModelRole, List[ModelSpec]] = {
    # ── G2-02 AI Stylist ─────────────────────────────────────────────────────
    # Selection rule: the shopper is waiting, so p50 latency gates entry, and
    # grounding quality decides the order. AI_PROVIDER_TIMEOUT_SECONDS is 4.0s
    # today, so anything above ~5s cannot be primary without a config change.
    ModelRole.STYLIST_CHAT: [
        ModelSpec(
            model_id="nvidia/nemotron-3-ultra-550b-a55b",
            endpoint=CHAT_COMPLETIONS_URL,
            params={"temperature": 0.6, "top_p": 0.95},
            measured_latency_s=(0.8, 4.1),
            slot_key_env="NVIDIA_KEY_NEMOTRON_3_ULTRA_550B_A55B",
            evidence=(
                "2026-09-27, real CONFIT stylist system+user prompt (3 grounded "
                "catalogue items, $385 total): 200 in 4.1s / 126 completion "
                "tokens. Output named every item, honoured the 2-3 sentence "
                "cap, stated the budget correctly and invented nothing."
            ),
            notes=(
                "Best measured grounding-per-second of the 14 chat models "
                "probed. Does NOT leak reasoning into content at default "
                "settings, so no enable_thinking guard is required."
            ),
        ),
        ModelSpec(
            model_id="nvidia/nemotron-3-super-120b-a12b",
            endpoint=CHAT_COMPLETIONS_URL,
            params={"temperature": 0.6, "top_p": 0.95},
            measured_latency_s=(2.4, 3.5),
            slot_key_env="NVIDIA_KEY_NEMOTRON_3_SUPER_120B_A12B",
            evidence=(
                "2026-09-27, same prompt: 200 in 3.5s / 256 tokens. Correct "
                "grounding and budget; slightly more verbose than Ultra."
            ),
            notes="Fastest high-quality option — first failover, also the cheapest primary if Ultra saturates.",
        ),
        ModelSpec(
            model_id="moonshotai/kimi-k3",
            endpoint=CHAT_COMPLETIONS_URL,
            params={"temperature": 0.6, "top_p": 0.95, "max_tokens": 3000},
            supports_vision=True,
            measured_latency_s=(8.6, 14.9),
            slot_key_env="NVIDIA_KEY_KIMI_K3",
            evidence=(
                "2026-09-27, same prompt: 200 in 14.9s / 110 tokens; the "
                "richest prose of the set. Vision verified separately."
            ),
            notes=(
                "Third, not first: 14.9s exceeds the stylist latency budget. "
                "Needs a generous max_tokens — with max_tokens=4096 and a "
                "trivial prompt it returned reasoning-only content."
            ),
        ),
    ],

    # ── Wardrobe auto-tagging / Visual Search attributes ─────────────────────
    # These replace the Gemini-dependent vision path documented in
    # MODEL_REGISTRY.json, and sit ALONGSIDE the self-hosted Qwen2.5-VL worker.
    ModelRole.GARMENT_VISION: [
        ModelSpec(
            model_id="google/diffusiongemma-26b-a4b-it",
            endpoint=CHAT_COMPLETIONS_URL,
            # enable_thinking is REQUIRED here, and it is the opposite of the
            # Nemotron guard. Measured 2026-09-27 on an identical prompt
            # ("Reply with exactly: OK"): WITHOUT the flag -> HTTP 200,
            # finish_reason=stop, content="" (silently empty, 0.9s); WITH the
            # flag -> content="OK" (1.5s). A diffusion LLM needs its denoising
            # pass to populate content on short prompts. NVIDIA's own sample
            # snippet ships this flag; dropping it produces phantom empties.
            params={"temperature": 0.2, "top_p": 0.95, "max_tokens": 2048,
                    "chat_template_kwargs": {"enable_thinking": True}},
            supports_vision=True,
            measured_latency_s=(1.7, 2.8),
            slot_key_env="NVIDIA_KEY_DIFFUSIONGEMMA_26B_A4B_IT",
            evidence=(
                "2026-09-27, real garment photo + the CONFIT strict-JSON "
                "tagging prompt: 200 in 1.7s, returned clean parseable JSON "
                "with no markdown fence — "
                '{"category":"suit","subcategory":"three-piece suit",'
                '"color_family":"blue","pattern":"windowpane",'
                '"formality":"formal","season":"all seasons","confidence":0.98}'
            ),
            notes=(
                "Fastest correct VLM measured and the only one that emitted "
                "bare JSON. 5x faster than the Qwen worker's 5.1s warm path. "
                "See the enable_thinking comment above — it is load-bearing."
            ),
        ),
        ModelSpec(
            model_id="moonshotai/kimi-k3",
            endpoint=CHAT_COMPLETIONS_URL,
            params={"temperature": 0.2, "top_p": 0.95, "max_tokens": 2048},
            supports_vision=True,
            measured_latency_s=(8.6, 10.3),
            slot_key_env="NVIDIA_KEY_KIMI_K3",
            evidence=(
                "2026-09-27, same garment + prompt: 200 in 10.3s, clean JSON, "
                "and the most precise pattern label of the set "
                '("windowpane check" vs gemma-4\'s looser "plaid").'
            ),
            notes="Accuracy-first failover; use as primary for admin catalogue enrichment where latency is irrelevant.",
        ),
        ModelSpec(
            model_id="nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
            endpoint=CHAT_COMPLETIONS_URL,
            params={"temperature": 0.2, "top_p": 0.95, "max_tokens": 2048,
                    "reasoning_budget": 1024},
            supports_vision=True,
            measured_latency_s=(0.8, 6.8),
            slot_key_env="NVIDIA_KEY_NEMOTRON_3_NANO_OMNI_30B_A3B_REASONING",
            evidence=(
                "2026-09-27: correct single-word vision answer in 6.8s, BUT "
                "returned HTTP 503 'ResourceExhausted: Worker local total "
                "request limit reached (16/16)' on two separate concurrent "
                "runs."
            ),
            notes=(
                "TERTIARY ONLY. The 16-request worker ceiling makes it unsafe "
                "as a primary under real traffic; the client's 503 handling "
                "rotates off it automatically."
            ),
        ),
    ],

    # ── Moderation ───────────────────────────────────────────────────────────
    ModelRole.CONTENT_SAFETY: [
        ModelSpec(
            model_id="nvidia/nemotron-3.5-content-safety",
            endpoint=CHAT_COMPLETIONS_URL,
            params={"temperature": 0.2, "top_p": 0.7, "max_tokens": 512,
                    "chat_template_kwargs": {"request_categories": "/categories"}},
            supports_vision=True,
            measured_latency_s=(0.4, 0.5),
            slot_key_env="NVIDIA_KEY_NEMOTRON_3_5_CONTENT_SAFETY",
            evidence=(
                "2026-09-27: benign text -> 'User Safety: safe' in 0.4s; "
                "'should I starve myself' -> 'User Safety: unsafe / Safety "
                "Categories: Suicide and Self Harm' in 0.5s; a real image URL "
                "-> 'User Safety: safe' in 0.5s."
            ),
            notes=(
                "Closes the MODEL_REGISTRY.json 'image-moderation: NOT "
                "REQUIRED (optional P2)' gap at 0.5s — cheap enough to run "
                "inline on every wardrobe upload and every stylist turn. "
                "Body-image self-harm detection matters specifically for a "
                "fit/measurement product."
            ),
        ),
    ],

    # ── Arabic localisation (Giza/MENA market) ───────────────────────────────
    ModelRole.TRANSLATION: [
        # PRIMARY for INBOUND query translation (added 2026-09-29).
        #
        # riva-translate is a purpose-built translator and is still correct for
        # OUTBOUND prose (EN->AR), where fluency is what matters. It is WRONG
        # for inbound shopping queries, measured on the live endpoint:
        #
        #   'فستان سواريه أحمر'  -> "Red Swarovski Dress"   (brand invented)
        #   'بدلة شغل كلاسيك'    -> "Classic work trousers" (suit -> trousers)
        #   'فرح مسائي'          -> "evening party"         (wedding lost)
        #
        # It also ignores the system turn, so a domain glossary cannot be
        # supplied to it. Each of those errors changes WHICH GARMENT the
        # catalogue search then looks for, so the shopper is answered about a
        # different product than the one they asked for.
        #
        # nemotron-3-super follows the system turn and got all three right:
        #   -> "evening wedding, not too formal" / "work suit" / "evening gown"
        # measured 0.89-1.09s on the same calls.
        ModelSpec(
            model_id="nvidia/nemotron-3-super-120b-a12b",
            endpoint=CHAT_COMPLETIONS_URL,
            params={
                "temperature": 0.0,
                "max_tokens": 160,
                "chat_template_kwargs": {"enable_thinking": False},
            },
            measured_latency_s=(0.89, 1.09),
            slot_key_env="NVIDIA_KEY_NEMOTRON_3_SUPER_120B_A12B",
            evidence=(
                "2026-09-29, AR->EN of three real shopping queries: 0.89-1.09s, "
                "all three preserved the garment and occasion where "
                "riva-translate did not (wedding/suit/evening gown). One 503 "
                "observed under repeat calls, which the key rotation and the "
                "next entry in this chain cover."
            ),
            notes=(
                "Inbound AR->EN only. Obeys a glossary in the system turn, "
                "which is what makes dialect terms ('فرح', 'سواريه') survive."
            ),
        ),
        ModelSpec(
            model_id="nvidia/riva-translate-4b-instruct-v2",
            endpoint=CHAT_COMPLETIONS_URL,
            params={"temperature": 0.0, "max_tokens": 1024},
            measured_latency_s=(1.1, 1.1),
            slot_key_env="NVIDIA_KEY_RIVA_TRANSLATE_4B_INSTRUCT_V2",
            evidence=(
                "2026-09-27, EN->AR of a real styling sentence: 200 in 1.1s -> "
                "'البليزر المكسو بالكتان الأزرق يتناغم جيدًا مع بنطلون بيج.' "
                "Fluent MSA, correct fashion register."
            ),
            notes=(
                "OUTBOUND prose (EN->AR) only, where fluency is the goal. "
                "Measured UNSAFE for inbound shopping queries: it ignores the "
                "system turn, so no glossary can be supplied, and it renamed "
                "a garment and invented a brand in live tests. Kept in the "
                "chain as the failover for outbound work, not as the primary."
            ),
        ),
    ],

    # ── Retrieval vectors ────────────────────────────────────────────────────
    ModelRole.EMBEDDING: [
        ModelSpec(
            model_id="nvidia/nemotron-3-embed-1b",
            endpoint=EMBEDDINGS_URL,
            params={"encoding_format": "float", "input_type": "query"},
            measured_latency_s=(0.2, 0.2),
            slot_key_env="NVIDIA_KEY_NEMOTRON_3_EMBED_1B",
            evidence="2026-09-27: 200 in 0.2s, 2048-dimension float vector returned.",
            notes=(
                "MODEL_REGISTRY.json correctly records that NO vector "
                "retrieval exists in CONFIT today. This binding is therefore "
                "INFRASTRUCTURE-ONLY and must stay unused until a pgvector "
                "chain is explicitly approved — an unused embedding model is "
                "prohibited by the registry's own rule. "
                "NOTE: nvidia/nvclip is listed in the catalogue but returns "
                "404 'Not found for account' on these credentials — it is NOT "
                "available, so image-vector search is not currently possible."
            ),
        ),
    ],

    # ── Offline / Celery only ────────────────────────────────────────────────
    ModelRole.BATCH_REASONING: [
        ModelSpec(
            model_id="z-ai/glm-5.3",
            endpoint=CHAT_COMPLETIONS_URL,
            params={"temperature": 0.5, "top_p": 1, "max_tokens": 3000},
            measured_latency_s=(63.6, 73.3),
            slot_key_env="NVIDIA_KEY_GLM_5_3",
            evidence=(
                "2026-09-27, stylist prompt: 200 in 73.3s / 319 tokens. The "
                "most analytically detailed answer produced by any model in "
                "the set — and far too slow to put in front of a shopper."
            ),
            notes="Celery tasks only (brand reports, gap analysis, catalogue enrichment). Never bind to an HTTP request path.",
        ),
        ModelSpec(
            model_id="z-ai/glm-5.3-flash",
            endpoint=CHAT_COMPLETIONS_URL,
            params={"temperature": 0.5, "top_p": 1, "max_tokens": 3000},
            measured_latency_s=(22.0, 45.4),
            slot_key_env="NVIDIA_KEY_GLM_5_3_FLASH",
            evidence="2026-09-27: 200 in 45.4s / 341 tokens, quality close to glm-5.3.",
            notes="'flash' is a vendor label, not a measurement: 45.4s is still offline-only.",
        ),
    ],

    ModelRole.CREATIVE_COPY: [
        ModelSpec(
            model_id="meta/muse-glimmer-30b",
            endpoint=CHAT_COMPLETIONS_URL,
            params={"temperature": 1.0, "top_p": 0.95, "max_tokens": 3000,
                    "reasoning_effort": "high"},
            measured_latency_s=(9.7, 56.9),
            slot_key_env="NVIDIA_KEY_MUSE_GLIMMER_30B",
            evidence=(
                "2026-09-27: 200 in 56.9s / 743 tokens on the stylist prompt; "
                "accurate but heavily over-length for the 2-3 sentence "
                "contract. Re-probed 4x afterwards: 200 in 53.9s / 30.7s / "
                "43.8s / 9.7s. One isolated HTTP 404 with an EMPTY body was "
                "observed between those runs and did not reproduce — it was a "
                "transient routing blip, NOT an end-of-life, which is why the "
                "client retries a bodyless 404 on another key before "
                "condemning a model."
            ),
            notes=(
                "Long-form marketing / mood-board copy generated ahead of "
                "time. Not a stylist model. Also leaks reasoning_content, "
                "which the client strips."
            ),
        ),
    ],

    # ── Cheap structured helpers ─────────────────────────────────────────────
    ModelRole.UTILITY_JSON: [
        ModelSpec(
            model_id="nvidia/nemotron-3.5-lightning-30b-a3b",
            endpoint=CHAT_COMPLETIONS_URL,
            params={"temperature": 0.6, "top_p": 0.95, "max_tokens": 1024, **_NO_THINKING},
            measured_latency_s=(1.3, 3.6),
            slot_key_env="NVIDIA_KEY_NEMOTRON_3_5_LIGHTNING_30B_A3B",
            evidence=(
                "2026-09-27: WITHOUT the guard -> 98.0s and 3000 tokens of "
                "leaked 'Here is a thinking:' chain-of-thought as the visible "
                "answer. WITH enable_thinking=false -> clean one-sentence "
                "answer in 3.6s. Both measured on the same prompt."
            ),
            notes=(
                "The _NO_THINKING guard is load-bearing. Shipping this model "
                "without it would expose raw chain-of-thought to end users."
            ),
        ),
    ],
}


# ─────────────────────────────────────────────────────────────────────────────
# Models that were supplied but are deliberately NOT wired to any role.
# Recording the reason is what stops someone re-adding them next quarter.
# ─────────────────────────────────────────────────────────────────────────────

UNROUTED_MODELS: Dict[str, str] = {
    "deepseek-ai/deepseek-v4.1-flash": (
        "UNUSABLE (measured). 200 OK but 283.7s for a 2-token reply and 299.4s "
        "for one vision call, on separate runs. Despite the 'flash' name this "
        "is ~70x slower than nemotron-3-super. No CONFIT surface tolerates it."
    ),
    "poolside/laguna-xs-2.1": (
        "NOT A PRODUCT MODEL + UNAVAILABLE. It is a code-generation model, and "
        "CONFIT ships no code-generation feature. Both probe attempts returned "
        "HTTP 503 'ResourceExhausted: Worker local total request limit reached "
        "(174/32)'. Usable as a developer tool outside the app; never in it."
    ),
    "nvidia/ising-calibration-1.5-31b": (
        "OUT OF DOMAIN. Superconducting-qubit resonator-spectroscopy analysis. "
        "Asked to reply 'OK' it self-identified as \"NVIDIA's quantum "
        "calibration analysis model\". Zero overlap with fashion/fit. Two "
        "separate keys were supplied for it; both are kept in the pool as "
        "overflow credentials for other models."
    ),
    "nvidia/nemotron-voicechat": (
        "NOT ENTITLED. Absent from GET /v1/models, and POST returned 404 on "
        "/v1/chat/completions, /v1/audio/speech and /v1/realtime. The G2_G3 "
        "§2.2 voice stylist therefore stays on the browser Web Speech API. "
        "Key retained in the pool."
    ),
    "kumo-relational": (
        "BLOCKED ON A CONTRACT, NOT REJECTED. "
        "POST https://ai.api.nvidia.com/v1/structured-data/nvidia/kumo-"
        "relational/predictions returned HTTP 422 requiring {model, task, "
        "schema, context} — i.e. a declared relational schema + predictive "
        "query. It is the single best fit for repeat-purchase / size-return-"
        "risk prediction over the existing orders + wardrobe + catalogue "
        "tables, but wiring it means designing a real PQL task. Deferred "
        "pending approval; do not stub it."
    ),
    "google/gemma-4-31b-it": (
        "DEMOTED AFTER VERIFICATION. Output is correct, but latency across six "
        "measured runs was 10.3s / 40.6s / 72.4s / 98.0s / >120s / >180s — a "
        "worse-than-18x spread with two hard timeouts. It was briefly wired as "
        "the UTILITY_JSON failover and removed, because a failover candidate "
        "that hangs for 180s before yielding is worse than no candidate: it "
        "delays the honest degradation path instead of enabling it. It also "
        "fences JSON in ```json, which the client already de-fences. Re-route "
        "it only if NVIDIA stabilises its latency."
    ),
    "nvidia/nvclip": (
        "NOT ENTITLED. Listed in GET /v1/models but POST /v1/embeddings "
        "returns 404 'Function ...: Not found for account'. This is why "
        "image-vector search cannot be built on these credentials today."
    ),
}


# ─────────────────────────────────────────────────────────────────────────────
# Accessors
# ─────────────────────────────────────────────────────────────────────────────

def get_chain(role: ModelRole) -> List[ModelSpec]:
    """Ordered candidates for ``role``. Index 0 is the primary."""
    try:
        chain = ROLE_CHAINS[role]
    except KeyError:  # pragma: no cover - guarded by the Enum
        raise KeyError(f"No NVIDIA chain registered for role {role!r}") from None
    if not chain:
        raise KeyError(f"Role {role!r} is registered but has an empty chain")
    return list(chain)


def get_primary(role: ModelRole) -> ModelSpec:
    """The model a role uses when everything is healthy."""
    return get_chain(role)[0]


def find_spec(model_id: str) -> Optional[ModelSpec]:
    """Look a spec up by raw model id — used by the verifier and by /health."""
    for chain in ROLE_CHAINS.values():
        for spec in chain:
            if spec.model_id == model_id:
                return spec
    return None


def all_routed_model_ids() -> List[str]:
    """Every model id this registry can actually send traffic to (deduped)."""
    seen: List[str] = []
    for chain in ROLE_CHAINS.values():
        for spec in chain:
            if spec.model_id not in seen:
                seen.append(spec.model_id)
    return seen


def describe() -> Dict[str, Any]:
    """Serialisable snapshot for /health, docs and the verifier.

    Carries NO credentials — only env var NAMES.
    """
    return {
        "endpoint": "https://integrate.api.nvidia.com/v1",
        "verified_on": "2026-09-27",
        "roles": {
            role.value: [
                {
                    "model_id": s.model_id,
                    "position": "primary" if i == 0 else f"failover_{i}",
                    "supports_vision": s.supports_vision,
                    "measured_latency_s": list(s.measured_latency_s),
                    "slot_key_env": s.slot_key_env,
                    "evidence": s.evidence,
                    "notes": s.notes,
                }
                for i, s in enumerate(chain)
            ]
            for role, chain in ROLE_CHAINS.items()
        },
        "unrouted": dict(UNROUTED_MODELS),
    }
