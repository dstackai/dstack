"""Add ix_jobs_project_id

Revision ID: ca5fb194134e
Revises: 2e7479a16e36
Create Date: 2026-10-22 09:01:45.369057+00:00

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "ca5fb194134e"
down_revision = "2e7479a16e36"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.drop_index(
            "ix_jobs_project_id",
            table_name="jobs",
            if_exists=True,
            postgresql_concurrently=True,
        )
        op.create_index(
            "ix_jobs_project_id",
            "jobs",
            ["project_id"],
            unique=False,
            postgresql_concurrently=True,
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.drop_index(
            "ix_jobs_project_id",
            table_name="jobs",
            if_exists=True,
            postgresql_concurrently=True,
        )
