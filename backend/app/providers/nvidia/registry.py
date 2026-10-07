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
        # PRIMARY SWAP 2026-10-07, measured on the PRODUCTION-SHAPED payload.
        #
        # Why it was needed. Production was serving every stylist turn with
        # "Groq openai/gpt-oss-120b" (14.5s / 3.8s / 7.9s probe, engine label
        # read off the live response) even though NVIDIA_API_KEY and all 19 slot
        # keys are set on the platform and AI_PROVIDERS lists the nvidia legs
        # first. The leg was not missing — it was unreachable: with the
        # orchestrator's real payload (max_tokens=900 plus the live stylist
        # system prompt) ultra-550b answered in **21.89s** and 503'd on the
        # first attempt, while AI_PROVIDER_TIMEOUT_SECONDS is 4.0s. Every call
        # therefore timed out and fell through to Groq. A configured provider
        # that cannot answer inside its budget is indistinguishable from an
        # absent one, and nothing in /api/v1/health showed it.
        #
        # The order below is set by that measurement, not by model size:
        #  * super-120b answers the SAME production-shaped payload in 2.71s and
        #    3.58s, grounded in the supplied catalogue, EGP prices preserved.
        #  * ultra-550b keeps the failover slot: its grounding is still the best
        #    measured (see its evidence), and as a failover it is allowed to
        #    miss a 6s budget without costing the shopper the first answer.
        ModelSpec(
            model_id="nvidia/nemotron-3-super-120b-a12b",
            endpoint=CHAT_COMPLETIONS_URL,
            params={
                "temperature": 0.6,
                "top_p": 0.95,
                "chat_template_kwargs": {"enable_thinking": False},
            },
            measured_latency_s=(0.72, 3.58),
            slot_key_env="NVIDIA_KEY_NEMOTRON_3_SUPER_120B_A12B",
            evidence=(
                "2026-10-07, production-shaped payload through the orchestrator's "
                "own leg (_call_nvidia_at): 2.71s and 3.58s, both grounded in the "
                "supplied items ('pair the Pleated Tapered Virgin Wool Trousers "
                "(165 EGP) with ...'), budget respected. Shorter stylist probes "
                "the same day: 0.90 / 0.91 / 1.28s (default thinking) and 0.88 / "
                "0.72s with enable_thinking=False. REVIVED today: it answered 410 "
                "Gone on 2026-10-03 and was absent from GET /v1/models, which is "
                "why it had been benched."
            ),
            notes=(
                "PRIMARY. enable_thinking=False is REQUIRED: with thinking on the "
                "reply carries a reasoning prefix and arrives a sentence late. "
                "~4x faster than ultra on identical payloads, which is what makes "
                "the NVIDIA leg actually serve instead of timing out. ultra-550b "
                "is the next candidate if this one 503s."
            ),
        ),
        ModelSpec(
            model_id="nvidia/nemotron-3-ultra-550b-a55b",
            endpoint=CHAT_COMPLETIONS_URL,
            params={"temperature": 0.6, "top_p": 0.95},
            measured_latency_s=(0.8, 21.89),
            slot_key_env="NVIDIA_KEY_NEMOTRON_3_ULTRA_550B_A55B",
            evidence=(
                "Best grounding measured in the pool: 2026-09-27, real CONFIT "
                "stylist prompt (3 grounded catalogue items, $385 total): 200 in "
                "4.1s / 126 completion tokens; named every item, honoured the "
                "2-3 sentence cap, stated the budget correctly, invented nothing. "
                "2026-10-01: 2.3 / 4.8 / 5.9s plus one 12s hard timeout. "
                "2026-10-07 (production-shaped payload): one 503 "
                "'ResourceExhausted: Worker local total request limit reached' at "
                "0.34s, then 200 in 21.89s — the measurement that explains why the "
                "NVIDIA leg was invisible in production, and why this slot is no "
                "longer the primary. Needs AI_PROVIDER_TIMEOUT_SECONDS >= 25 to "
                "serve reliably, which no shopper-facing turn should wait for."
            ),
            notes=(
                "FAILOVER_1. Still the best-grounded model in the pool, but its "
                "tail latency on the production payload (21.89s measured) exceeds "
                "any sane per-provider budget, so it is reached only when the "
                "primary fails fast. It REMAINS the translation primary, where the "
                "nvidia_client deadline is much wider and the 2026-10-03 battery "
                "showed it preserves 'فرح' and true colours. Groq is the "
                "orchestrator's next leg if this chain exhausts — honest "
                "degradation, never a synthesised answer."
            ),
        ),
        # moonshotai/kimi-k3 was the third entry here until 2026-10-01, when a
        # live re-verification measured it at 85.2s / 103.5s-with-empty-content
        # / 120s-hard-timeout across three probes (it was 8.6-14.9s on
        # 2026-09-27). With a 60s stylist deadline it can never complete, so
        # keeping it here only delayed honest degradation. See UNROUTED_MODELS.
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
                "See the enable_thinking comment above — it is load-bearing. "
                "Re-verified live 2026-10-01: 200 in 0.9s."
            ),
        ),
        # moonshotai/kimi-k3 sat here (failover_1) until 2026-10-01, when a
        # live re-verification timed it out at 90s and caught a phantom-empty
        # 200 (finish_reason=stop, content="") on a separate probe. Demoted
        # to UNROUTED_MODELS; nano-omni takes the failover slot.
        ModelSpec(
            model_id="nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
            endpoint=CHAT_COMPLETIONS_URL,
            params={"temperature": 0.2, "top_p": 0.95, "max_tokens": 2048,
                    "reasoning_budget": 1024},
            supports_vision=True,
            measured_latency_s=(0.8, 24.6),
            slot_key_env="NVIDIA_KEY_NEMOTRON_3_NANO_OMNI_30B_A3B_REASONING",
            evidence=(
                "2026-09-27: correct single-word vision answer in 6.8s, BUT "
                "returned HTTP 503 'ResourceExhausted: Worker local total "
                "request limit reached (16/16)' on two separate concurrent "
                "runs. Re-verified live 2026-10-01: correct vision answer in "
                "24.6s — it works, but it is slow."
            ),
            notes=(
                "FAILOVER ONLY. The 16-request worker ceiling makes it unsafe "
                "as a primary under real traffic; the client's 503 handling "
                "rotates off it automatically. Promoted to failover_1 on "
                "2026-10-01 after kimi-k3 was demoted."
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
        # PRIMARY SWAP 2026-10-03, forced by the endpoint: nemotron-3-super-
        # 120b-a12b answered 410 Gone (end-of-life) and left GET /v1/models,
        # which silently demoted BOTH translation directions onto
        # riva-translate — measured that day on production: Arabic prompts got
        # English replies (reply_language="en", 0 Arabic characters) because
        # riva, which ignores the system turn, answered the outbound EN->AR
        # call in NORWEGIAN ("Den marineblå blazeren...") and the
        # contains_arabic guard correctly refused to ship it. Inbound decayed
        # the same way ('فرح مسائي' -> "Evening party", wedding lost).
        #
        # Replacement candidate battery, measured live 2026-10-03 (same three
        # inbound queries + two outbound sentences, enable_thinking=False):
        #   - nemotron-3-ultra-550b-a55b: 'فرح مسائي فستان سواريه أحمر' ->
        #     "Evening wedding red evening gown"; 'بدلة شغل كلاسيك رجالي
        #     شتوي' -> "Men's classic winter work suit"; 'جاكيت كاجوال
        #     للخروج' -> "Casual jacket for going out". Outbound: 104-114
        #     Arabic chars, ZERO leaked Latin words (brands/prices preserved),
        #     'sage-green' kept its colour (riva had turned it into 'الأبيض').
        #     0.3-3.3s per call. SELECTED.
        #   - nemotron-3-nano-omni-30b-a3b-reasoning: fluent Arabic but leaks
        #     parenthetical English ("(virgin wool)") and lost 'فرح' ->
        #     "red evening dress". REJECTED.
        #   - nemotron-3.5-lightning-30b-a3b: 'فرح' -> "Evening party" +
        #     invented "swimsuit". REJECTED (riva-class failure).
        #   - z-ai/glm-5.3 / glm-5.3-flash: leak "The user wants me to
        #     translate..." preamble into content. REJECTED.
        #   - moonshotai/kimi-k3: correct when it answers but degenerated to
        #     "Men's!!!!!!!!" on one probe, 53s for three calls. REJECTED
        #     (matches its 2026-10-1 stylist degradation).
        #   - llama-3.1-nemotron-70b/51b-instruct, nemotron-nano-3-30b-a3b:
        #     404 function-not-found. DEAD.
        ModelSpec(
            model_id="nvidia/nemotron-3-ultra-550b-a55b",
            endpoint=CHAT_COMPLETIONS_URL,
            # enable_thinking is REQUIRED for this model in the translation
            # role. Measured 2026-10-03: WITHOUT the flag, terse instruction
            # prompts return the chain-of-thought ("The user wants me to
            # translate an Egyptian Arabic shopping query into...") as
            # content; WITH it, clean translations only. Stylist-prose prompts
            # do not need the guard, which is why STYLIST_CHAT omits it.
            params={
                "temperature": 0.0,
                "max_tokens": 160,
                "chat_template_kwargs": {"enable_thinking": False},
            },
            measured_latency_s=(0.3, 3.3),
            slot_key_env="NVIDIA_KEY_NEMOTRON_3_ULTRA_550B_A55B",
            evidence=(
                "2026-10-03 full candidate battery above: both directions "
                "correct on every probe (wedding/suit/jacket preserved "
                "inbound; zero Latin leakage, true colours, brands and prices "
                "preserved outbound), 0.3-3.3s per call on the NIM free tier. "
                "The slot is simultaneously STYLIST_CHAT primary, so it is "
                "already warm in production."
            ),
            notes=(
                "PRIMARY for BOTH directions. Follows the system turn, which "
                "is what makes dialect terms ('فرح', 'سواريه') survive "
                "inbound and colours stay true outbound — the exact property "
                "super had and riva lacks."
            ),
        ),
        # REVIVED 2026-10-07 as the translation failover (see the STYLIST_CHAT
        # entry above for the revival evidence). It is deliberately NOT the
        # primary for this role even though it is 10x faster than ultra: the
        # 2026-10-07 battery reproduced the exact defect that had it benched.
        ModelSpec(
            model_id="nvidia/nemotron-3-super-120b-a12b",
            endpoint=CHAT_COMPLETIONS_URL,
            params={
                "temperature": 0.0,
                "max_tokens": 256,
                "chat_template_kwargs": {"enable_thinking": False},
            },
            measured_latency_s=(0.24, 5.14),
            slot_key_env="NVIDIA_KEY_NEMOTRON_3_SUPER_120B_A12B",
            evidence=(
                "2026-10-07, same inbound/outbound battery the 2026-10-03 "
                "candidate sweep used. OUTBOUND EN->AR: correct Egyptian "
                "Arabic both probes (51 and 54 Arabic characters), brand "
                "'Massimo Dutti' dropped as expected but every price and the "
                "sage-green colour preserved — 5.14s and 1.89s. INBOUND "
                "AR->EN: 0.24-0.38s, but two of three probes prefixed the "
                "answer with the literal token 'Message:' and one rendered "
                "'فرح مسائي' (evening wedding) as 'Evening joy' — the same "
                "false friend that got riva benched. Correct on the other "
                "two queries ('بدلة شغل كلاسيك رجالي شتوي' -> \"Men's classic "
                "winter work suit\")."
            ),
            notes=(
                "FAILOVER_1 for translation, ahead of riva: it follows the "
                "system turn (riva ignores it), and its outbound Arabic is "
                "clean where riva's was Norwegian. NOT primary because of the "
                "'Message:' prefix leak and the 'فرح' false friend inbound — "
                "both are quality defects ultra does not have. Promote it "
                "only after a bigger inbound battery clears, or with a "
                "strip_prefix guard in the caller."
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
                "FAILOVER_2 for outbound EN->AR prose only (ultra-550b leads "
                "both directions since 2026-10-03; super-120b took failover_1 "
                "on 2026-10-07 when it came back). Fluent "
                "but instruction-blind: "
                "it ignores the system turn, so no glossary can be supplied, "
                "it renamed a garment and invented a brand on live inbound "
                "tests, and it mistranslated a colour on live outbound tests. "
                "Better than no translation when super is down — never the "
                "first choice."
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
            evidence="2026-09-27: 200 in 0.2s, 2048-dimension float vector returned. Re-verified live 2026-10-01: 200 in 0.3s, 2048 dimensions.",
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
    # nvidia/nemotron-3-super-120b-a12b was listed here as END-OF-LIFE from
    # 2026-10-03 (410 Gone on every call, absent from GET /v1/models). It was
    # REVIVED on 2026-10-07 — five consecutive 200s at 0.72-1.28s on the real
    # stylist prompt, and back in the catalogue — so it is routed again as
    # stylist_chat failover_1 and translation failover_1. Both chain entries
    # carry the new measurements; this note stays so the next reader can see
    # the full history instead of assuming the entry was never considered.
    # Its original promotion conditions (bigger inbound translation battery,
    # or a prefix-stripping guard) are recorded in the TRANSLATION specs.
    "moonshotai/kimi-k3": (
        "DEMOTED AFTER DEGRADATION (2026-10-01). Re-measured live with three "
        "probes: 120s hard read-timeout, then HTTP 200 in 103.5s with "
        "finish_reason=stop and EMPTY content (the phantom-empty failure "
        "mode), then a genuine 200 in 85.2s. On 2026-09-27 the same probes "
        "took 8.6-14.9s. Its latency now exceeds every role deadline (60s "
        "stylist / 90s vision), so a chain containing it can never reach it "
        "in time — keeping it wired only delayed the honest-degradation path. "
        "Key retained in the pool. Re-evaluate only if NVIDIA stabilises it."
    ),
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
        "verified_on": "2026-10-01",
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
