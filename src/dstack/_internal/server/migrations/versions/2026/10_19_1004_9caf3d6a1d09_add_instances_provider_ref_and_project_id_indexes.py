"""Add ix_instances_provider_ref and ix_instances_project_id

Revision ID: 9caf3d6a1d09
Revises: aff11cf0ff72
Create Date: 2026-10-19 10:04:00.000000+00:00

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "9caf3d6a1d09"
down_revision = "aff11cf0ff72"
branch_labels = None
depends_on = None


TABLE_NAME = "instances"
INDEXES = [
    ("ix_instances_provider_ref", ["provider_ref"], True),
    ("ix_instances_project_id", ["project_id"], False),
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
