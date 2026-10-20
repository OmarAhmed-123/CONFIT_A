# Dataset selection for the CONFIT_A storefront

**Status:** decision basis only — **nothing is imported by this document.**
**Created:** 2026-10-20 · **Slice:** catalog track, licence-first (turn 17)
**Scope:** docs only. No data import, no `backend/app` change, no migration.

> **Rule this document exists to satisfy.** The storefront needs real catalog data, but no
> dataset enters the product until a **lawful** one is chosen and the owner signs off on its
> licence. This file produces that decision basis; the import build is the following slice.

**Evidence standard.** Every licence below is **quoted from the source page, fetched on
2026-10-20**, not recalled. The exact excerpts are reproduced in §7 with their URLs. Where a
licence does not plainly permit commercial use in a resale context, the row is marked
**NEEDS-OWNER-CONFIRM** rather than asserted.

---

## 1. Decision summary

| # | Source | Licence (short) | Commercial resale-context use | Verdict |
|---|---|---|---|---|
| A | DeepFashion (CUHK MMLab) | Research-only | **No** — text forbids it | **REJECT** |
| B | H&M Personalized Fashion Recommendations (Kaggle competition) | Competition terms | **No** — non-commercial | **REJECT** |
| C | Fashion Product Images (Small) — Kaggle dataset | Self-declared "MIT" | **Unknown** — uploader likely holds no rights | **REJECT** + NEEDS-OWNER-CONFIRM |
| D | Fashionpedia (CVDF / Cornell Tech) | No dataset-level licence | **Unknown** — per-image licences | **NEEDS-OWNER-CONFIRM** |
| E | Fashion-MNIST (Zalando SE) | MIT | **Yes** | **REJECT on fit** (lawful, unusable) |
| F | **Unsplash** | Unsplash License | **Yes** — explicit | **RECOMMENDED** (images) |
| G | Pexels | Pexels License | **Yes** — explicit, names e-commerce | **APPROVED secondary** |

**Recommendation: Unsplash License** as the image basis, with **Pexels** as the co-approved
secondary. Both are already the source of record for the 50 stock images in production
(§3), and both are already permitted by the site's CSP (§6.1) — so the recommendation adds
no new third-party surface.

**It is a photo licence, not a product feed.** It supplies images and nothing else: no
titles, no prices, no categories, no SKUs. Those fields must be authored. See §5 — this is
the single most important limitation in this document and the reason the import build
cannot simply "load a dataset".

---

## 2. Evaluated sources

### A. DeepFashion — **REJECT** (non-commercial, research-only)

| | |
|---|---|
| **Name** | Large-scale Fashion (DeepFashion) Database |
| **Source URL** | https://mmlab.ie.cuhk.edu.hk/projects/DeepFashion.html |
| **Licence (verbatim)** | "The DeepFashion is available for **non-commercial** research purposes only." |
| **Also (verbatim)** | "You agree **not to** reproduce, duplicate, copy, sell, trade, resell or exploit for any commercial purposes, any portion of the images and any portion of derived data." |
| **Commercial verdict** | **NO.** Not ambiguous. The prohibition names "sell, trade, resell" and "derived data" explicitly. |
| **Image rights** | "All images of the DeepFashion are obtained from the Internet which are not property of MMLAB, The Chinese University of Hong Kong." — CUHK cannot grant rights it does not hold, and says so. |
| **Size / fields** | 800,000+ images; 50 categories; 1,000 descriptive attributes; bounding boxes; clothing landmarks; 300,000+ cross-pose pairs. Access to three of the four benchmarks is gated behind a **signed** agreement with an institutional email. |
| **Fit for CONFIT_A** | Superb on paper (categories, attributes, landmarks, in-shop photography) — which is exactly why the rejection matters. Its structure would map cleanly onto `Category`/`Product`/`ProductSKU`. **Irrelevant: the licence forbids the use.** |
| **Rejection reason** | Non-commercial / research-only licence. Serving these images or derived data in a commercial storefront is the specific act the licence prohibits. |

### B. H&M Personalized Fashion Recommendations — **REJECT** (competition-only)

