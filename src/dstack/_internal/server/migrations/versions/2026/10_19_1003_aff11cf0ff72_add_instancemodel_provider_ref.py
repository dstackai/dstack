"""Add InstanceModel.provider_ref

Revision ID: aff11cf0ff72
Revises: 40f19bea9d2a
Create Date: 2026-10-19 10:03:45.638994+00:00

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "aff11cf0ff72"
down_revision = "40f19bea9d2a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("instances", schema=None) as batch_op:
        batch_op.add_column(sa.Column("provider_ref", sa.String(length=12), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("instances", schema=None) as batch_op:
        batch_op.drop_column("provider_ref")
