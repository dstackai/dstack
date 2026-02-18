"""Add FileArchiveModel

Revision ID: 5f1707c525d2
Revises: 35e90e1b0d3e
Create Date: 2025-06-12 12:28:26.678380

"""

import sqlalchemy as sa
import sqlalchemy_utils
from alembic import op

# revision identifiers, used by Alembic.
revision = "5f1707c525d2"
down_revision = "35e90e1b0d3e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "file_archives",
        sa.Column("id", sqlalchemy_utils.types.uuid.UUIDType(binary=False), nullable=False),
        sa.Column("user_id", sqlalchemy_utils.types.uuid.UUIDType(binary=False), nullable=False),
        sa.Column("blob_hash", sa.Text(), nullable=False),
        sa.Column("blob", sa.LargeBinary(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_file_archives_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_file_archives")),
        sa.UniqueConstraint("user_id", "blob_hash", name="uq_file_archives_user_id_blob_hash"),
    )


def downgrade() -> None:
    op.drop_table("file_archives")
