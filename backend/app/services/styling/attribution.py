"""Where a style claim comes from — and what we are therefore allowed to say.

THE DEFECT THIS CLOSES (measured 2026-09-24)
An anonymous caller with no profile asked for *"a smart casual outfit for an art
gallery opening under $300"* and was answered:

    "Here is your grounded Evening & Party ensemble tailored to your Smart Casual
     profile."

There is no profile. ``"Smart Casual"`` is a **system default** that
``stylist_service`` used as a *matching input*; the prose then promoted it to a
fact about the shopper. It is the same honesty class as the fabricated body
measurements ("178 cm · 72 kg, Athletic") closed in the same cycle: the product
stated something it did not know.

THE RULE
    A system default is never presented as a user fact.

Four sources are distinguished, and exactly ONE of them licenses the phrase
"your … profile":

    profile       a persisted style profile (authenticated shopper with archetypes)
    conversation  the shopper said it in THIS request ("make it minimalist")
    default       nothing was provided, so CONFIT chose a starting point
    unknown       nothing to attribute (no signal at all)

The phrase builder is the single place the sentence lives, so the three prose
sites (orchestrator deterministic fallback, grounding generator, stylist
provider) cannot drift apart again. This module is deliberately pure: no I/O, no
settings, no database — it is the kind of rule that should be impossible to
misread while editing a longer function.
"""
from __future__ import annotations

STYLE_SOURCE_PROFILE = "profile"
STYLE_SOURCE_CONVERSATION = "conversation"
STYLE_SOURCE_DEFAULT = "default"
STYLE_SOURCE_UNKNOWN = "unknown"

KNOWN_SOURCES = (
    STYLE_SOURCE_PROFILE,
    STYLE_SOURCE_CONVERSATION,
    STYLE_SOURCE_DEFAULT,
    STYLE_SOURCE_UNKNOWN,
)


def resolve_style_source(
    *,
    profile_styles_present: bool,
    prompt_drove_aesthetic: bool,
) -> str:
    """Decide which source the aesthetic actually came from.

    Order matters and is the whole point: a direction the shopper typed in this
    request is attributed to the conversation even when a stored profile exists
    (the stored profile is not what produced this answer), and a default is never
    upgraded to "profile" merely because it was used for matching.
    """
    if prompt_drove_aesthetic:
        return STYLE_SOURCE_CONVERSATION
    if profile_styles_present:
        return STYLE_SOURCE_PROFILE
    return STYLE_SOURCE_DEFAULT


def style_attribution_phrase(aesthetic: str, source: str) -> str:
    """The clause that follows "Here is your … ensemble" / "look".

    Only ``profile`` may claim ownership. ``default`` says out loud that CONFIT
    chose the direction and no profile is on file, which is the truthful version
    of what used to be a fabricated personal fact.
    """
    if source == STYLE_SOURCE_PROFILE:
        return f"tailored to your {aesthetic} profile"
    if source == STYLE_SOURCE_CONVERSATION:
        return f"following the {aesthetic} direction you gave in this request"
    if source == STYLE_SOURCE_DEFAULT:
        return (
            f"built on a {aesthetic} starting point — no style profile is on file "
            f"for this session"
        )
    return "built on the items below"


def profile_claim_allowed(source: str) -> bool:
    """Whether any surface may describe this answer as profile-personalised."""
    return source == STYLE_SOURCE_PROFILE
