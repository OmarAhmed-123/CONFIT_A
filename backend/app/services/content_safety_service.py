"""CONFIT content-safety guardrail — NVIDIA Nemotron-3 Content Safety.

Closes the gap `MODEL_REGISTRY.json` records as
``"image-moderation": "NOT REQUIRED (optional P2 safety, not in approved scope)"``
with the note that it *would* be a P2 add "only if product policy requires it".
Product policy does require it: CONFIT accepts photographs of users' bodies and
stores encrypted anthropometric measurements, and image validation today is
"PIL format/dimension only". Measured moderation cost is **0.33–0.50 s**, which
is cheap enough to run inline on every upload and every stylist turn.

The taxonomy is NOT the stock one. ``docs/safety/confit_safety_policy_v1.0.0.md``
is the canonical source of truth — a BYO policy generated with NVIDIA's
``nemotron-policy-generator`` skill, adding four categories the stock V2
taxonomy does not name (disordered-eating promotion, body shaming,
non-consensual imagery, minor body imagery). The prompt shape below follows the
skill's **Pattern E**, because the model was trained on that exact shape.

Fail behaviour is deliberately ASYMMETRIC, and that asymmetry is the whole
design:

* **Uploads fail CLOSED.** If the classifier cannot be reached, the image is
  not stored. A stored illegal image is unrecoverable; a failed upload is a
  retry.
* **Chat fails OPEN.** A stylist turn still gets answered by the deterministic
  ``StylingEngine``. Degrading text quality is visible and harmless.

Nothing here ever fabricates a verdict. When the classifier does not answer,
the result carries ``measured=False`` and the caller applies the fail policy —
consistent with this codebase's rule that an unmeasured state is reported
honestly rather than defaulted to "fine".
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Dict, List, Optional, Sequence

from backend.app.core.logging import logger
from backend.app.providers.nvidia import (
    ModelRole,
    NvidiaNotConfigured,
    NvidiaProviderError,
    nvidia_client,
)

#: Canonical policy document. Keep this pointer accurate — the policy is the
#: artifact a reviewer signs off, not this module.
POLICY_DOC = "docs/safety/confit_safety_policy_v1.0.0.md"
POLICY_VERSION = "1.0.0"


class Severity(IntEnum):
    """Runtime enforcement bands. NOT model output.

    Nemotron-3 emits only ``User Safety: safe/unsafe`` plus a category list;
    severity is what the runtime consults to pick an action.
    """

    SAFE = 0
    ANNOTATE = 1     # log only, user sees no change
    BLOCK_REPLY = 2  # block the AI response, let the user continue
    BLOCK_REDIRECT = 3  # block + supportive resources
    HARD_BLOCK = 4   # block, do not persist, audit


#: Category -> severity, transcribed from the policy's enforcement map.
#: Keys are lowercase; the model emits display names and casing varies.
CATEGORY_SEVERITY: Dict[str, Severity] = {
    # ── Custom CONFIT categories (S23+) ─────────────────────────────────────
    "disordered eating promotion": Severity.BLOCK_REDIRECT,
    "disordered_eating_promotion": Severity.BLOCK_REDIRECT,
    "body shaming": Severity.BLOCK_REPLY,
    "body_shaming": Severity.BLOCK_REPLY,
    "non-consensual or intimate imagery": Severity.HARD_BLOCK,
    "nonconsensual_imagery": Severity.HARD_BLOCK,
    "body imagery of minors": Severity.HARD_BLOCK,
    "minor_body_imagery": Severity.HARD_BLOCK,
    # ── V2 canonical ────────────────────────────────────────────────────────
    "sexual (minor)": Severity.HARD_BLOCK,
    "suicide and self harm": Severity.BLOCK_REDIRECT,
    "pii/privacy": Severity.BLOCK_REDIRECT,
    "violence": Severity.BLOCK_REPLY,
    "harassment": Severity.BLOCK_REPLY,
    "hate/identity hate": Severity.BLOCK_REPLY,
    "threat": Severity.BLOCK_REPLY,
    "sexual": Severity.BLOCK_REPLY,
    "criminal planning/confessions": Severity.BLOCK_REPLY,
    "guns and illegal weapons": Severity.BLOCK_REPLY,
    "controlled/regulated substances": Severity.BLOCK_REPLY,
    "malware": Severity.BLOCK_REPLY,
    "illegal activity": Severity.BLOCK_REPLY,
    "fraud/deception": Severity.BLOCK_REPLY,
    "manipulation": Severity.BLOCK_REPLY,
    "immoral/unethical": Severity.BLOCK_REPLY,
    "unauthorized advice": Severity.ANNOTATE,
    "political/misinformation/conspiracy": Severity.ANNOTATE,
    "copyright/trademark/plagiarism": Severity.ANNOTATE,
    "profanity": Severity.ANNOTATE,
    "needs caution": Severity.ANNOTATE,
}

#: Unknown category emitted by the model. Never silently treated as safe — an
#: unrecognised label still means the classifier flagged something.
DEFAULT_UNSAFE_SEVERITY = Severity.BLOCK_REPLY

# ── The BYO taxonomy injected at inference (skill Pattern E) ─────────────────
# Category NAMES, not Sn labels: Nemotron-3 emits names. Kept terse on purpose —
# the full definitions live in the policy doc; the model needs the discriminating
# line, and an over-long block measurably dilutes attention.
_CUSTOM_TAXONOMY = """\
Custom safety taxonomy (in addition to the standard categories):
- Disordered eating promotion: requests for or encouragement of starvation, \
purging, extreme caloric restriction, or "thinspiration". NOT ordinary size, \
fit, or measurement questions, and NOT garment descriptions like "slimming".
- Body shaming: demeaning or humiliating language about body shape, size, \
weight, or features. NOT neutral fit guidance such as "high-rise trousers \
lengthen the leg line".
- Non-consensual or intimate imagery: nude or intimate photos, or a photo of \
another identifiable person supplied as a try-on base. NOT professional \
product photography, including swimwear shown as a product.
- Body imagery of minors: any body photo or body measurements that appear to \
belong to a minor, sexualized or not. NOT photographs of children's garments \
on their own."""

