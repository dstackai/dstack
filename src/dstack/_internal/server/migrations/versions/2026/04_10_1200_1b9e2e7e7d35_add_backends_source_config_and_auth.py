"""Add BackendModel.source_config and BackendModel.source_auth

Revision ID: 1b9e2e7e7d35
Revises: ad8c50120507
Create Date: 2026-04-10 12:00:00.000000+00:00

"""

import sqlalchemy as sa
from alembic import op

import dstack._internal.server.models

# revision identifiers, used by Alembic.
revision = "1b9e2e7e7d35"
down_revision = "ad8c50120507"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("backends", schema=None) as batch_op:
        batch_op.add_column(sa.Column("source_config", sa.String(length=20000), nullable=True))
        batch_op.add_column(
            sa.Column(
                "source_auth",
                dstack._internal.server.models.EncryptedString(20000),
                nullable=True,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("backends", schema=None) as batch_op:
        batch_op.drop_column("source_auth")
        batch_op.drop_column("source_config")
