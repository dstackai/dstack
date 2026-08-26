"""Backfill EventTargetModel.entity_gateway_id

Revision ID: 620892d149b5
Revises: 193c9622ac7e
Create Date: 2026-08-23 11:57:45.694508+00:00

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "620892d149b5"
down_revision = "193c9622ac7e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE event_targets SET entity_gateway_id = entity_id
        WHERE entity_type = 'GATEWAY' AND entity_gateway_id IS NULL
        """
    )


def downgrade() -> None:
    pass
