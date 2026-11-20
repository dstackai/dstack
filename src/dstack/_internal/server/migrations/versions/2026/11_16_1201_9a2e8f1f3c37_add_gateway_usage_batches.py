"""Add Gateway usage batches with one row per user and run

Revision ID: 9a2e8f1f3c37
Revises: 6b5610ff36c1
Create Date: 2026-11-16 12:01:47.939623+00:00

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy_utils import UUIDType

from dstack._internal.server.models import NaiveDateTime

# revision identifiers, used by Alembic.
revision = "9a2e8f1f3c37"
down_revision = "6b5610ff36c1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    row_number_check = "batch_row_number >= 0"
    sqlite_checks = []
    if op.get_context().dialect.name == "sqlite":
        row_number_check = "typeof(batch_row_number) = 'integer' AND " + row_number_check
        sqlite_checks.append(
            sa.CheckConstraint(
                "typeof(prompt_tokens) = 'integer' AND typeof(cached_prompt_tokens) = 'integer' "
                "AND typeof(completion_tokens) = 'integer' AND typeof(total_tokens) = 'integer' "
                "AND typeof(unknown_usage_attempts) = 'integer'",
                name=op.f("ck_usage_batches_integer_counters"),
            )
        )

    op.create_table(
        "usage_batches",
        sa.Column("id", UUIDType(binary=False), nullable=False),
        sa.Column("gateway_replica_id", UUIDType(binary=False), nullable=False),
        sa.Column("gateway_id", UUIDType(binary=False), nullable=False),
        sa.Column("batch_id", sa.String(length=128), nullable=False),
        sa.Column("interval_start", NaiveDateTime(), nullable=False),
        sa.Column("interval_end", NaiveDateTime(), nullable=False),
        sa.Column("received_at", NaiveDateTime(), nullable=False),
        sa.Column("user_id", UUIDType(binary=False), nullable=False),
        sa.Column("run_id", UUIDType(binary=False), nullable=False),
        sa.Column("prompt_tokens", sa.BigInteger(), nullable=False),
        sa.Column("cached_prompt_tokens", sa.BigInteger(), nullable=False),
        sa.Column("completion_tokens", sa.BigInteger(), nullable=False),
        sa.Column("total_tokens", sa.BigInteger(), nullable=False),
        sa.Column("unknown_usage_attempts", sa.BigInteger(), nullable=False),
        sa.Column("batch_row_number", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_usage_batches")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="RESTRICT",
            name=op.f("fk_usage_batches_user_id_users"),
        ),
        sa.UniqueConstraint(
            "gateway_replica_id",
            "batch_id",
            "user_id",
            "run_id",
            name="uq_usage_batches_replica_batch_pair",
        ),
        sa.CheckConstraint(row_number_check, name=op.f("ck_usage_batches_row_number")),
        sa.CheckConstraint(
            "prompt_tokens >= 0 AND cached_prompt_tokens >= 0 "
            "AND cached_prompt_tokens <= prompt_tokens AND completion_tokens >= 0 "
            "AND total_tokens >= 0 AND total_tokens - prompt_tokens = completion_tokens "
            "AND unknown_usage_attempts >= 0",
            name=op.f("ck_usage_batches_counters"),
        ),
        *sqlite_checks,
    )
    first_row = sa.text("batch_row_number = 0")
    op.create_index(
        "uq_usage_batches_replica_batch",
        "usage_batches",
        ["gateway_replica_id", "batch_id"],
        unique=True,
        sqlite_where=first_row,
        postgresql_where=first_row,
    )
    op.create_index(
        "uq_usage_batches_replica_minute",
        "usage_batches",
        ["gateway_replica_id", "interval_start"],
        unique=True,
        sqlite_where=first_row,
        postgresql_where=first_row,
    )
    op.create_index(
        "ix_usage_batches_gateway_interval", "usage_batches", ["gateway_id", "interval_start"]
    )
    op.create_index("ix_usage_batches_user_id", "usage_batches", ["user_id"])
    op.create_index("ix_usage_batches_run_id", "usage_batches", ["run_id"])


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT 1 FROM usage_batches LIMIT 1")):
        raise ValueError("Populated usage downgrade requires a backup and reconciliation")
    op.drop_table("usage_batches")
