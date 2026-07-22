"""Backfill EventTargetModel.entity_run_id

Revision ID: 87d4312605e5
Revises: ad348ea93493
Create Date: 2026-07-22 13:31:47.070886+00:00

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "87d4312605e5"
down_revision = "ad348ea93493"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Events recorded before entity_run_id was introduced have it unset.
    # The within_runs events filter relies on entity_run_id, so backfill it.
    # Job targets are backfilled via the jobs table, so this migration must run
    # before the job models the events reference are deleted
    # (e.g. superseded no capacity submissions deleted on resubmission).
    # Old replicas can still record events without entity_run_id while
    # this migration is being deployed. Such events won't be backfilled and
    # won't be returned by the within_runs events filter.
    op.execute(
        """
        UPDATE event_targets SET entity_run_id = entity_id
        WHERE entity_type = 'run' AND entity_run_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE event_targets SET entity_run_id = jobs.run_id
        FROM jobs
        WHERE jobs.id = event_targets.entity_id
            AND event_targets.entity_type = 'job'
            AND event_targets.entity_run_id IS NULL
        """
    )


def downgrade() -> None:
    pass