| | |
|---|---|
| **Name** | H&M Personalized Fashion Recommendations (Kaggle competition) |
| **Source URL** | https://www.kaggle.com/competitions/h-and-m-personalized-fashion-recommendations/rules |
| **Licence (verbatim)** | "**DATA ACCESS AND USE**: Non-Commercial Purposes & Academic Research" |
| **Also (verbatim)** | "Privately sharing code or data outside of teams is not permitted." |
| **Commercial verdict** | **NO.** The competition-specific terms state the permitted purpose directly. |
| **Image rights** | H&M Hennes & Mauritz GBC AB is the sponsor; the terms grant rights **to the sponsor** over participants' winning submissions, not to participants over H&M's imagery. The direction of the grant is the opposite of what a storefront would need. |
| **Size / fields** | Transaction-level data (customers, articles, purchases) plus article metadata and article images — a genuine retail catalogue with real prices. |
| **Fit for CONFIT_A** | Structurally the closest thing to what a storefront wants: real articles, real prices, real images. |
| **Rejection reason** | **Competition-only terms.** This is the canonical trap: a dataset that is free to download, models well, and is licensed for the one thing we are not doing. Note also that accepting competition rules is a personal agreement with the sponsor, not a redistribution licence we could extend to a shop. |

### C. Fashion Product Images (Small) — **REJECT**, and **NEEDS-OWNER-CONFIRM** on the licence field

| | |
|---|---|
| **Name** | Fashion Product Images (Small) — 44,000 products with category labels and images |
| **Source URL** | https://www.kaggle.com/datasets/paramaggarwal/fashion-product-images-small |
| **Licence (verbatim, the Kaggle metadata field)** | "## License — [MIT](https://www.mit.edu/~amini/LICENSE.md)" |
| **What the page says about provenance (verbatim)** | "Thr growing e-commerce industry presents us with a large dataset waiting to be scraped and researched upon." |
| **Commercial verdict** | **UNKNOWN — do not rely on the "MIT" field.** The licence is a *self-declared metadata field filled in by the uploader*, and its link target is a personal page at `mit.edu`, not the MIT licence text. |
| **Image rights** | The images are product photography scraped from the Myntra catalogue. The `productDisplayName` column carries **third-party brands** (Puma, Fila, Fabindia, John Players, Disney, Fossil, Titan, Adidas, Timberland…). The uploader does not hold the copyright in those photographs or trademarks and therefore cannot license them, whatever the field says. |
| **Size / fields** | 44,000 products (larger 2400×1600 variant available); `styles.csv` columns: `id`, `gender`, `masterCategory`, `subCategory`, `articleType`, `baseColour`, `season`, `year`, `usage`, `productDisplayName`. |
| **Fit for CONFIT_A** | Excellent field shape — `masterCategory`/`subCategory`/`articleType` collapse neatly into our 6 categories; `baseColour` maps to `color_family`; `usage` maps to `occasion_tags`. **No price column**, so prices would still be authored. |
| **Rejection reason** | A licence field cannot launder a third party's copyright. Presenting Puma's photograph as a CONFIT_A catalogue item is a trademark and copyright exposure regardless of what a CSV column says. |
| **NEEDS-OWNER-CONFIRM** | If the owner wants this data, the question to answer is *not* "is it MIT?" but "does the owner have written permission from Myntra and from each named brand?" Nothing short of that makes it safe. |

### D. Fashionpedia — **NEEDS-OWNER-CONFIRM** (no dataset-level licence)

