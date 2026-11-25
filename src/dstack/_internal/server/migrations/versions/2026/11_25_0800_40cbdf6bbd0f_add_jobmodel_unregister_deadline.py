"""Add JobModel.unregister_deadline

Revision ID: 40cbdf6bbd0f
Revises: bb3f3be7c111
Create Date: 2026-11-25 08:00:00.000000+00:00

"""

import sqlalchemy as sa
from alembic import op

import dstack._internal.server.models

# revision identifiers, used by Alembic.
revision = "40cbdf6bbd0f"
down_revision = "bb3f3be7c111"
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
