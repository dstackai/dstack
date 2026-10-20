"""Add ix_jobs_provider_ref and ix_jobs_project_id

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


TABLE_NAME = "jobs"
INDEXES = [
    ("ix_jobs_provider_ref", ["provider_ref"], True),
    ("ix_jobs_project_id", ["project_id"], False),
]


def _drop_index(name: str) -> None:
    op.drop_index(
        name,
        table_name=TABLE_NAME,
        if_exists=True,
        postgresql_concurrently=True,
    )


def upgrade() -> None:
    with op.get_context().autocommit_block():
        for name, columns, unique in INDEXES:
            _drop_index(name)
            op.create_index(
                name,
                TABLE_NAME,
                columns,
                unique=unique,
                postgresql_concurrently=True,
            )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        for name, _, _ in INDEXES:
            _drop_index(name)