| | |
|---|---|
| **Name** | Fashionpedia (ontology + annotated image dataset) |
| **Source URLs** | https://fashionpedia.github.io/home/index.html · https://github.com/cvdfoundation/fashionpedia · https://fashionpedia.github.io/home/Fashionpedia_download.html |
| **Licence** | **No dataset-level licence statement exists on either the project page or the annotations repository README** (verified by reading both on 2026-10-20). |
| **What exists instead (read)** | COCO-style annotations carry a per-image `"license" : int` field and a top-level `"licenses": [license]` array, where `license { "id": int, "name": str, "url": str }`. Rights are therefore **per image**, and the images are sourced from the open web. |
| **Commercial verdict** | **UNKNOWN.** Not a rejection — but not a grant either. A blanket "this dataset is commercially usable" claim would be unsupported. Any use requires filtering images by their individual licence entry and retaining the attribution the entry names. |
| **Image rights** | Per-image, via the `licenses` array. Some entries will be commercially usable; some will not. |
| **Size / fields** | 48,825 images; 27 main apparel categories; 19 apparel parts; 294 fine-grained attributes; instance segmentation masks; bbox; per-mask attributes. Ontology is expert-built and explicitly mapped to DeepFashion2 and ModaNet classes. |
| **Fit for CONFIT_A** | The **ontology** is the valuable part: 27 categories + 294 attributes is a far better taxonomy than our 6 seeded categories, and it is a *description*, not a photograph — reusing a category vocabulary raises no image-rights question. The images are the risky half. |
| **NEEDS-OWNER-CONFIRM** | Two separate decisions: (1) may we adopt the **category/attribute vocabulary** (low risk, likely yes — cite the paper); (2) may we use **specific images** whose `licenses` entry is commercial (requires per-image triage, not a dataset decision). Do not treat these as one question. |

### E. Fashion-MNIST — **REJECT on fit** (licence is clean, data is useless for a shop)

| | |
|---|---|
| **Name** | Fashion-MNIST — a MNIST-like fashion product database |
| **Source URL** | https://github.com/zalandoresearch/fashion-mnist |
| **Licence (verbatim, `LICENSE`)** | "The MIT License (MIT) Copyright © 2017 Zalando SE, https://tech.zalando.com" — "Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or **sell** copies of the Software…" |
| **Commercial verdict** | **YES.** Cleanest licence of the seven. |
| **Image rights** | MIT, from Zalando SE. |
| **Size / fields** | 70,000 images, **28×28 greyscale**, 10 classes (T-shirt/top, Trouser, Pullover, Dress, Coat, Sandal, Shirt, Sneaker, Bag, Ankle boot). No product URL, no price, no size, no colour, no SKU. |
| **Fit for CONFIT_A** | **None.** A 28×28 greyscale thumbnail cannot serve a premium editorial storefront, and there is not one field that maps to `base_price`, `title_ar`, `thumbnail_url`, or `sku_code`. |
| **Rejection reason** | Lawful but unusable. Recorded deliberately: it demonstrates that "commercially licensed" and "usable" are different tests, and that the first does not imply the second. |
| **Legitimate use** | As a **model-training** set for classification/embedding work (e.g. `style_embedding`), where a 28×28 greyscale input is acceptable. Not as catalogue content. |

### F. Unsplash — **RECOMMENDED**

| | |
|---|---|
| **Name** | Unsplash (photo library + API) |
| **Source URL** | https://unsplash.com/license |
| **Licence (verbatim)** | "Unsplash grants you an irrevocable, nonexclusive, worldwide copyright license to download, copy, modify, distribute, perform, and use images from Unsplash for free, including for commercial purposes, without permission from or attributing the photographer or Unsplash. This license does not include the right to compile images from Unsplash to replicate a similar or competing service." |
| **Also (verbatim)** | "All images can be **downloaded** and used for **free**" · "**Commercial** and **non-commercial** purposes" · "**No permission needed** (though attribution is appreciated!)" |
| **Prohibitions (verbatim)** | "Images cannot be **sold** without significant modification." · "Compiling images from Unsplash to replicate a similar or competing service." |
| **Commercial verdict** | **YES.** An irrevocable, worldwide copyright licence that names commercial purposes. The two prohibitions do not bite here: we are not selling the photographs as photographs, and we are not building a stock-photo service. |
| **Image rights** | Licensed by Unsplash. Note: Unsplash cannot grant model or property releases; see §4. |
| **Size / fields** | Photographs and metadata only — no product titles, no prices, no categories, no SKUs. |
| **Fit for CONFIT_A** | Photographs of garments, on-model and flat-lay, at high resolution with 4:5-friendly framing. Directly usable for `thumbnail_url`/`images` and for the derived-media ladder. **Already in production:** 20 of the 54 registered `product_images` rows are `provider='unsplash'` (§3). |

