"""Index exclusive volumes by instance

Revision ID: 26bb6dd37157
Revises: fe7552e4c072
Create Date: 2026-11-25 17:07:38.094670+00:00

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "26bb6dd37157"
down_revision = "fe7552e4c072"
branch_labels = None
depends_on = None


TABLE = "volumes_attachments"
INDEX = "ix_volumes_attachments_exclusive_instance_id"


def upgrade() -> None:
    condition = sa.text("exclusive_volume_id IS NOT NULL")
    with op.get_context().autocommit_block():
        op.drop_index(INDEX, table_name=TABLE, if_exists=True, postgresql_concurrently=True)
        op.create_index(
            INDEX,
            TABLE,
            ["instance_id"],
            postgresql_where=condition,
            sqlite_where=condition,
            postgresql_concurrently=True,
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.drop_index(INDEX, table_name=TABLE, if_exists=True, postgresql_concurrently=True)
