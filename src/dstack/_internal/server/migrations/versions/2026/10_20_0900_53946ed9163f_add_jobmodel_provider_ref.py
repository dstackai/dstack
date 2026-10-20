"""Add JobModel.provider_ref

Revision ID: 53946ed9163f
Revises: d0f36d5050ea
Create Date: 2026-10-20 09:00:00.000000+00:00

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "53946ed9163f"
down_revision = "d0f36d5050ea"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("provider_ref", sa.String(length=12), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.drop_column("provider_ref")
