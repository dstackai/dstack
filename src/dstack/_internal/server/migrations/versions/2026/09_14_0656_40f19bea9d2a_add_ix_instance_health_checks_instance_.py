"""Add ix_instance_health_checks_instance_id_collected_at

Revision ID: 40f19bea9d2a
Revises: 652af7a3c9c9
Create Date: 2026-09-14 06:56:41.088290+00:00

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "40f19bea9d2a"
down_revision = "652af7a3c9c9"
branch_labels = None
depends_on = None

INDEX_NAME = "ix_instance_health_checks_instance_id_collected_at"
TABLE_NAME = "instance_health_checks"


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
            ["instance_id", "collected_at"],
            unique=False,
            postgresql_concurrently=True,
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        _drop_index()
