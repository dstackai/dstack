"""Add JobModel.job_runtime_data

Revision ID: 803c7e9ed85d
Revises: c48df7985d57
Create Date: 2025-01-10 14:17:24.029983

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "803c7e9ed85d"
down_revision = "c48df7985d57"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("job_runtime_data", sa.Text(), nullable=True))

    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.drop_column("job_runtime_data")

    # ### end Alembic commands ###
