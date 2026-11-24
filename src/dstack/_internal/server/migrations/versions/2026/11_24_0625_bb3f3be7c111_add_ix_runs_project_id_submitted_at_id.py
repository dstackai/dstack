"""Add ix_runs_project_id_submitted_at_id

Revision ID: bb3f3be7c111
Revises: 2d2692d5b3c2
Create Date: 2026-11-24 06:25:56.558461+00:00

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "bb3f3be7c111"
down_revision = "2d2692d5b3c2"
branch_labels = None
depends_on = None

TABLE_NAME = "runs"
INDEX_NAME = "ix_runs_project_id_submitted_at_id"


def _drop_index() -> None:
    op.drop_index(
        INDEX_NAME,
        table_name=TABLE_NAME,
        if_exists=True,
        postgresql_concurrently=True,
    )


def upgrade() -> None:
    with op.get_context().autocommit_block():
        _drop_index()
        op.create_index(
            INDEX_NAME,
            TABLE_NAME,
            ["project_id", sa.text("submitted_at DESC"), "id"],
            unique=False,
            postgresql_concurrently=True,
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        _drop_index()
