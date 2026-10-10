"""Reproduce the repeated-answer path: run the REAL StylistService up to the model
call, record exactly what the model would receive, and stub only the provider."""
import asyncio, json, sys
from backend.app.core.database import SessionLocal
from backend.app.services.stylist_service import StylistService
from backend.app.schemas.stylist import StylistPromptRequest  # noqa: F401

PROMPTS = [
    "What should I wear to a formal wedding?",
    "Analyze this outfit and tell me why the colors don't work.",
    "Build an outfit around these navy trousers.",
    "Recommend an affordable casual outfit using items I already own.",
    "I have a white shirt, black vest, olive trousers and black jeans. Make 6 formal outfits for work.",
    "ما هو أفضل لون حذاء للبدلة الكحلية؟",
    "Give me a weekend look for brunch in Cairo.",
]

class Stub:
    def __init__(self): self.calls = []
    async def generate_styling_advice(self, **kw):
        self.calls.append(kw)
        return {"styling_advice_text": "STUB", "provider_used": "STUB"}

async def main():
    db = SessionLocal()
    svc = StylistService(db)
    stub = Stub()
    svc.orchestrator = stub
    out = []
    for p in PROMPTS:
        stub.calls.clear()
        r = await svc.interact_with_stylist(user_id=None, prompt=p, include_wardrobe_items=False)
        kw = stub.calls[-1]
        items = [i.get("product_title") for i in (kw["selected_outfit"] or {}).get("items", [])] if kw.get("selected_outfit") else []
        out.append({
            "prompt": p,
            "occasion": (kw.get("intent") or {}).get("occasion"),
            "style_source": (kw.get("intent") or {}).get("style_source"),
            "llm_sees_history": False,
            "llm_user_prompt_contains_question": p in str(kw.get("prompt")),
            "selected_items": items,
            "n_alternates": len(kw.get("alternate_outfits") or []),
            "content_engine_recs": [o.get("name") or o.get("title") for o in r.get("recommendations", [])],
        })
    print(json.dumps(out, ensure_ascii=False, indent=1))
    db.close()

asyncio.run(main())
