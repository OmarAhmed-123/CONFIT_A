"""Turn an Arabic shopping request into the English the stylist can read.

WHY THIS EXISTS
---------------
Measured on production, 2026-09-29:

    "عايز حاجة تنفع لفرح مسائي مش رسمي أوي"  -> engine: none, 0 recommendations
    "formal wedding look, evening"           -> Groq,        2 recommendations

Same request, two languages, opposite outcomes. `StylingEngine
._OCCASION_KEYWORDS` is an English-only vocabulary, so an Arabic query
matched nothing, intent fell back to `style_source: "default"`, and the
stylist honestly asked the shopper to rephrase. CONFIT prices in EGP/AED/SAR
and ships a fully Arabic UI, so its primary market could never get a
recommendation.

TWO LAYERS, DELIBERATELY
------------------------
1. A LEXICON, applied first. Deterministic, no network, no hallucination.
   It covers the occasion and garment words that actually decide the search,
   including Egyptian and Gulf dialect that a generic translator mangles.
2. A MODEL, for the rest of the sentence. Only reached when the text is
   Arabic, and only to produce the free-text the lexicon cannot cover.

The lexicon is not a fallback for the model — it is the authority. A model
paraphrase that loses "wedding" silently changes which garments are
retrieved, so the terms that steer retrieval are pinned in code and the
model handles the prose around them.

WHY NOT riva-translate
----------------------
It is the purpose-built translator and it is wrong for this direction.
Measured live:

    'فستان سواريه أحمر'  -> "Red Swarovski Dress"    (brand invented)
    'بدلة شغل كلاسيك'    -> "Classic work trousers"  (suit became trousers)
    'فرح مسائي'          -> "evening party"          (wedding lost)

It also ignores the system turn, so a glossary cannot be given to it.
`ModelRole.TRANSLATION` therefore leads with nemotron-3-super, which obeys
the glossary and got all three right. riva stays in the chain for OUTBOUND
prose, where fluency is what matters.

FAILURE POLICY
--------------
Fails OPEN. If the model is unreachable the lexicon-substituted text is used
anyway: a partially translated query still retrieves something sensible,
whereas refusing would leave the Arabic shopper exactly where they were.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

logger = logging.getLogger("confit")

#: Arabic block. Presence of any of these means the text needs translating.
_ARABIC = re.compile(r"[\u0600-\u06FF\u0750-\u077F]")

#: Terms that STEER RETRIEVAL. Pinned in code because a paraphrase that drops
#: "wedding" changes which products are searched, and the shopper is then
#: answered about something they did not ask for.
#:
#: Keyed longest-first at match time so "فستان سواريه" beats "فستان".
_LEXICON: Dict[str, str] = {
    # occasions
    "فرح": "wedding", "افراح": "wedding", "أفراح": "wedding",
    "زفاف": "wedding", "خطوبة": "engagement party", "خطوبه": "engagement party",
    "سهرة": "evening", "سهره": "evening", "مسائي": "evening", "مسائية": "evening",
    "شغل": "work", "الشغل": "work", "مكتب": "office", "عمل": "work",
    "مقابلة": "interview", "انترفيو": "interview",
    "كاجوال": "casual", "كاچوال": "casual", "يومي": "casual",
    "حفلة": "party", "حفله": "party", "بارتي": "party",
    "عشاء": "dinner", "غدا": "lunch", "مناسبة": "occasion", "مناسبه": "occasion",
    "رسمي": "formal", "رسميه": "formal", "رسمية": "formal",
    "سفر": "travel", "اجازة": "vacation", "إجازة": "vacation",
    "عيد": "eid celebration", "تخرج": "graduation",
    # garments — the words riva got wrong
    "بدلة": "suit", "بدله": "suit", "طقم": "suit",
    "سواريه": "evening gown", "سوارية": "evening gown",
    "فستان": "dress", "فساتين": "dresses",
    "جاكيت": "jacket", "جاكت": "jacket", "بليزر": "blazer",
    "قميص": "shirt", "تيشيرت": "t-shirt", "تيشرت": "t-shirt",
    "بنطلون": "trousers", "بنطال": "trousers", "جينز": "jeans",
    "جيبة": "skirt", "جونلة": "skirt", "تنورة": "skirt",
    "حذاء": "shoes", "جزمة": "shoes", "شنطة": "bag", "شنطه": "bag",
    "كرافتة": "tie", "كرفتة": "tie", "معطف": "coat", "بالطو": "coat",
    "بلوزة": "blouse", "بلوزه": "blouse", "كارديجان": "cardigan",
    # modifiers that change formality
    "مش": "not", "أوي": "very", "اوي": "very", "جدا": "very", "جداً": "very",
    "تحت": "under", "اقل من": "under", "أقل من": "under",
    "رخيص": "affordable", "غالي": "premium", "بسيط": "simple",
    "انيق": "elegant", "أنيق": "elegant", "شيك": "chic",
    "كلاسيك": "classic", "مودرن": "modern", "عصري": "modern",
}

#: Built once: longest keys first so multi-word and compound terms win.
_LEXICON_ORDERED = sorted(_LEXICON.items(), key=lambda kv: -len(kv[0]))

_GLOSSARY_LINE = ", ".join(
    f"'{ar}'={en}"
    for ar, en in list(_LEXICON.items())[:28]
)

_SYSTEM_PROMPT = (
    "You translate Arabic fashion-shopping requests into English for a "
    "catalogue search engine.\n"
    "Rules:\n"
    "1. Output ONLY the English translation. No preamble, no quotes.\n"
    "2. Preserve the occasion, garment type, colour, formality and budget "
    "exactly. Never substitute a different garment.\n"
    "3. Never invent a brand name.\n"
    f"Egyptian/Gulf glossary: {_GLOSSARY_LINE}."
)


@dataclass(frozen=True)
class TranslationResult:
    """What the stylist should search with, and how it was produced."""

    text: str
    #: True when the input contained Arabic and was processed.
    translated: bool
    #: "lexicon" | "model" | "lexicon_only" (model unreachable) | "passthrough"
    source: str
    original: str
    latency_seconds: float = 0.0


def contains_arabic(text: Optional[str]) -> bool:
    return bool(text and _ARABIC.search(text))


def apply_lexicon(text: str) -> Tuple[str, int]:
    """Substitute retrieval-steering terms. Returns (text, substitutions)."""
    out = text
    hits = 0
    for arabic, english in _LEXICON_ORDERED:
        if arabic in out:
            out = out.replace(arabic, f" {english} ")
            hits += 1
    return re.sub(r"\s+", " ", out).strip(), hits


async def translate_query(text: str) -> TranslationResult:
    """Render an Arabic shopping request as English.

    English input is returned untouched — no network call, no latency, and
    nothing for a model to paraphrase.
    """
    original = text or ""
    if not contains_arabic(original):
        return TranslationResult(
            text=original, translated=False, source="passthrough", original=original
        )

    import time

    started = time.time()
    lexicon_text, hits = apply_lexicon(original)

    try:
        from backend.app.providers.nvidia.client import NvidiaClient
        from backend.app.providers.nvidia.registry import ModelRole

        client = NvidiaClient()
        rendered = await client.chat(
            ModelRole.TRANSLATION,
            user=original,
            system=_SYSTEM_PROMPT,
        )
        candidate = (rendered or "").strip().strip('"').strip()
        # A translator that returns Arabic has not translated. Rejecting it
        # here stops an untranslated string reaching the English-only
        # occasion matcher and silently scoring nothing.
        if candidate and not contains_arabic(candidate):
            logger.info(
                "query_translated",
                extra={"source": "model", "lexicon_hits": hits},
            )
            return TranslationResult(
                text=candidate,
                translated=True,
                source="model",
                original=original,
                latency_seconds=round(time.time() - started, 3),
            )
        logger.warning("query_translation_returned_arabic", extra={"hits": hits})
    except Exception as exc:
        # Fail OPEN: the lexicon substitution alone still retrieves something
        # sensible, and refusing would leave the shopper where they started.
        logger.warning(
            "query_translation_model_unavailable",
            extra={"detail": str(exc)[:200], "lexicon_hits": hits},
        )

    return TranslationResult(
        text=lexicon_text or original,
        translated=hits > 0,
        source="lexicon_only",
        original=original,
        latency_seconds=round(time.time() - started, 3),
    )
