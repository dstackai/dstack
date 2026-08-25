"""Add EventTargetModel.entity_gateway_id

Revision ID: 193c9622ac7e
Revises: dbbe9f32ec66
Create Date: 2026-08-23 11:57:43.043467+00:00

"""

import sqlalchemy as sa
import sqlalchemy_utils
from alembic import op

# revision identifiers, used by Alembic.
revision = "193c9622ac7e"
down_revision = "dbbe9f32ec66"
branch_labels = None
depends_on = None

INDEX_NAME = "ix_event_targets_entity_gateway_id"
TABLE_NAME = "event_targets"


def _drop_index() -> None:
    op.drop_index(
        INDEX_NAME,
        table_name=TABLE_NAME,
        if_exists=True,
        postgresql_concurrently=True,
    )


def upgrade() -> None:
    with op.batch_alter_table(TABLE_NAME, schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "entity_gateway_id",
                sqlalchemy_utils.types.uuid.UUIDType(binary=False),
                nullable=True,
            )
        )
    with op.get_context().autocommit_block():
        _drop_index()
        op.create_index(
            INDEX_NAME,
            TABLE_NAME,
            ["entity_gateway_id"],
            unique=False,
            postgresql_concurrently=True,
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        _drop_index()
    with op.batch_alter_table(TABLE_NAME, schema=None) as batch_op:
        batch_op.drop_column("entity_gateway_id")
