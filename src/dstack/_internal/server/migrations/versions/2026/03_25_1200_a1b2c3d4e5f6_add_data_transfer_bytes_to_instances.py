"""Add data_transfer_bytes to instances

Revision ID: a1b2c3d4e5f6
Revises: c1c2ecaee45c
Create Date: 2026-03-25 12:00:00.000000+00:00

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "a1b2c3d4e5f6"
down_revision = "c1c2ecaee45c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "instances",
        sa.Column("data_transfer_bytes", sa.BigInteger(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("instances", "data_transfer_bytes")
