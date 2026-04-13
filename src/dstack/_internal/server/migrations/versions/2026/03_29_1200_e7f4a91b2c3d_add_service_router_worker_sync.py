"""Add service_router_worker_sync for router-worker reconcile pipeline.

Revision ID: e7f4a91b2c3d
Revises: 1b9e2e7e7d35
Create Date: 2026-03-29 12:00:00.000000+00:00

"""

import sqlalchemy as sa
import sqlalchemy_utils
from alembic import op

import dstack._internal.server.models

revision = "e7f4a91b2c3d"
down_revision = "1b9e2e7e7d35"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "service_router_worker_sync",
        sa.Column("id", sqlalchemy_utils.types.uuid.UUIDType(binary=False), nullable=False),
        sa.Column("run_id", sqlalchemy_utils.types.uuid.UUIDType(binary=False), nullable=False),
        sa.Column("deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", dstack._internal.server.models.NaiveDateTime(), nullable=False),
        sa.Column(
            "last_processed_at", dstack._internal.server.models.NaiveDateTime(), nullable=False
        ),
        sa.Column(
            "lock_expires_at", dstack._internal.server.models.NaiveDateTime(), nullable=True
        ),
        sa.Column("lock_token", sqlalchemy_utils.types.uuid.UUIDType(binary=False), nullable=True),
        sa.Column("lock_owner", sa.String(length=100), nullable=True),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["runs.id"],
            name=op.f("fk_service_router_worker_sync_run_id_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_service_router_worker_sync")),
    )
    op.create_index(
        op.f("ix_service_router_worker_sync_pipeline_fetch_q"),
        "service_router_worker_sync",
        [sa.literal_column("last_processed_at ASC")],
        unique=False,
    )
    op.create_index(
        op.f("ix_service_router_worker_sync_run_id"),
        "service_router_worker_sync",
        ["run_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_service_router_worker_sync_run_id"), table_name="service_router_worker_sync"
    )
    op.drop_index(
        op.f("ix_service_router_worker_sync_pipeline_fetch_q"),
        table_name="service_router_worker_sync",
    )
    op.drop_table("service_router_worker_sync")
