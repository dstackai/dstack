"""Index exclusive volume attachments

Revision ID: fe7552e4c072
Revises: 48487e02b247
Create Date: 2026-11-25 16:07:18.986578+00:00

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "fe7552e4c072"
down_revision = "48487e02b247"
branch_labels = None
depends_on = None


TABLE = "volumes_attachments"
INDEX = "ix_volumes_attachments_exclusive_volume_id"


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.drop_index(INDEX, table_name=TABLE, if_exists=True, postgresql_concurrently=True)
        op.create_index(
            INDEX, TABLE, ["exclusive_volume_id"], unique=True, postgresql_concurrently=True
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.drop_index(INDEX, table_name=TABLE, if_exists=True, postgresql_concurrently=True)
