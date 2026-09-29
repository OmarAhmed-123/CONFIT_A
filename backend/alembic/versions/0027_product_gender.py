"""Give products a gender, and backfill it from the garment name.

THE DEFECT
----------
Measured on production: "mens casual weekend look" returned an outfit
containing "Strappy Metallic Leather Heeled Sandals".

`products` had no gender column. The only "gender" in the codebase was
`gender_mode`, a try-on RENDER parameter describing the uploaded photo,
never an attribute of the garment. The styling engine was structurally
incapable of honouring a gendered request, so it ignored it.

BACKFILL
--------
Derived from the garment noun via the same classifier the application uses
(`services/styling/garment_gender.infer_gender`), so the migration and the
runtime cannot disagree about what a "tuxedo" is.

Defaults to `unisex`, which the filter treats permissively. That matters:
excluding neutral garments from a gendered request would leave the composer
with too few slots to build a complete outfit, which is a worse failure
than showing a neutral shirt.

Revision: 0027_product_gender
Revises:  0026_product_style_embedding
"""
import sqlalchemy as sa
from alembic import op

revision: str = "0027_product_gender"
down_revision: str = "0026_product_style_embedding"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column("gender", sa.String(16), nullable=False, server_default="unisex"),
    )

    # Backfill with the application's own classifier so there is exactly one
    # definition of what each garment noun means.
    from backend.app.services.styling.garment_gender import infer_gender

    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT p.id, p.title, c.slug FROM products p "
            "LEFT JOIN categories c ON c.id = p.category_id"
        )
    ).fetchall()

    counts = {"mens": 0, "womens": 0, "unisex": 0}
    for product_id, title, slug in rows:
        gender = infer_gender(title, slug)
        counts[gender] = counts.get(gender, 0) + 1
        if gender != "unisex":
            bind.execute(
                sa.text("UPDATE products SET gender = :g WHERE id = :i"),
                {"g": gender, "i": product_id},
            )
    print(f"[0027] gender backfill: {counts}")


def downgrade() -> None:
    op.drop_column("products", "gender")
