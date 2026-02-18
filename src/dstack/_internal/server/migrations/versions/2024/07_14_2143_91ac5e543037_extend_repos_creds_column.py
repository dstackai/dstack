"""Extend repos.creds column

Revision ID: 91ac5e543037
Revises: 5ad8debc8fe6
Create Date: 2024-07-14 21:43:03.242059

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "91ac5e543037"
down_revision = "5ad8debc8fe6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("repos", schema=None) as batch_op:
        batch_op.alter_column(
            "creds",
            existing_type=sa.VARCHAR(length=2000),
            type_=sa.String(length=5000),
            existing_nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("repos", schema=None) as batch_op:
        batch_op.alter_column(
            "creds",
            existing_type=sa.String(length=5000),
            type_=sa.VARCHAR(length=2000),
            existing_nullable=True,
        )
