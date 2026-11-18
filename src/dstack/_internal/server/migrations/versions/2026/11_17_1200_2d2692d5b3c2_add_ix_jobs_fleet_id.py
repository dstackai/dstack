"""Add ix_jobs_fleet_id

Revision ID: 2d2692d5b3c2
Revises: 6b5610ff36c1
Create Date: 2026-11-17 12:00:00.000000+00:00

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "2d2692d5b3c2"
down_revision = "6b5610ff36c1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.drop_index(
            "ix_jobs_fleet_id",
            table_name="jobs",
            if_exists=True,
            postgresql_concurrently=True,
        )
        op.create_index(
            "ix_jobs_fleet_id",
            "jobs",
            ["fleet_id"],
            unique=False,
            postgresql_concurrently=True,
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.drop_index(
            "ix_jobs_fleet_id",
            table_name="jobs",
            if_exists=True,
            postgresql_concurrently=True,
        )
