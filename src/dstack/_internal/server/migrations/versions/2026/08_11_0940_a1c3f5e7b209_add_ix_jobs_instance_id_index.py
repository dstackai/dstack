"""Add ix_jobs_instance_id index

Revision ID: a1c3f5e7b209
Revises: ecc9e8a0bfac
Create Date: 2026-08-11 09:40:00.000000+00:00

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "a1c3f5e7b209"
down_revision = "ecc9e8a0bfac"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.drop_index(
            "ix_jobs_instance_id",
            table_name="jobs",
            if_exists=True,
            postgresql_concurrently=True,
        )
        op.create_index(
            "ix_jobs_instance_id",
            "jobs",
            ["instance_id"],
            unique=False,
            postgresql_concurrently=True,
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.drop_index(
            "ix_jobs_instance_id",
            table_name="jobs",
            if_exists=True,
            postgresql_concurrently=True,
        )
