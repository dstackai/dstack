"""Add rolling deployment fields

Revision ID: 35e90e1b0d3e
Revises: 35f732ee4cf5
Create Date: 2025-05-29 15:30:27.878569

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "35e90e1b0d3e"
down_revision = "35f732ee4cf5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("runs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("deployment_num", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("desired_replica_count", sa.Integer(), nullable=True))
    with op.batch_alter_table("runs", schema=None) as batch_op:
        batch_op.execute("UPDATE runs SET deployment_num = 0")
        batch_op.execute("UPDATE runs SET desired_replica_count = 1")
        batch_op.alter_column("deployment_num", nullable=False)
        batch_op.alter_column("desired_replica_count", nullable=False)

    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("deployment_num", sa.Integer(), nullable=True))
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.execute("UPDATE jobs SET deployment_num = 0")
        batch_op.alter_column("deployment_num", nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("runs", schema=None) as batch_op:
        batch_op.drop_column("deployment_num")
        batch_op.drop_column("desired_replica_count")

    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.drop_column("deployment_num")