_ALLOW_LIST = """\
Allow-list (explicitly permitted even though they sound adjacent to a category):
- Body measurements as numbers (chest, waist, hip, inseam, height, weight).
- Fit and silhouette vocabulary: slimming, flattering, elongates, runs small.
- The user's own clothed photo, including swimwear, for virtual try-on.
- Swimwear and lingerie presented as product photography.
- Neutral size-inclusivity language: plus size, petite, tall.
- A user mentioning a personal weight or fitness goal in passing while asking a \
clothing question, for example "I want to lose 10 kg before my wedding, what \
should I wear now?". Stating a goal is safe; only asking for dangerous METHODS \
(starving, purging, extreme restriction) is unsafe.
- Arabic-language equivalents of all of the above."""

_USER_SAFETY = re.compile(r"User Safety:\s*(safe|unsafe)", re.IGNORECASE)
_RESPONSE_SAFETY = re.compile(r"Response Safety:\s*(safe|unsafe)", re.IGNORECASE)
_CATEGORIES = re.compile(r"Safety Categories:\s*(.+)", re.IGNORECASE)


@dataclass(frozen=True)
class SafetyVerdict:
    """The outcome of one moderation call.

    ``measured`` is the honesty flag. False means the classifier did not give a
    verdict, so ``safe`` carries no evidence and the caller must apply its fail
    policy rather than trusting the value.
    """

    safe: bool
    measured: bool
    severity: Severity = Severity.SAFE
    categories: List[str] = field(default_factory=list)
    latency_s: float = 0.0
    model_id: Optional[str] = None
    error: Optional[str] = None
    raw: Optional[str] = None

    @property
    def should_block(self) -> bool:
        return self.measured and not self.safe and self.severity >= Severity.BLOCK_REPLY

    @property
    def must_not_persist(self) -> bool:
        """S4 — the artefact may not be written to storage at all."""
        return self.measured and self.severity >= Severity.HARD_BLOCK

    def to_audit(self) -> Dict[str, Any]:
        """Credential-free, PII-free record for the audit chain.

        Deliberately excludes the moderated text/image: writing the offending
        content into an append-only audit log would persist exactly what the
        S4 rule says must never be stored.
        """
        return {
            "policy_version": POLICY_VERSION,
            "safe": self.safe,
            "measured": self.measured,
            "severity": int(self.severity),
            "categories": list(self.categories),
            "model_id": self.model_id,
            "latency_s": self.latency_s,
            "error": self.error,
        }


