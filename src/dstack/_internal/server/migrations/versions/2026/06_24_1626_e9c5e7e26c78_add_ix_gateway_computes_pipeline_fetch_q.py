"""Add ix_gateway_computes_pipeline_fetch_q

Revision ID: e9c5e7e26c78
Revises: 857d8fa7fcc5
Create Date: 2026-06-24 16:26:22.834262+00:00

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "e9c5e7e26c78"
down_revision = "857d8fa7fcc5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.drop_index(
            "ix_gateway_computes_pipeline_fetch_q",
            table_name="gateway_computes",
            if_exists=True,
            postgresql_concurrently=True,
        )
        op.create_index(
            "ix_gateway_computes_pipeline_fetch_q",
            "gateway_computes",
            [sa.literal_column("last_processed_at ASC")],
            unique=False,
            sqlite_where=sa.text("deleted = 0"),
            postgresql_where=sa.text("deleted IS FALSE"),
            postgresql_concurrently=True,
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.drop_index(
            "ix_gateway_computes_pipeline_fetch_q",
            table_name="gateway_computes",
            if_exists=True,
            postgresql_concurrently=True,
        )
