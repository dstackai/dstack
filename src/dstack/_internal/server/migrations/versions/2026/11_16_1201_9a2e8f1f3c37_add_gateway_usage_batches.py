"""Add Gateway usage batches with historical replica/Gateway IDs

Revision ID: 9a2e8f1f3c37
Revises: 6b5610ff36c1
Create Date: 2026-11-16 12:01:47.939623+00:00

"""

import sqlalchemy as sa
import sqlalchemy_utils
from alembic import op

import dstack._internal.server.models

# revision identifiers, used by Alembic.
revision = "9a2e8f1f3c37"
down_revision = "6b5610ff36c1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "usage_batches",
        sa.Column("id", sqlalchemy_utils.types.uuid.UUIDType(binary=False), nullable=False),
        sa.Column(
            "gateway_replica_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            nullable=False,
        ),
        sa.Column("gateway_id", sqlalchemy_utils.types.uuid.UUIDType(binary=False), nullable=True),
        sa.Column("batch_id", sa.String(length=128), nullable=False),
        sa.Column(
            "interval_start", dstack._internal.server.models.NaiveDateTime(), nullable=False
        ),
        sa.Column("interval_end", dstack._internal.server.models.NaiveDateTime(), nullable=False),
        sa.Column("received_at", dstack._internal.server.models.NaiveDateTime(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_usage_batches")),
        sa.UniqueConstraint(
            "gateway_replica_id", "batch_id", name="uq_usage_batches_replica_batch"
        ),
        sa.UniqueConstraint(
            "gateway_replica_id", "interval_start", name="uq_usage_batches_replica_minute"
        ),
    )
    op.create_index(
        "ix_usage_batches_gateway_interval", "usage_batches", ["gateway_id", "interval_start"]
    )
    op.create_table(
        "usage_counters",
        sa.Column(
            "usage_baches_id", sqlalchemy_utils.types.uuid.UUIDType(binary=False), nullable=False
        ),
        sa.Column("consumer_subject_id", sa.String(length=128), nullable=False),
        sa.Column("service_id", sa.String(length=128), nullable=False),
        sa.Column("prompt_tokens", sa.BigInteger(), nullable=False),
        sa.Column("cached_prompt_tokens", sa.BigInteger(), nullable=False),
        sa.Column("completion_tokens", sa.BigInteger(), nullable=False),
        sa.Column("total_tokens", sa.BigInteger(), nullable=False),
        sa.Column("unknown_usage_attempts", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["usage_baches_id"],
            ["usage_batches.id"],
            name=op.f("fk_usage_counters_usage_baches_id_usage_batches"),
        ),
        sa.PrimaryKeyConstraint(
            "usage_baches_id", "consumer_subject_id", "service_id", name=op.f("pk_usage_counters")
        ),
    )


def downgrade() -> None:
    conn = op.get_bind()
    if conn.scalar(sa.text("SELECT COUNT(*) FROM usage_batches")) or conn.scalar(
        sa.text("SELECT COUNT(*) FROM usage_counters")
    ):
        raise ValueError("Populated usage downgrade requires a backup and reconciliation")
    op.drop_table("usage_counters")
    op.drop_table("usage_batches")
