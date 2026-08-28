from typing import Dict, Any


class GroundingGenerator:
    """Generates natural language styling descriptions grounded strictly on selected items."""

    @classmethod
    def generate_grounded_text(
        cls,
        prompt: str,
        outfit: Dict[str, Any],
        intent: Dict[str, Any]
    ) -> str:
        items = outfit.get("items", [])
        occasion = intent.get("occasion", "Special Event")
        aesthetic = intent.get("aesthetic", "Quiet Luxury")
        total_price = outfit.get("total_price", 0.0)

        item_by_pos = {it.get("position"): it for it in items}

        if "dress" in item_by_pos:
            dress = item_by_pos["dress"]
            shoes = item_by_pos.get("footwear")
            acc = item_by_pos.get("accessory")

            text = (
                f"For your {occasion} occasion, I have styled a complete {aesthetic} look centered around the "
                f"{dress['brand_name']} {dress['product_title']} in {dress.get('color_family', 'Champagne Gold')}. "
            )
            if shoes:
                text += f"We paired it with {shoes['brand_name']} {shoes['product_title']} to elevate the silhouette, "
            if acc:
                text += f"and accented with the {acc['brand_name']} {acc['product_title']}. "
            text += f"The full ensemble totals ${total_price:.2f}, delivering flawless drape and occasion-appropriate elegance."
            return text

        outer = item_by_pos.get("outerwear")
        top = item_by_pos.get("top")
        bottom = item_by_pos.get("bottom")
        shoes = item_by_pos.get("footwear")
        acc = item_by_pos.get("accessory")

        parts = []
        if outer:
            parts.append(f"the {outer['brand_name']} {outer['product_title']} ({outer.get('color_family', 'Navy')})")
        if top:
            parts.append(f"the {top['brand_name']} {top['product_title']}")
        if bottom:
            parts.append(f"matching {bottom['brand_name']} {bottom['product_title']}")
        if shoes:
            parts.append(f"{shoes['brand_name']} {shoes['product_title']}")
        if acc:
            parts.append(f"{acc['brand_name']} {acc['product_title']}")

        items_str = ", ".join(parts[:3])
        if len(parts) > 3:
            items_str += f", and {parts[3]}"
        if len(parts) > 4:
            items_str += f" with {parts[4]}"

        text = (
            f"Here is your grounded {occasion} ensemble tailored to your {aesthetic} profile. "
            f"I curated a cohesive look featuring {items_str}. "
            f"Every piece aligns in silhouette, fabric texture, and color harmony, bringing the complete shoppable look to ${total_price:.2f}."
        )
        return text