### G. Pexels — **APPROVED secondary**

| | |
|---|---|
| **Name** | Pexels (photo + video library) |
| **Source URL** | https://www.pexels.com/license/ |
| **Licence (verbatim)** | "All photos and videos on Pexels can be downloaded and used for free." · "Attribution is not required." · "You can modify the photos and videos from Pexels. Be creative and edit them as you like." |
| **Explicit use cases (verbatim)** | "### On your website, blog or app — Use the photos and videos online – whether it's a website, **e-commerce shop**, newsletter, e-book, presentation, blog or a template you sell." |
| **Prohibitions (verbatim)** | "Don't sell unaltered copies of a photo or video, e.g. as a poster, print or on a physical product without modifying it first." · "Don't imply endorsement of your product by people or brands on the imagery." · "Don't redistribute or sell the photos and videos on other stock photo or wallpaper platforms." · "Don't use the photos or videos as part of your trade-mark, design-mark, trade-name, business name or service mark." |
| **Commercial verdict** | **YES** — and it is the only one of the seven that names "**e-commerce shop**" as an allowed use in so many words. |
| **Image rights** | Licensed by Pexels. Model/property releases are not granted; see §4. |
| **Size / fields** | Photographs only. |
| **Fit for CONFIT_A** | **Already the majority source in production:** 30 of 54 registered rows are `provider='pexels'`. The "don't imply endorsement" clause is the one to respect when a photo shows a person wearing the garment. |

---

## 3. Current catalog state — why a photo licence is the right shape of answer

Measured read-only against production Neon on 2026-10-20 (§6.2 for the method):

| Measure | Value |
|---|---|
| `products` | **12** — 9 from the demo seed, **3** created through the real import path (slug `brand-<id>-<hash>`) |
| `product_skus` | 28 |
| `product_images` | 54 — `stock` 50 · `generated` 4; by provider `pexels` 30, `unsplash` 20, `generated` 4 |
| `categories` | 6 — outerwear, tops, bottoms, dresses, footwear, accessories |
| `brand_profiles` | 4 |
| price range | 75.00 – 395.00, **all `USD`** |
| `alembic_version` | `0041_photo_index` |

Two consequences:

1. **The lawful photo path already exists and already works.** 50 of 54 registered images
   are Pexels/Unsplash. The recommendation in §1 is therefore an *extension of the current,
   audited practice*, not a new legal posture.
2. **4 `generated` images are a known temporary.** The media plan's own rule states:
   *"Every product has an image source. Stock photos are licensed (Pexels, Unsplash).
   Generated visuals are AI illustrations and must be replaced with photographs before a
   public launch."* (`backend/scripts/data/product_image_plan_2026-10-09.json`, `rule`).
   Two products — `structured-metallic-evening-box-clutch` and
   `brand-4-57ad561648ff0fe831b25730` — still carry AI illustrations.

---

## 4. What the recommendation does **not** give you — **NEEDS-OWNER-CONFIRM**

Stock-photo licences cover **copyright in the photograph**. They do not cover:

1. **Model releases.** A photo of a person wearing a garment is licensed for the *image*;
   the model has not agreed to endorse CONFIT_A. Pexels forbids implying endorsement
   outright ("Don't imply endorsement of your product by people or brands on the imagery").
   Presenting such a photo as "our model wearing our shirt" is the risk.
2. **Trade dress / brand marks.** Visible logos on garments or props are third-party
   trademarks. Neither licence grants trademark rights.
3. **Truthfulness of the catalogue.** A stock photograph of *a* navy blazer used as the
   picture for a *specific* SKU is a claim about that SKU. The codebase already treats this
   as a trust defect, not a legal nicety — `product_media_service.media_payload()` documents
   that "a stock editorial picture presented as a boutique's own product shot is a trust
   defect, and the label has to come from the same row that holds the file", and
   `ProductImage.source_type` is constrained to `stock | own | partner` and "Never inferred
   in the UI" (`backend/app/models/catalog.py`).

**Owner decision needed (one of):**

- **(a)** Import as `source_type='stock'` with `provider` and `attribution` populated, and let
  the UI label stock imagery honestly. *This is consistent with the code as written.*
