"""Add InstanceModel blocks fields

Revision ID: 51d45659d574
Revises: da574e93fee0
Create Date: 2025-02-04 11:10:41.626273

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "51d45659d574"
down_revision = "da574e93fee0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("instances", schema=None) as batch_op:
        batch_op.add_column(sa.Column("total_blocks", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("busy_blocks", sa.Integer(), nullable=True))

    op.execute("""
        UPDATE instances
        SET total_blocks = 1
    """)
    op.execute("""
        UPDATE instances
        SET busy_blocks = CASE
            WHEN job_id IS NOT NULL THEN 1
            ELSE 0
        END
    """)

    with op.batch_alter_table("instances", schema=None) as batch_op:
        batch_op.alter_column("busy_blocks", existing_type=sa.INTEGER(), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("instances", schema=None) as batch_op:
        batch_op.drop_column("busy_blocks")
        batch_op.drop_column("total_blocks")