class ContentSafetyService:
    """Moderation gate for user text and user images."""

    def __init__(self, client=nvidia_client) -> None:
        self._client = client

    @property
    def configured(self) -> bool:
        return bool(getattr(self._client, "configured", False))

    async def check_text(self, text: str, *, context: str = "chat") -> SafetyVerdict:
        """Moderate a user-authored string (stylist prompt, review, note)."""
        if not (text or "").strip():
            return SafetyVerdict(safe=True, measured=True)
        return await self._classify(user_text=text, images=None, context=context)

    async def check_image(
        self, image_url: str, *, caption: str = "", context: str = "upload"
    ) -> SafetyVerdict:
        """Moderate an image before it is stored or sent to try-on.

        ``image_url`` may be an https URL or a ``data:image/...;base64,`` URI;
        both are accepted by the endpoint.
        """
        prompt = caption.strip() or "User submitted this image to a virtual try-on and wardrobe app."
        return await self._classify(user_text=prompt, images=[image_url], context=context)

    async def _classify(
        self, *, user_text: str, images: Optional[Sequence[str]], context: str
    ) -> SafetyVerdict:
        payload = (
            f"{_CUSTOM_TAXONOMY}\n\n{_ALLOW_LIST}\n\n"
            f"Human user:\n{user_text}\n\nAI assistant:\n"
        )
        try:
            result = await self._client.chat(
                ModelRole.CONTENT_SAFETY,
                user=payload,
                images=list(images) if images else None,
                timeout_s=10.0,
            )
        except NvidiaNotConfigured as exc:
            # Not an incident: an unconfigured deployment is a valid state.
            return SafetyVerdict(safe=True, measured=False, error=str(exc))
        except (NvidiaProviderError, Exception) as exc:  # noqa: BLE001
            logger.error(
                "content_safety_unavailable",
                context=context, error=str(exc),
                action_required=(
                    "uploads must fail closed; chat may proceed on the "
                    "deterministic engine"
                ),
            )
            return SafetyVerdict(safe=True, measured=False, error=str(exc))

        verdict = self._parse(result.text, result.model_id, result.latency_s)
        if not verdict.safe:
            logger.warn(
                "content_safety_block",
                context=context,
                severity=int(verdict.severity),
                categories=verdict.categories,
                model=verdict.model_id,
                policy_version=POLICY_VERSION,
            )
        return verdict

    @staticmethod
    def _parse(text: str, model_id: str, latency_s: float) -> SafetyVerdict:
        """Parse the documented emit shape.

        Verified live 2026-09-27 — the model answers exactly:
            User Safety: unsafe
            Safety Categories: Suicide and Self Harm
        """
        user_match = _USER_SAFETY.search(text or "")
        response_match = _RESPONSE_SAFETY.search(text or "")

        if not user_match and not response_match:
            # A 200 we cannot interpret is NOT a pass. Report it unmeasured so
            # upload paths still fail closed.
            logger.error(
                "content_safety_unparseable",
                model=model_id, raw=(text or "")[:200],
                action_required="verify the model's emit format has not changed",
            )
            return SafetyVerdict(safe=True, measured=False, model_id=model_id,
                                 latency_s=latency_s, error="unparseable verdict",
                                 raw=(text or "")[:200])

        unsafe = any(
            m and m.group(1).lower() == "unsafe" for m in (user_match, response_match)
        )
        categories: List[str] = []
        cat_match = _CATEGORIES.search(text or "")
        if cat_match:
            categories = [
                c.strip() for c in cat_match.group(1).split(",") if c.strip()
            ]

        if not unsafe:
            return SafetyVerdict(safe=True, measured=True, severity=Severity.SAFE,
                                 model_id=model_id, latency_s=latency_s)

        severity = Severity.SAFE
        for name in categories:
            severity = max(
                severity,
                CATEGORY_SEVERITY.get(name.strip().lower(), DEFAULT_UNSAFE_SEVERITY),
            )
        if not categories:
            # Flagged unsafe with no category (/no_categories, or the list was
            # dropped). Still unsafe — never downgrade to safe.
            severity = DEFAULT_UNSAFE_SEVERITY

        return SafetyVerdict(
            safe=False, measured=True, severity=severity, categories=categories,
            model_id=model_id, latency_s=latency_s, raw=(text or "")[:200],
        )


#: Shared instance.
content_safety_service = ContentSafetyService()


# ── Caller-facing refusal copy ───────────────────────────────────────────────
# Kept here so refusals are consistent and reviewable in one place. Per the
# policy: never echo the detected category back to the user — that accuses them
# and leaks classifier behaviour.

REFUSAL_IMAGE = (
    "We can't process this image. Please upload a clear photo of yourself "
    "wearing fitted clothing, or a product photo of the garment on its own."
)

REFUSAL_SELF_HARM = (
    "I want to help you find clothes you feel good in, and I'm not able to help "
    "with that particular request. If you're struggling with how you're eating "
    "or feeling about your body, talking to someone helps — in Egypt you can "
    "reach the Ministry of Health line on 105, and befrienders.org lists free, "
    "confidential support worldwide. I'm still here for styling whenever you want."
)

REFUSAL_GENERIC = (
    "I can't help with that one, but I'm happy to keep going on styling, fit, "
    "or sizing."
)


def refusal_for(verdict: SafetyVerdict, *, is_image: bool = False) -> str:
    """The user-facing message for a blocked verdict."""
    if is_image:
        return REFUSAL_IMAGE
    if verdict.severity >= Severity.BLOCK_REDIRECT:
        lowered = {c.lower() for c in verdict.categories}
        if lowered & {"suicide and self harm", "disordered eating promotion",
                      "disordered_eating_promotion"}:
            return REFUSAL_SELF_HARM
    return REFUSAL_GENERIC