- **(b)** Treat the imported catalogue as **placeholder** content, visually marked as demo
  data, until real partner photography exists.
- **(c)** Do not import stock imagery at all; author rows with `source_type='own'` only.

I am **not** asserting that (a) is settled. It is the option the existing code anticipates,
which is why it is recommended — but it is the owner's call, and the answer changes what the
import build writes into `product_images`.

---

## 5. What must be authored — the dataset cannot supply it

Neither Unsplash nor Pexels carries a single field that maps to a required column of our
import contract. Required by `BrandCatalogService.REQUIRED_FIELDS`
(`backend/app/services/brand_catalog_service.py:49`):
`title`, `category_slug`, `base_price`, `color_family`, `thumbnail_url`.

| Field | Source | Note |
|---|---|---|
| `thumbnail_url` | **dataset** | The only required field a photo licence fills |
| `title` | authored | Must be a real garment description |
| `title_ar` | authored | NOT NULL and Arabic in all 12 production rows. The import **silently falls back to the English `title`** when `title_ar` is absent (`brand_catalog_service.py:439`), which would put Latin text in an RTL storefront |
| `base_price` | authored / owner | No evaluated dataset supplies a price for CONFIT_A's currency |
| `category_slug` | mapped | Must be one of the 6 existing slugs — see the defect in §6.3 |
| `color_family`, `size`, `stock_level` | authored | `size` defaults to `'M'`, `stock_level` to 0 if omitted |
| `description`, `material`, `style_tags`, `occasion_tags` | authored | Bounded arrays; `occasion_tags` can be informed by a dataset's `usage` column |

**The honest summary:** the lawful datasets give us *pictures of clothes*. A catalogue is
*pictures plus claims about specific sellable items*. Everything in the second category —
price, title, Arabic title, size run, stock, category — is authored or supplied by the
owner/partner. That is the work the import slice actually has to do, and it is why this
slice stops at a decision.

---

## 6. Constraints the eventual import will hit

### 6.1 CSP — only four image hosts are permitted today

`vercel.json:43` sets:

```
img-src 'self' data: blob: https://images.unsplash.com https://images.pexels.com
        https://placehold.co https://br-mute-waterfall-b2p706dr.storage.c-6.eu-central-1.aws.neon.tech
```

Consequences:

- **Unsplash and Pexels host URLs render as-is.** No policy change needed — a concrete
  reason to prefer them over any other source.
- **Any other image host will be blocked by the browser**, so a dataset served from, say,
  an S3 bucket or a retailer CDN cannot be linked directly. Either re-host through the
  verified media route (`img-src 'self'`, `backend/app/controllers/media_controller.py:68`)
  or **widen the CSP** — which is a security-policy change and needs owner sign-off, not a
  side effect of an import.
- Uploaded/derived assets should go to the private bucket and be served through
  `/api/v1/media/...` (`read_media_object`, `backend/app/services/storage_service.py:518`).

### 6.2 The import path does **not** write the media registry

Verified by reading: `backend/app/services/brand_catalog_service.py` contains **no reference
to `ProductImage`**. The import writes `Product.thumbnail_url` and `Product.images` (a JSON
array of URLs) and stops there.

The storefront prefers the registry and falls back to those legacy columns
(`backend/app/controllers/catalog_controller.py:279-296`: registered media first, then
`images`, then `thumbnail_url`). So an imported product will render **without** the derived
4:5 / 1:1 / 3:2 / 16:9 ladder, without registered dimensions, and without the provenance
fields (`source_type`/`provider`/`attribution`) that §4 depends on — unless the import slice
also runs a media-derivation pass. `verify_product_media.py` check 4 only inspects "every
product that **HAS** registered rows", so this gap is invisible to that gate.

### 6.3 Pre-existing defects found while auditing (reported, **not** fixed — out of scope)

1. **The official CSV template contains categories that do not exist.**
   `generate_sample_csv()` emits `"shirts"` (`brand_catalog_service.py:713`) and
   `"trousers"` (line 719). The seeded categories are outerwear/tops/bottoms/dresses/
   footwear/accessories (`backend/app/seed_data.py:194-201`). `_validate_row` rejects an
   unknown slug (lines 171-173), so **2 of the template's own 4 sample rows would fail
   validation.**
