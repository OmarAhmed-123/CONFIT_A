from typing import List, Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class DynamicPromptPackage:
    """Structured output emitted by the Internal Dynamic Prompt Builder."""
    system_prompt: str
    task_prompt: str
    negative_prompt: str
    identity_constraints: Dict[str, str]
    garment_constraints: List[Dict[str, Any]]
    layering_constraints: List[str]
    render_directives: Dict[str, Any]
    suitability_warnings: List[str]
    unsupported_warnings: List[str]
    truthfulness_flags: Dict[str, bool]
    assembled_prompt_text: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "system_prompt": self.system_prompt,
            "task_prompt": self.task_prompt,
            "negative_prompt": self.negative_prompt,
            "identity_constraints": self.identity_constraints,
            "garment_constraints": self.garment_constraints,
            "layering_constraints": self.layering_constraints,
            "render_directives": self.render_directives,
            "suitability_warnings": self.suitability_warnings,
            "unsupported_warnings": self.unsupported_warnings,
            "truthfulness_flags": self.truthfulness_flags,
            "assembled_prompt_text": self.assembled_prompt_text
        }


class InternalDynamicPromptBuilder:
    """Production-Grade Automated Prompt Construction Engine for Virtual Try-On.
    Translates user image reference, product metadata, slot ontology, and operation mode
    into strict identity-preserving, category-aware rendering instructions behind the scenes.
    """

    @classmethod
    def build_prompt_package(
        cls,
        user_image_ref: str,
        applied_items: List[Dict[str, Any]],
        gender_mode: str = "infer_from_image",
        pose_mode: str = "standing_front",
        output_mode: str = "full_body",
        background_mode: str = "luxury_studio",
        operation_type: str = "full_outfit_apply",
        image_suitability: Optional[Dict[str, Any]] = None,
        animation_mode: bool = False,
        output_aspect: str = "9:16"
    ) -> DynamicPromptPackage:
        suitability_warnings = []
        unsupported_warnings = []
        truthfulness_flags = {
            "is_exact_twin_mode": True,
            "is_preview_limited": False,
            "footwear_calibrated": False,
            "headwear_deferred": False
        }

        # 1. Identity Constraints
        identity_constraints = {
            "face_lock": "Strict mandatory preservation of exact facial geometry, eyes, nose, lips, jawline, beard/clean-shave, glasses, and expression.",
            "hair_lock": "Preserve exact hairstyle, hairline contour, and hair color.",
            "skin_tone": "Maintain natural skin tone, complexion, and ambient lighting response without artificial beautification or tone shifting.",
            "body_silhouette": "Preserve exact shoulder breadth, torso length, waist-to-hip ratio, and height baseline.",
            "posture_baseline": f"Respect baseline posture ({pose_mode}) without synthetic limb manipulation."
        }

        # 2. Garment Constraints and Normalization
        garment_constraints = []
        ordered_items = sorted(applied_items, key=lambda x: x.get("layer_order", 1))

        has_footwear = False
        has_dress = False

        for it in ordered_items:
            pos = it.get("position", "garment")
            cat = it.get("category_name", "Apparel")
            title = it.get("product_title", "")
            brand = it.get("brand_name", "CONFIT")
            color = it.get("color_family", "Coordinated")
            material = it.get("material", "Fine Fabric")
            price = it.get("price", 0.0)

            # Detect unsupported or deferred categories (e.g. headwear/hats that obscure face)
            if "hat" in title.lower() or "cap" in title.lower() or "helmet" in title.lower():
                unsupported_warnings.append(f"Headwear '{title}' deferred from try-on to guarantee 100% facial identity preservation.")
                truthfulness_flags["headwear_deferred"] = True
                continue

            if pos == "footwear":
                has_footwear = True
                truthfulness_flags["footwear_calibrated"] = True
            if pos == "dress":
                has_dress = True

            garment_constraints.append({
                "slot": pos.upper(),
                "layer_order": it.get("layer_order", 1),
                "title": title,
                "brand": brand,
                "category": cat,
                "color": color,
                "material": material,
                "price": price,
                "fit_directive": f"Drape {material} faithfully according to catalog cut with authentic seams, buttons, and texture."
            })

        # 3. Layering & Conflict Constraints
        layering_constraints = []
        if has_dress:
            layering_constraints.append("Dress acts as full-body primary foundation; separate tops and trousers are cleared.")
            layering_constraints.append("Outerwear layers cleanly over dress shoulders and chest.")
        else:
            layering_constraints.append("Base shirt/top fits naturally across torso (Layer 2).")
            layering_constraints.append("Tailored outerwear layers over shirt with open lapels (Layer 4).")
            layering_constraints.append("Trousers fall vertically with pressed creases (Layer 10).")

        if has_footwear:
            layering_constraints.append("Footwear aligns symmetrically to both feet with accurate ground contact and perspective (Layer 20).")
        layering_constraints.append("Accessories attach strictly to designated zones without clipping (Layer 30).")

        # 4. Image Suitability Adjustments
        if image_suitability:
            if not image_suitability.get("is_valid", True):
                suitability_warnings.append("Image resolution or framing is sub-optimal; rendering applied with soft edge blending.")
                truthfulness_flags["is_preview_limited"] = True
            if "stone" in str(image_suitability.get("suggestions", [])).lower() or "outdoor" in str(image_suitability.get("lighting_quality", "")).lower():
                suitability_warnings.append("Outdoor ground detected: contact shadows calibrated for textured surface.")

        # 5. Render Directives
        render_directives = {
            "output_mode": output_mode,
            "background_mode": background_mode,
            "lighting": "Soft key light with natural ambient fill and realistic contact shadows",
            "aspect_ratio": output_aspect,
            "operation_type": operation_type
        }

        # 6. Dynamic Negative Prompts
        negative_prompt_parts = [
            "face swap", "identity drift", "different person", "altered ethnicity",
            "body slimming", "body bulking", "body reshaping",
            "duplicate garments", "duplicate collars", "duplicate sleeves", "duplicate waistbands",
            "wrong garment category", "recolored product", "distorted fabric", "clipping",
            "transparent body parts", "extra limbs", "broken fingers", "missing feet",
            "cartoon rendering", "mannequin effect", "fake fashion sketch", "low-quality artifacts"
        ]
        if has_footwear:
            negative_prompt_parts.extend(["floating shoes", "mismatched feet", "ankle clipping", "hovering footwear"])
        if has_dress:
            negative_prompt_parts.extend(["trousers under dress", "overlapping skirt pants"])

        negative_prompt = ", ".join(negative_prompt_parts)

        # 7. Assemble Full Dynamic Prompt Text
        system_prompt = (
            "You are CONFIT's Internal Automated Virtual Try-On Engine. Your task is to dress the real human subject "
            "from the reference image with the exact specified catalog garments while enforcing absolute identity preservation."
        )

        items_formatted = []
        for idx, g in enumerate(garment_constraints, start=1):
            if animation_mode:
                items_formatted.append(f"  Step {idx}. Slot [{g['slot']}]: {g['title']} by {g['brand']} ({g['color']}, {g['material']}, ${g['price']:.2f}) — {g['fit_directive']}")
            else:
                items_formatted.append(f"  {idx}. Slot [{g['slot']}]: {g['title']} by {g['brand']} ({g['color']}, {g['material']}, ${g['price']:.2f}) — {g['fit_directive']}")

        items_text = "\n".join(items_formatted) if items_formatted else "  1. Catalog clothing piece."

        if animation_mode:
            task_prompt = f"""=== CONFIT DYNAMIC ANIMATION TRY-ON SPECIFICATION ===
[OPERATION]: {operation_type.upper()} | ASPECT: {output_aspect} | BACKGROUND: {background_mode}
[TARGET USER IMAGE REFERENCE]: {user_image_ref}
[USER GENDER PRESENTATION]: {gender_mode}
[IDENTITY PRESERVATION — MANDATORY]: STRICT MANDATORY PRESERVATION (Face, hair, skin tone, body silhouette, height baseline preserved)

[DYNAMIC GARMENT TRANSFER SEQUENCE]:
{items_text}

[PHYSICAL REALISM & FOOTWEAR TRANSFER]:
  - Realistic cloth kinematics: natural unfold, body collision, gravity draping, and fold settling.
  - Footwear aligns to both feet with accurate ground contact, perspective, and ankle transition without hovering.
  - Final State: User is wearing the complete selected outfit with clean final layering, holding on a premium final frame."""
        else:
            task_prompt = f"""=== CONFIT AUTOMATED IDENTITY-PRESERVING VTON DIRECTIVES ===
[OPERATION MODE]: {operation_type.upper()} | OUTPUT MODE: {output_mode} | BACKGROUND: {background_mode}
[TARGET USER IMAGE REFERENCE]: {user_image_ref}
[USER GENDER PRESENTATION]: {gender_mode}
[POSE CONSTRAINT]: {pose_mode} (Preserve original posture baseline and stance)
[BODY & FACE PRESERVATION POLICY]: STRICT MANDATORY PRESERVATION (Face, hair, skin tone, body silhouette, height baseline preserved)

[SELECTED CATALOG GARMENTS TO APPLY]:
{items_text}

[ANATOMICAL LAYERING & DRESSING DIRECTIVES]:
  - """ + "\n  - ".join(layering_constraints)

        assembled_prompt_text = f"""{system_prompt}

{task_prompt}

[NEGATIVE PROMPT / RESTRICTIONS]:
  {negative_prompt}"""

        return DynamicPromptPackage(
            system_prompt=system_prompt,
            task_prompt=task_prompt,
            negative_prompt=negative_prompt,
            identity_constraints=identity_constraints,
            garment_constraints=garment_constraints,
            layering_constraints=layering_constraints,
            render_directives=render_directives,
            suitability_warnings=suitability_warnings,
            unsupported_warnings=unsupported_warnings,
            truthfulness_flags=truthfulness_flags,
            assembled_prompt_text=assembled_prompt_text
        )
