"""Add JobModel.exit_status

Revision ID: 6c1a9d6530ee
Revises: 7ba3b59d7ca6
Create Date: 2025-05-09 10:25:19.715852

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "6c1a9d6530ee"
down_revision = "7ba3b59d7ca6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("exit_status", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.drop_column("exit_status")
