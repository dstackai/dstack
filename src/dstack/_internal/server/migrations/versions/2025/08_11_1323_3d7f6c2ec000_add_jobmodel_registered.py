"""Add JobModel.registered

Revision ID: 3d7f6c2ec000
Revises: 74a1f55209bd
Create Date: 2025-08-11 13:23:39.530103

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "3d7f6c2ec000"
down_revision = "74a1f55209bd"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("registered", sa.Boolean(), server_default=sa.false(), nullable=False)
        )


def downgrade() -> None:
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.drop_column("registered")
