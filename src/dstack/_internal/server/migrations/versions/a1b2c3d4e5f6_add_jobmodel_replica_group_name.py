"""Add JobModel.replica_group_name

Revision ID: a1b2c3d4e5f6
Revises: ff1d94f65b08
Create Date: 2025-10-17 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "a1b2c3d4e5f6"
down_revision = "ff1d94f65b08"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("replica_group_name", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.drop_column("replica_group_name")

