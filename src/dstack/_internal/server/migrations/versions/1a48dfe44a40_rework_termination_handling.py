"""Rework termination handling

Revision ID: 1a48dfe44a40
Revises: 9eea6af28e10
Create Date: 2024-02-21 10:11:32.350099

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "1a48dfe44a40"
down_revision = "9eea6af28e10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("instances", schema=None) as batch_op:
        batch_op.drop_column("fail_reason")
        batch_op.drop_column("fail_count")

    with op.batch_alter_table("instances", schema=None) as batch_op:
        batch_op.add_column(sa.Column("termination_deadline", sa.DateTime(), nullable=True))
        batch_op.add_column(
            sa.Column("termination_reason", sa.VARCHAR(length=4000), nullable=True)
        )
        batch_op.add_column(sa.Column("health_status", sa.VARCHAR(length=4000), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("instances", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("fail_count", sa.Integer(), server_default=sa.text("0"), nullable=False)
        )
        batch_op.add_column(sa.Column("fail_reason", sa.String(length=4000), nullable=True))

    with op.batch_alter_table("instances", schema=None) as batch_op:
        batch_op.drop_column("termination_deadline")
        batch_op.drop_column("termination_reason")
        batch_op.drop_column("health_status")
