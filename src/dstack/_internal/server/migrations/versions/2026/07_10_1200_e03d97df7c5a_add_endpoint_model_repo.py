"""add endpoint model fields

Revision ID: e03d97df7c5a
Revises: 4e1d6c2a9b77
Create Date: 2026-07-10 12:00:00.000000+00:00

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "e03d97df7c5a"
down_revision = "4e1d6c2a9b77"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("endpoints", schema=None) as batch_op:
        batch_op.add_column(sa.Column("model_base", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("model_repo", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("endpoints", schema=None) as batch_op:
        batch_op.drop_column("model_repo")
        batch_op.drop_column("model_base")
