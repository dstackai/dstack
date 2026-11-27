"""Add exclusive volume attachment ID

Revision ID: 48487e02b247
Revises: 17e6c7ef91dd
Create Date: 2026-11-25 16:06:28.559512+00:00

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "48487e02b247"
down_revision = "17e6c7ef91dd"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "volumes_attachments", sa.Column("exclusive_volume_id", sa.String(255), nullable=True)
    )


def downgrade() -> None:
    with op.batch_alter_table("volumes_attachments") as batch_op:
        batch_op.drop_column("exclusive_volume_id")
