"""Granite builds the styling list itself (the IBM "AI stylist" step).

WHAT THIS ADDS THAT THE PROSE LEG DID NOT
  Until now Granite only *described* a list that the deterministic engine had
  already chosen. In IBM's tutorial
  (ibm.com/think/tutorials/build-ai-stylist-with-granite-python-watsonx-ai,
  Step 8) the reasoning model performs the SELECTION: it receives the closet and
  the shopper's criteria and returns one shirt, one bottom and one pair of
  shoes. This module does that job, with two deliberate departures.

DEPARTURE 1 - the model names product IDs, not filenames.
  The tutorial reads the answer back by substring-matching image filenames:
      if item['filename'].lower() in outfit.lower()
  That is fragile (a filename that is a prefix of another, a model that
  paraphrases, an answer that mentions a file it did not choose) and it cannot
  express "this product is not in the catalogue". Here the model must return a
  JSON `product_id` from a closed list, and every ID is checked against the
  exact candidates it was shown. An invented product is rejected, not rendered.

DEPARTURE 2 - the budget is not the model's job.
  Live measurement (2026-10-24): asked to respect "under 7000 EGP", Granite
  returned 11,000 EGP worth of items 3 times out of 3, then got it right on a
  later identical call. Its arithmetic is not reliable, so it is not trusted:
  the composer's existing Decimal-exact `_enforce_budget` still runs on whatever
  this module returns, and a look that cannot be brought inside the budget is
  suppressed exactly as before.

FAILURE POLICY
  Every rejection returns ``None`` and logs a reason. The caller then keeps the
  deterministic selection it already built. A slow, malformed or unavailable
  model can therefore never degrade the shopper's experience below the shipped
  behaviour; it can only change WHICH of the eligible products are picked.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.providers.watsonx import WatsonxAuthError, WatsonxClient

#: Hard caps so a request can never turn into a wall of tokens. The candidate
#: list is the shopper-visible shortlist, not the whole catalogue.
MAX_CANDIDATES = 36
MAX_ITEMS = 5
MIN_ITEMS = 2
MAX_REASON_CHARS = 120

#: `_detected_slot` values that belong to each coarse canvas position. Mirrors
#: the composer's _candidate_pool so the model and the server agree on what a
#: "top" is.
_POSITION_OF_SLOT = {
    "dress": "dress", "jumpsuit": "dress",
    "formal_outer": "outerwear", "semi_formal_outer": "outerwear", "casual_outer": "outerwear",
    "formal_shirt": "top", "casual_shirt": "top", "knit_layer": "top", "t_shirt": "top",
    "formal_bottom": "bottom", "semi_formal_bottom": "bottom", "casual_bottom": "bottom",
    "formal_shoes": "footwear", "semi_formal_shoes": "footwear",
    "casual_shoes": "footwear", "boots": "footwear",
    "tie": "accessory", "pocket_square": "accessory", "belt": "accessory",
    "bag": "accessory", "watch": "accessory",
}

SYSTEM_PROMPT = (
    "You are CONFIT's personal stylist. You choose outfits from a fixed list of "
    "products a shop has in stock. You never invent products, brands or prices. "
    "You reply with JSON only, no prose and no markdown."
)


def _slot_name(product: Any) -> str:
    slot = getattr(product, "_detected_slot", None)
    name = getattr(slot, "value", None) or str(slot)
    return name.lower()


def position_for(product: Any) -> Optional[str]:
    """Coarse canvas position for a product, from its classified slot."""
    return _POSITION_OF_SLOT.get(_slot_name(product))


def _candidate_rows(products: Sequence[Any]) -> List[Dict[str, Any]]:
    """The shortlist shown to the model. Only real catalogue facts."""
    rows: List[Dict[str, Any]] = []
    for p in products:
        try:
            brand = p.brand.brand_name if getattr(p, "brand", None) else "CONFIT Partner"
        except Exception:  # noqa: BLE001 - a lazy relation may not be loaded
            brand = "CONFIT Partner"
        rows.append({
            "product_id": p.id,
            "title": getattr(p, "title", "") or "",
            "brand": brand,
            "position": position_for(p),
            "price": float(getattr(p, "base_price", 0) or 0),
            "currency": getattr(p, "currency", None),
            "colour": getattr(p, "color_family", None),
            "material": getattr(p, "material", None),
        })
    return rows


def _build_prompt(rows: List[Dict[str, Any]], intent: Dict[str, Any]) -> str:
    occasion = intent.get("occasion") or "Smart Casual"
    aesthetic = intent.get("aesthetic") or "Quiet Luxury"
    budget = intent.get("detected_budget")
    budget_line = (
        f"The total for the whole outfit must not exceed {budget} {rows[0].get('currency') or ''}".strip()
        if budget else "There is no fixed budget."
    )
    return (
        f"Put together ONE outfit for: {occasion}. Style direction: {aesthetic}. "
        f"{budget_line}\n\n"
        "Rules:\n"
        f"- Choose between {MIN_ITEMS} and {MAX_ITEMS} products, each exactly once.\n"
        "- Use ONLY product_id values from the list. Never invent an id.\n"
        "- Build a wearable outfit: usually a dress, OR a top with a bottom, plus footwear.\n"
        "- Add an outerwear or accessory only when it improves the look.\n"
        "- Prefer colours and materials that work together, and stay inside the budget.\n\n"
        "Reply with exactly this JSON shape and nothing else:\n"
        '{"items": [{"product_id": <int>, "reason": "<max 12 words>"}], '
        '"title": "<max 8 words>"}\n\n'
        "Products:\n"
        + json.dumps(rows, ensure_ascii=False)
    )


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    """Pull the first JSON object out of a model answer.

    Granite is told to answer with JSON only, but a stray ```json fence or a
    leading sentence is a real possibility, so both are tolerated. Anything that
    still does not parse is a rejection, never a guess.
    """
    if not text:
        return None
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        parsed = json.loads(cleaned)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        parsed = json.loads(cleaned[start:end + 1])
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


class ValidationError(ValueError):
    """The model's selection is not usable as a shopping recommendation."""


def validate_selection(
    payload: Dict[str, Any], offered: Dict[int, Any]
) -> List[Tuple[Any, str]]:
    """Check a model selection against the products it was actually shown.

    Returns ``[(product, reason), ...]`` in the model's order, or raises
    ValidationError explaining the first reason it cannot be shown to a shopper.
    """
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        raise ValidationError("no items in payload")

    if len(items) > MAX_ITEMS:
        raise ValidationError(f"more than {MAX_ITEMS} items requested ({len(items)})")
    if len(items) < MIN_ITEMS:
        raise ValidationError(f"only {len(items)} item(s); an outfit needs at least {MIN_ITEMS}")

    chosen: List[Tuple[Any, str]] = []
    seen: set = set()
    for entry in items:
        if not isinstance(entry, dict):
            raise ValidationError("item is not an object")
        raw_id = entry.get("product_id")
        try:
            product_id = int(raw_id)
        except (TypeError, ValueError):
            raise ValidationError(f"product_id {raw_id!r} is not an integer") from None

        product = offered.get(product_id)
        if product is None:
            # The failure this whole module exists to prevent: a product the
            # shopper was never offered. Rejected, never rendered.
            raise ValidationError(f"product_id {product_id} was not offered")
        if product_id in seen:
            raise ValidationError(f"product_id {product_id} chosen twice")
        if position_for(product) is None:
            raise ValidationError(f"product_id {product_id} has no wearable position")

        seen.add(product_id)
        reason = str(entry.get("reason") or "").strip()[:MAX_REASON_CHARS]
        chosen.append((product, reason))

    return chosen


def _coverage_ok(chosen: List[Tuple[Any, str]]) -> bool:
    """A shopper can wear this: a dress, or a top+bottom; footwear anywhere.

    OBSERVED 2026-10-24 against live Granite: with a generous budget the model
    returned a DRESS plus TROUSERS. Both ids were legal and the ids were real,
    so id-validation alone let it through - but nobody wears a slip dress over
    trousers as one outfit. A dress and a bottom are mutually exclusive here,
    which is the same branch the deterministic composer takes (`is_dress_intent`
    picks one path, never both). Layers over a dress (outerwear, footwear,
    accessory) stay allowed.
    """
    positions = {position_for(p) for p, _ in chosen}
    has_dress = "dress" in positions
    has_bottom = "bottom" in positions
    if has_dress and has_bottom:
        return False
    has_separates = "top" in positions and has_bottom
    return bool(has_dress or has_separates)


class WatsonxListBuilder:
    """Asks Granite to choose the outfit, then proves the choice is legal."""

    def __init__(self, client: Optional[WatsonxClient] = None) -> None:
        self._client = client or WatsonxClient()

    @staticmethod
    def is_enabled() -> bool:
        """Kill switch, so the leg can be turned off without a deploy."""
        if not getattr(settings, "WATSONX_LIST_BUILDING", True):
            return False
        # The shared client owns the IAM token cache; instantiating a throwaway
        # one here would report "configured" correctly but is needless churn.
        from backend.app.providers.watsonx import watsonx_client

        return watsonx_client.is_configured()

    async def build(
        self, products: Sequence[Any], intent: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Return a validated selection, or None to keep the deterministic one.

        Never raises for a model-side problem: a styling request must not fail
        because a third-party model answered badly.
        """
        if not products or not self._client.is_configured():
            return None

        # Deduplicate and cap. Cheapest-first is deliberate: when the shortlist
        # has to be trimmed, the trim must not push the model out of budget.
        unique: List[Any] = []
        seen_ids: set = set()
        for p in products:
            if p.id in seen_ids or position_for(p) is None:
                continue
            seen_ids.add(p.id)
            unique.append(p)
        if len(unique) < MIN_ITEMS:
            return None
        unique.sort(key=lambda p: float(getattr(p, "base_price", 0) or 0))
        shortlist = unique[:MAX_CANDIDATES]
        offered = {p.id: p for p in shortlist}

        prompt = _build_prompt(_candidate_rows(shortlist), intent)

        # Two attempts maximum. Temperature 0 because this is a structured
        # extraction task, not a creative one: the same shortlist should produce
        # the same outfit, and a shopper must not see a different look on refresh.
        # The retry exists because a small model occasionally returns one item or
        # an unwearable shape; a corrective second pass is cheaper than losing the
        # model's judgement entirely, and it is still bounded.
        correction = ""
        for attempt in (1, 2):
            try:
                result = await self._client.chat(
                    system_prompt=SYSTEM_PROMPT,
                    user_prompt=prompt + correction,
                    max_tokens=600,
                    temperature=0.0,
                )
            except WatsonxAuthError as exc:
                logger.warn("watsonx list builder skipped: auth", reason=type(exc).__name__)
                return None
            except Exception as exc:  # noqa: BLE001 - never fail a request over this
                logger.warn("watsonx list builder skipped", reason=type(exc).__name__)
                return None

            if result is None:
                return None
            content, model_id = result

            payload = _extract_json(content)
            if payload is None:
                logger.info("watsonx list builder: unparseable answer", model=model_id)
                return None

            try:
                chosen = validate_selection(payload, offered)
            except ValidationError as exc:
                # Logged with the reason only - never the raw answer, which can be
                # arbitrarily long and may quote catalogue copy. An invented id is
                # NOT retried: a model that fabricates products once is not asked
                # to try again.
                logger.info("watsonx list builder: rejected", reason=str(exc), model=model_id)
                return None

            if _coverage_ok(chosen):
                title = str(payload.get("title") or "").strip()[:80] or None
                return {
                    "items": [{"product": p, "reason": reason} for p, reason in chosen],
                    "title": title,
                    "model_id": model_id,
                }

            logger.info("watsonx list builder: incomplete shape", model=model_id, attempt=attempt)
            if attempt == 1:
                correction = (
                    "\n\nYour previous answer could not be used: it was not a wearable "
                    "outfit. Choose a dress on its own, OR a top with a bottom, plus "
                    "footwear. Never a dress together with a bottom."
                )

        return None


#: Process-wide builder. The underlying client owns the IAM token cache.
watsonx_list_builder = WatsonxListBuilder()
