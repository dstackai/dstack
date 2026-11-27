"""Add FleetModel.skip_min_processing_interval

Revision ID: e4a1c9f2b7d3
Revises: 17e6c7ef91dd
Create Date: 2026-11-27 09:00:00.000000+00:00

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "e4a1c9f2b7d3"
down_revision = "17e6c7ef91dd"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("fleets", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "skip_min_processing_interval",
                sa.Boolean(),
                server_default=sa.false(),
                nullable=False,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("fleets", schema=None) as batch_op:
        batch_op.drop_column("skip_min_processing_interval")
