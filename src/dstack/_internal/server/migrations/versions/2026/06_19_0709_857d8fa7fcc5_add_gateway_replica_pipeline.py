"""Add gateway replica pipeline

Revision ID: 857d8fa7fcc5
Revises: b7609b94ea4d
Create Date: 2026-06-19 07:09:26.989255+00:00

"""

import sqlalchemy as sa
import sqlalchemy_utils
from alembic import op

import dstack._internal.server.models

# revision identifiers, used by Alembic.
revision = "857d8fa7fcc5"
down_revision = "b7609b94ea4d"
branch_labels = None
depends_on = None

# partial definition for queries
gateway_computes = sa.table(
    "gateway_computes",
    sa.column("id"),
    sa.column("gateway_id"),
    sa.column("last_processed_at", sa.DateTime()),
    sa.column("created_at", sa.DateTime()),
    sa.column("status", sa.String(100)),
    sa.column("deleted", sa.Boolean()),
    sa.column("active", sa.Boolean()),
    sa.column("region", sa.String(100)),
    sa.column("ip_address", sa.String(100)),
    sa.column("instance_id", sa.String(100)),
)
gateways = sa.table(
    "gateways",
    sa.column("id"),
    sa.column("gateway_compute_id"),
    sa.column("status", sa.String(100)),
)


def upgrade() -> None:
    with op.batch_alter_table("gateway_computes", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "last_processed_at", dstack._internal.server.models.NaiveDateTime(), nullable=True
            )
        )
        batch_op.add_column(sa.Column("status", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("status_message", sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "lock_expires_at", dstack._internal.server.models.NaiveDateTime(), nullable=True
            )
        )
        batch_op.add_column(
            sa.Column(
                "lock_token", sqlalchemy_utils.types.uuid.UUIDType(binary=False), nullable=True
            )
        )
        batch_op.add_column(sa.Column("lock_owner", sa.String(length=100), nullable=True))
        batch_op.alter_column("instance_id", existing_type=sa.VARCHAR(length=100), nullable=True)
        batch_op.alter_column("ip_address", existing_type=sa.VARCHAR(length=100), nullable=True)
        batch_op.alter_column("region", existing_type=sa.VARCHAR(length=100), nullable=True)

    op.execute(sa.update(gateway_computes).values(last_processed_at=gateway_computes.c.created_at))

    gateway_is_provisioning = sa.exists(
        sa.select(sa.literal(1))
        .select_from(gateways)
        .where(
            sa.or_(
                gateways.c.id == gateway_computes.c.gateway_id,
                gateways.c.gateway_compute_id == gateway_computes.c.id,
            ),
            gateways.c.status == "PROVISIONING",
        )
    )
    op.execute(
        sa.update(gateway_computes).values(
            status=sa.case(
                (gateway_computes.c.deleted == True, "TERMINATED"),
                (gateway_computes.c.active == False, "TERMINATING"),
                (gateway_is_provisioning, "PROVISIONING"),
                else_="RUNNING",
            )
        )
    )

    with op.batch_alter_table("gateway_computes", schema=None) as batch_op:
        batch_op.alter_column(
            "last_processed_at",
            existing_type=dstack._internal.server.models.NaiveDateTime(),
            nullable=False,
        )
        batch_op.alter_column("status", existing_type=sa.String(100), nullable=False)


def downgrade() -> None:
    op.execute(
        sa.delete(gateway_computes).where(
            sa.or_(
                gateway_computes.c.status == "SUBMITTED",
                gateway_computes.c.region.is_(None),
                gateway_computes.c.ip_address.is_(None),
                gateway_computes.c.instance_id.is_(None),
            )
        )
    )
    with op.batch_alter_table("gateway_computes", schema=None) as batch_op:
        batch_op.alter_column("region", existing_type=sa.VARCHAR(length=100), nullable=False)
        batch_op.alter_column("ip_address", existing_type=sa.VARCHAR(length=100), nullable=False)
        batch_op.alter_column("instance_id", existing_type=sa.VARCHAR(length=100), nullable=False)
        batch_op.drop_column("lock_owner")
        batch_op.drop_column("lock_token")
        batch_op.drop_column("lock_expires_at")
        batch_op.drop_column("status_message")
        batch_op.drop_column("status")
        batch_op.drop_column("last_processed_at")
