"""Store the visual-search embedding alongside the product.

Visual search matched keywords from a Gemini description: two navy blazers
with different cuts scored identically, and a garment whose description
omitted "navy" scored zero however navy it was.

Embedding-based retrieval needs the catalogue vectors to live somewhere.
They are held as a JSON array of floats rather than a vector column so the
SQLite test database and Neon Postgres share one schema — the catalogue is
hundreds of rows, so a linear cosine scan costs far less than operating
pgvector.

`style_embedding_model` travels WITH the vector. Embeddings from two models
are not comparable, and mixing them degrades ranking silently rather than
failing, so both the backfill and the search refuse a row whose model id is
not the one in use.

Nullable on purpose: a product without an embedding is simply absent from
visual results until it is backfilled, which is honest. The column has no
server default, so nothing is invented for existing rows.

Revision: 0026_product_style_embedding
Revises:  0025_order_item_discount_allocation
"""
import sqlalchemy as sa
from alembic import op

revision: str = "0026_product_style_embedding"
down_revision: str = "0025_order_item_discount_allocation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("products", sa.Column("style_embedding", sa.Text(), nullable=True))
    op.add_column(
        "products", sa.Column("style_embedding_model", sa.String(120), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("products", "style_embedding_model")
    op.drop_column("products", "style_embedding")
