"""Replace ix_jobs_run_id with ix_jobs_run_id_replica_num_job_num_submission_num

Revision ID: 6b5610ff36c1
Revises: ca5fb194134e
Create Date: 2026-11-06 10:12:47.823527+00:00

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "6b5610ff36c1"
down_revision = "ca5fb194134e"
branch_labels = None
depends_on = None

TABLE_NAME = "jobs"
OLD_INDEX_NAME = "ix_jobs_run_id"
NEW_INDEX_NAME = "ix_jobs_run_id_replica_num_job_num_submission_num"
NEW_INDEX_COLUMNS = ["run_id", "replica_num", "job_num", "submission_num"]


def _drop_index(name: str) -> None:
    op.drop_index(
        name,
        table_name=TABLE_NAME,
        if_exists=True,
        postgresql_concurrently=True,
    )


def upgrade() -> None:
    with op.get_context().autocommit_block():
        _drop_index(NEW_INDEX_NAME)
        op.create_index(
            NEW_INDEX_NAME,
            TABLE_NAME,
            NEW_INDEX_COLUMNS,
            unique=False,
            postgresql_concurrently=True,
        )
        # The new index starts with `run_id`, so it serves every lookup the old one did.
        _drop_index(OLD_INDEX_NAME)


def downgrade() -> None:
    with op.get_context().autocommit_block():
        _drop_index(OLD_INDEX_NAME)
        op.create_index(
            OLD_INDEX_NAME,
            TABLE_NAME,
            ["run_id"],
            unique=False,
            postgresql_concurrently=True,
        )
        _drop_index(NEW_INDEX_NAME)
