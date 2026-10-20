"""Add ix_jobs_provider_ref

Revision ID: ff8202ca9a48
Revises: 53946ed9163f
Create Date: 2026-10-20 09:02:00.000000+00:00

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "ff8202ca9a48"
down_revision = "53946ed9163f"
branch_labels = None
depends_on = None


INDEX_NAME = "ix_jobs_provider_ref"
TABLE_NAME = "jobs"


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
            ["provider_ref"],
            unique=True,
            postgresql_concurrently=True,
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        _drop_index()
