"""Backfill EventTargetModel.entity_fleet_id

Revision ID: 4d3cbb932bb2
Revises: 0ebd6564f375
Create Date: 2026-07-23 08:25:22.615590+00:00

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "4d3cbb932bb2"
down_revision = "0ebd6564f375"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Events recorded before entity_fleet_id was introduced have it unset.
    # The within_fleets events filter relies on entity_fleet_id, so backfill it.
    # Instance targets are backfilled via the instances table, so this migration
    # must run before the instance models the events reference are deleted
    # (e.g. placeholder instances deleted on job termination).
    # Old replicas can still record events without entity_fleet_id while
    # this migration is being deployed. Such events won't be backfilled and
    # won't be returned by the within_fleets events filter.
    op.execute(
        """
        UPDATE event_targets SET entity_fleet_id = entity_id
        WHERE entity_type = 'FLEET' AND entity_fleet_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE event_targets SET entity_fleet_id = instances.fleet_id
        FROM instances
        WHERE instances.id = event_targets.entity_id
            AND instances.fleet_id IS NOT NULL
            AND event_targets.entity_type = 'INSTANCE'
            AND event_targets.entity_fleet_id IS NULL
        """
    )


def downgrade() -> None:
    pass