2. **The error hint names the same non-existent categories.** Line 173 suggests
   "outerwear, **shirts**, **trousers**, **knitwear**, accessories" — three slugs that are
   not in the database. A user following the hint is led into the error.
3. **A bulk import would email customers by default.** `send_notifications` is
   `Query(True)` on the CSV route (`backend/app/controllers/brand_controller.py:474`) and
   the dispatch fires for every newly created product (`brand_catalog_service.py:546`). A
   dataset load **must** pass `send_notifications=false`.
4. **Currency is inconsistent.** All 12 production products are `USD` (75–395); the sample
   template uses `EGP`; `MARKET="EG"`. Authored prices need one decision before import.

---

## 7. Evidence log — quotes as fetched (2026-10-20)

| Source | URL fetched | Excerpt used |
|---|---|---|
| DeepFashion | `https://mmlab.ie.cuhk.edu.hk/projects/DeepFashion.html` | "The DeepFashion is available for **non-commercial** research purposes only." · "You agree **not to** reproduce, duplicate, copy, sell, trade, resell or exploit for any commercial purposes, any portion of the images and any portion of derived data." · "All images of the DeepFashion are obtained from the Internet which are not property of MMLAB…" |
| H&M competition | `https://www.kaggle.com/competitions/h-and-m-personalized-fashion-recommendations/rules` | "**DATA ACCESS AND USE**: Non-Commercial Purposes & Academic Research" · "Privately sharing code or data outside of teams is not permitted." |
| Fashion Product Images (Small) | `https://www.kaggle.com/datasets/paramaggarwal/fashion-product-images-small` | "## License — [MIT](https://www.mit.edu/~amini/LICENSE.md)" · "Thr growing e-commerce industry presents us with a large dataset waiting to be scraped and researched upon." |
| Fashionpedia | `https://fashionpedia.github.io/home/index.html`, `https://github.com/cvdfoundation/fashionpedia`, `.../Fashionpedia_download.html` | No dataset-level licence statement present; annotations define `image.license: int` and `licenses: [ {id, name, url} ]` |
| Fashion-MNIST | `https://raw.githubusercontent.com/zalandoresearch/fashion-mnist/master/LICENSE` | "The MIT License (MIT) Copyright © 2017 Zalando SE… including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or **sell** copies of the Software…" |
| Unsplash | `https://unsplash.com/license` | "Unsplash grants you an irrevocable, nonexclusive, worldwide copyright license to … use images from Unsplash for free, including for commercial purposes, without permission from or attributing the photographer or Unsplash." · "Images cannot be **sold** without significant modification." |
| Pexels | `https://www.pexels.com/license/` | "All photos and videos on Pexels can be downloaded and used for free." · "Use the photos and videos online – whether it's a website, **e-commerce shop**…" · "Don't imply endorsement of your product by people or brands on the imagery." |

---

## 8. Sign-off required before any import

| # | Question | Owner answer |
|---|---|---|
| 1 | Approve **Unsplash** as the image basis (with **Pexels** as secondary)? | ☐ |
| 2 | Choose the stock-imagery posture for imported rows: **(a)** import as `source_type='stock'` and label it in the UI, **(b)** import as visibly-marked demo content, or **(c)** do not import stock imagery? (§4) | ☐ |
| 3 | Approve the currency for authored prices (USD as today, or EGP)? (§6.3.4) | ☐ |
| 4 | Confirm the 6 existing categories are the import target, and whether a finer taxonomy is wanted (§2 D suggests Fashionpedia's ontology is worth borrowing as a vocabulary) | ☐ |
| 5 | Approve whether the import slice may also run a media-derivation pass to populate `product_images` (§6.2), or whether legacy `thumbnail_url` is acceptable for the first load | ☐ |
| 6 | If any source other than Unsplash/Pexels is wanted: approve a **CSP** change (§6.1) | ☐ |

**No import work starts until questions 1 and 2 are answered.**
