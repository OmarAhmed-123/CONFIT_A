"""Deterministic, candidate-rich catalogue fixture for composer tests.

Two ways to use it:
* `fixture_catalogue()` inserts the rows in a transaction and ROLLS THEM BACK. Use it
  when the test calls the composer directly with the product list.
* `committed_catalogue()` COMMITS the rows (with in-stock SKUs, which the stylist
  service requires) and DELETES them on exit. Use it when the test runs the full
  `StylistService`, which reads the catalogue from the database.

Either way the composer under test is the real `StylingEngine`. Nothing here is
shown to a customer and the shared seeded catalogue is left unchanged.
"""
import json
from contextlib import contextmanager

from backend.app.core.database import SessionLocal
from backend.app.models.catalog import Product, ProductSKU
from backend.app.services.styling_engine import StylingEngine

# category ids from the seed: 1 outerwear, 2 tops, 3 bottoms, 5 footwear, 6 accessories
# brand ids from the seed: 1 Massimo Dutti, 2 COS, 3 Reiss, 4 Arket

#: (slug, title, category_id, brand_id, colour, style_tags, occasion_tags)
CANDIDATES = [
    # outerwear (blazers): navy, olive, burgundy, charcoal
    ("fx-blazer-navy", "Tailored Wool Blazer", 1, 1, "Navy Blue", ["smart_casual", "tailored"], ["work", "business", "dinner"]),
    ("fx-blazer-olive", "Tailored Wool Blazer", 1, 4, "Olive Green", ["smart_casual", "tailored"], ["work", "business"]),
    ("fx-blazer-burgundy", "Tailored Wool Blazer", 1, 3, "Burgundy", ["smart_casual", "tailored"], ["work", "business"]),
    ("fx-blazer-charcoal", "Tailored Wool Blazer", 1, 2, "Charcoal Grey", ["smart_casual", "tailored"], ["work", "business"]),
    # tops (dress shirts): white, cream, olive, burgundy
    ("fx-shirt-white", "Classic Oxford Dress Shirt", 2, 2, "Optic White", ["smart_casual", "essential"], ["work", "business"]),
    ("fx-shirt-cream", "Classic Oxford Dress Shirt", 2, 4, "Ivory Cream", ["smart_casual", "essential"], ["work", "business"]),
    ("fx-shirt-olive", "Classic Oxford Dress Shirt", 2, 3, "Olive Green", ["smart_casual", "essential"], ["work", "business"]),
    ("fx-shirt-burgundy", "Classic Oxford Dress Shirt", 2, 1, "Burgundy", ["smart_casual", "essential"], ["work", "business"]),
    # bottoms (wool trousers): navy x2, charcoal, cream, olive
    ("fx-trousers-navy", "Pleated Wool Trousers", 3, 1, "Navy Blue", ["tailored", "smart_casual"], ["work", "business", "dinner"]),
    ("fx-trousers-charcoal", "Pleated Wool Trousers", 3, 2, "Charcoal Grey", ["tailored", "smart_casual"], ["work", "business"]),
    ("fx-trousers-cream", "Pleated Wool Trousers", 3, 4, "Ivory Cream", ["tailored", "smart_casual"], ["work", "business"]),
    ("fx-trousers-olive", "Pleated Wool Trousers", 3, 3, "Olive Green", ["tailored", "smart_casual"], ["work", "business"]),
    ("fx-trousers-navy-2", "Pleated Wool Trousers", 3, 4, "Navy Blue", ["tailored", "smart_casual"], ["work", "business"]),
    # footwear: black oxfords, olive suede derbies, navy loafers
    ("fx-shoes-oxford-black", "Leather Oxford Shoes", 5, 1, "Obsidian Black", ["formal", "tailored"], ["work", "business", "wedding"]),
    ("fx-shoes-suede-olive", "Suede Derby Shoes", 5, 3, "Olive Green", ["smart_casual"], ["work", "business"]),
    ("fx-shoes-loafer-navy", "Leather Penny Loafers", 5, 2, "Navy Blue", ["smart_casual"], ["work", "business"]),
    # accessories: silk ties in navy, burgundy and emerald
    ("fx-tie-navy", "Silk Necktie", 6, 1, "Navy Blue", ["formal", "tailored"], ["work", "business"]),
    ("fx-tie-burgundy", "Silk Necktie", 6, 3, "Burgundy", ["formal", "tailored"], ["work", "business"]),
    ("fx-tie-emerald", "Silk Necktie", 6, 4, "Emerald Green", ["formal", "tailored"], ["work", "business"]),
]


def _make(db, slug, title, category_id, brand_id, colour, style_tags, occasion_tags, *, price=180):
    p = Product(
        brand_id=brand_id, category_id=category_id, title=title, title_ar=title,
        slug=slug, description=f"{title} in {colour}.", description_ar=title,
        base_price=price, currency="USD", style_tags=json.dumps(style_tags),
        occasion_tags=json.dumps(occasion_tags), color_family=colour,
        dominant_hex="#1B1F3B", thumbnail_url="https://example.invalid/fixture.jpg",
        images="[]", size_chart_json="{}", gender="unisex", is_active=True,
    )
    db.add(p)
    return p


def _sku(db, product):
    db.add(ProductSKU(
        product=product, sku_code=f"{product.slug}-M".upper(), size="M",
        color=product.color_family, stock_level=10, is_in_stock=True,
    ))


def _rows(db, extra=(), omit=()):
    rows = []
    for row in CANDIDATES:
        if row[0] in omit:
            continue
        rows.append(_make(db, *row))
    for row in extra:
        rows.append(_make(db, *row))
    return rows


@contextmanager
def fixture_catalogue(extra=(), omit=()):
    """Yield (db, products). Rolled back on exit: nothing persists."""
    db = SessionLocal()
    try:
        rows = _rows(db, extra, omit)
        db.flush()
        yield db, rows
    finally:
        db.rollback()
        db.close()


@contextmanager
def committed_catalogue(extra=(), omit=()):
    """Yield (db, products) after COMMITTING them with in-stock SKUs; delete on exit."""
    db = SessionLocal()
    rows = []
    try:
        rows = _rows(db, extra, omit)
        db.flush()
        for r in rows:
            _sku(db, r)
        db.commit()
        yield db, rows
    finally:
        db.rollback()
        for r in rows:
            db.query(ProductSKU).filter(ProductSKU.product_id == r.id).delete()
            db.query(Product).filter(Product.id == r.id).delete()
        db.commit()
        db.close()


def compose(db, products, prompt, palette=None):
    intent = StylingEngine.parse_intent(prompt)
    intent["image_palette"] = list(palette or [])
    outfits, meta = StylingEngine.compose_outfits_with_meta(products, intent, None, 3)
    return intent, outfits, meta


def ids_of(look):
    return {i.get("product_id") for i in look.get("items", [])}
