"""Add remote connection details

Revision ID: 1e3fb39ef74b
Revises: 866ec1d67184
Create Date: 2024-04-08 08:02:33.357013

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "1e3fb39ef74b"
down_revision = "866ec1d67184"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("instances", schema=None) as batch_op:
        batch_op.add_column(sa.Column("remote_connection_info", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("instances", schema=None) as batch_op:
        batch_op.drop_column("remote_connection_info")
