"""Add ix_fleets_current_master_instance_id index

Revision ID: c7b0a8e57294
Revises: 9cb8e4e4d986
Create Date: 2026-03-05 10:45:00.000000+00:00

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "c7b0a8e57294"
down_revision = "9cb8e4e4d986"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.drop_index(
            "ix_fleets_current_master_instance_id",
            table_name="fleets",
            if_exists=True,
            postgresql_concurrently=True,
        )
        op.create_index(
            "ix_fleets_current_master_instance_id",
            "fleets",
            ["current_master_instance_id"],
            unique=False,
            postgresql_concurrently=True,
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.drop_index(
            "ix_fleets_current_master_instance_id",
            table_name="fleets",
            if_exists=True,
            postgresql_concurrently=True,
        )
