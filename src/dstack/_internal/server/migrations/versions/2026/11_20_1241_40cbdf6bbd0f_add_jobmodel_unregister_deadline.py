"""Add JobModel.unregister_deadline

Revision ID: 40cbdf6bbd0f
Revises: 2d2692d5b3c2
Create Date: 2026-11-20 12:41:35.026269+00:00

"""

import sqlalchemy as sa
from alembic import op

import dstack._internal.server.models

# revision identifiers, used by Alembic.
revision = "40cbdf6bbd0f"
down_revision = "2d2692d5b3c2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "unregister_deadline",
                dstack._internal.server.models.NaiveDateTime(),
                nullable=True,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.drop_column("unregister_deadline")
