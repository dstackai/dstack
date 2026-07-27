"""Add EventTargetModel.entity_fleet_id

Revision ID: 0ebd6564f375
Revises: 87d4312605e5
Create Date: 2026-07-23 08:22:23.295309+00:00

"""

import sqlalchemy as sa
import sqlalchemy_utils
from alembic import op

# revision identifiers, used by Alembic.
revision = "0ebd6564f375"
down_revision = "87d4312605e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("event_targets", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "entity_fleet_id",
                sqlalchemy_utils.types.uuid.UUIDType(binary=False),
                nullable=True,
            )
        )
        batch_op.create_index(
            batch_op.f("ix_event_targets_entity_fleet_id"), ["entity_fleet_id"], unique=False
        )
        batch_op.create_foreign_key(
            batch_op.f("fk_event_targets_entity_fleet_id_fleets"),
            "fleets",
            ["entity_fleet_id"],
            ["id"],
            ondelete="CASCADE",
        )


def downgrade() -> None:
    with op.batch_alter_table("event_targets", schema=None) as batch_op:
        batch_op.drop_constraint(
            batch_op.f("fk_event_targets_entity_fleet_id_fleets"), type_="foreignkey"
        )
        batch_op.drop_index(batch_op.f("ix_event_targets_entity_fleet_id"))
        batch_op.drop_column("entity_fleet_id")
