"""Add JobModel.running_at

Revision ID: 652af7a3c9c9
Revises: 620892d149b5
Create Date: 2026-09-08 10:02:00.000000

"""

import sqlalchemy as sa
from alembic import op

import dstack._internal.server.models

# revision identifiers, used by Alembic.
revision = "652af7a3c9c9"
down_revision = "620892d149b5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("running_at", dstack._internal.server.models.NaiveDateTime(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.drop_column("running_at")
