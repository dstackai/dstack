"""add runmodel desired_replica_counts

Revision ID: 706e0acc3a7d
Revises: 903c91e24634
Create Date: 2025-12-18 10:54:13.508297

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "706e0acc3a7d"
down_revision = "903c91e24634"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("runs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("desired_replica_counts", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("runs", schema=None) as batch_op:
        batch_op.drop_column("desired_replica_counts")
