# Architecture — stylist feature in context

Platform-level architecture (all domains, specs, data model) is in
`CONFIT_Architecture_Master_Specification.md`; the README has the one-screen
overview. This page covers the **wardrobe stylist** slice end-to-end and how it runs
locally without any hosted provider.

```
 Browser (React 18 + TS, Vite, i18next EN/AR RTL)
   WardrobeView ─ tab "AI Stylist" ─► WardrobeStylistPanel.tsx
        │  cookie session (httpOnly) + CSRF; /api/* proxied by Vite in dev
        ▼
 FastAPI  backend/app/api/v1/endpoints/wardrobe*.py
   POST /wardrobe/items            ─► wardrobe_service  ─► wardrobe_taxonomy (normalise category/colour/pattern)
   POST /wardrobe/outfit-recommendation (40/h/user)
        │
        ▼
   wardrobe_stylist_service.py
     1. load caller's wardrobe (id-tagged)           ─ PostgreSQL (SQLAlchemy 2, Alembic 0001…0048)
     2. apply colour exclusions (server-side)
     3. provider switch  WARDROBE_STYLIST_PROVIDER
          watsonx ──► providers/watsonx/client.py ──► IBM watsonx.ai  POST /ml/v1/text/chat
                      (IAM cache, retries, error taxonomy)      model: WATSONX_REASONING_MODEL_ID
                      prompts.py  wx-stylist-1.1 (system + id-tagged closet + context)
          deterministic ──► _deterministic() rule matcher (no network)
     4. validate every cited id ∈ caller's wardrobe; role from stored category
     5. complete missing core positions by rules (selected_by=rule_matcher, disclosed)
     6. reconcile prose with final items (D10), compute fit_status (D11)
     7. OutfitRecommendation {items[], summary, limitations, source, model_id,
                              prompt_version, ai_generated, fit_status, …}
   POST /wardrobe/outfits  ─► wardrobe_outfit_service (re-validates ids, keeps provenance)
   GET  /health            ─► liveness + schema gate (Alembic head) + capability states
```

## Key properties

* **Provenance is data, not decoration.** `source`, `model_id`, `prompt_version`,
  `ai_generated`, per-item `selected_by` travel with every answer and are persisted
  with saved looks; the UI only renders them. A double or the rule matcher can never
  appear as Granite (tests FR-18, D13).
* **Model ids and endpoints are configuration** (`core/config.py`); deploy-on-demand
  routing is a config flip (`WATSONX_*_DEPLOYMENT_ID`).
* **Validation happens after the model**, on ids, roles, colours and prose — the model
  is treated as an untrusted suggester.
* **Database**: PostgreSQL is the reference engine (migrations include PG-only
  provenance triggers, 0024). SQLite remains for fast unit loops only.
  Driver selection: `POSTGRES_DRIVER_POLICY.md`.
* **Runs anywhere**: `scripts/dev/*` + `docker-compose.dev.yml` give a full local stack
  (PostgreSQL + API + SPA) with the AI mode chosen explicitly
  (`local-development.md`). Hosted providers (Neon, Vercel, Cloudflare, Redis) are
  deployment concerns only (`deployment-recovery.md`).

## Where things live

| Concern | Path |
|---|---|
| Stylist service / rules / Arabic labels | `backend/app/services/wardrobe_stylist_service.py` |
| Taxonomy (categories, colour families EN+AR, occasions, seasons) | `backend/app/services/wardrobe_taxonomy.py` |
| watsonx client / prompts / vision | `backend/app/providers/watsonx/{client,prompts,vision}.py` |
| Schemas (request validation, response contract) | `backend/app/schemas/wardrobe_stylist.py` |
| Migrations | `backend/alembic/versions/0047_*`, `0048_*` |
| UI panel + saved looks | `frontend/src/components/wardrobe/WardrobeStylistPanel.tsx`, `SavedWardrobeLooks.tsx` |
| i18n | `frontend/src/i18n/{en,ar}.json` (`wardrobe_stylist.*`) |
| Quality eval (16 scenarios, H1–H13) | `scripts/eval/wardrobe_stylist_quality_eval.py` |
| Load harness + watsonx double | `scripts/load/` |
| Local dev scripts | `scripts/dev/` |
