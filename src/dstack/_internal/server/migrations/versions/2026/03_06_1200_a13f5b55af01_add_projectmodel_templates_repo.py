"""Add ProjectModel.templates_repo

Revision ID: a13f5b55af01
Revises: 5e8c7a9202bc
Create Date: 2026-03-06 12:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "a13f5b55af01"
down_revision = "c7b0a8e57294"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("projects", schema=None) as batch_op:
        batch_op.add_column(sa.Column("templates_repo", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("projects", schema=None) as batch_op:
        batch_op.drop_column("templates_repo")
