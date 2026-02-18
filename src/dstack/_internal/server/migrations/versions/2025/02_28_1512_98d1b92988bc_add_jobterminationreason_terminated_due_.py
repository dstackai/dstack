"""Add JobTerminationReason.TERMINATED_DUE_TO_UTILIZATION_POLICY

Revision ID: 98d1b92988bc
Revises: 60e444118b6d
Create Date: 2025-02-28 15:12:37.649876

"""

import sqlalchemy as sa
from alembic import op
from alembic_postgresql_enum import TableReference

# revision identifiers, used by Alembic.
revision = "98d1b92988bc"
down_revision = "60e444118b6d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.alter_column(
            "termination_reason",
            existing_type=sa.VARCHAR(length=34),
            type_=sa.Enum(
                "FAILED_TO_START_DUE_TO_NO_CAPACITY",
                "INTERRUPTED_BY_NO_CAPACITY",
                "WAITING_INSTANCE_LIMIT_EXCEEDED",
                "WAITING_RUNNER_LIMIT_EXCEEDED",
                "TERMINATED_BY_USER",
                "VOLUME_ERROR",
                "GATEWAY_ERROR",
                "SCALED_DOWN",
                "DONE_BY_RUNNER",
                "ABORTED_BY_USER",
                "TERMINATED_BY_SERVER",
                "INACTIVITY_DURATION_EXCEEDED",
                "TERMINATED_DUE_TO_UTILIZATION_POLICY",
                "CONTAINER_EXITED_WITH_ERROR",
                "PORTS_BINDING_FAILED",
                "CREATING_CONTAINER_ERROR",
                "EXECUTOR_ERROR",
                "MAX_DURATION_EXCEEDED",
                name="jobterminationreason",
            ),
            existing_nullable=True,
        )
    # PostgreSQL
    op.sync_enum_values(
        enum_schema="public",
        enum_name="jobterminationreason",
        new_values=[
            "FAILED_TO_START_DUE_TO_NO_CAPACITY",
            "INTERRUPTED_BY_NO_CAPACITY",
            "WAITING_INSTANCE_LIMIT_EXCEEDED",
            "WAITING_RUNNER_LIMIT_EXCEEDED",
            "TERMINATED_BY_USER",
            "VOLUME_ERROR",
            "GATEWAY_ERROR",
            "SCALED_DOWN",
            "DONE_BY_RUNNER",
            "ABORTED_BY_USER",
            "TERMINATED_BY_SERVER",
            "INACTIVITY_DURATION_EXCEEDED",
            "TERMINATED_DUE_TO_UTILIZATION_POLICY",
            "CONTAINER_EXITED_WITH_ERROR",
            "PORTS_BINDING_FAILED",
            "CREATING_CONTAINER_ERROR",
            "EXECUTOR_ERROR",
            "MAX_DURATION_EXCEEDED",
        ],
        affected_columns=[
            TableReference(
                table_schema="public", table_name="jobs", column_name="termination_reason"
            )
        ],
        enum_values_to_rename=[],
    )


def downgrade() -> None:
    # SQLite
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.alter_column(
            "termination_reason",
            existing_type=sa.Enum(
                "FAILED_TO_START_DUE_TO_NO_CAPACITY",
                "INTERRUPTED_BY_NO_CAPACITY",
                "WAITING_INSTANCE_LIMIT_EXCEEDED",
                "WAITING_RUNNER_LIMIT_EXCEEDED",
                "TERMINATED_BY_USER",
                "VOLUME_ERROR",
                "GATEWAY_ERROR",
                "SCALED_DOWN",
                "DONE_BY_RUNNER",
                "ABORTED_BY_USER",
                "TERMINATED_BY_SERVER",
                "INACTIVITY_DURATION_EXCEEDED",
                "TERMINATED_DUE_TO_UTILIZATION_POLICY",
                "CONTAINER_EXITED_WITH_ERROR",
                "PORTS_BINDING_FAILED",
                "CREATING_CONTAINER_ERROR",
                "EXECUTOR_ERROR",
                "MAX_DURATION_EXCEEDED",
                name="jobterminationreason",
            ),
            type_=sa.VARCHAR(length=34),
            existing_nullable=True,
        )
    # PostgreSQL
    op.sync_enum_values(
        enum_schema="public",
        enum_name="jobterminationreason",
        new_values=[
            "FAILED_TO_START_DUE_TO_NO_CAPACITY",
            "INTERRUPTED_BY_NO_CAPACITY",
            "WAITING_INSTANCE_LIMIT_EXCEEDED",
            "WAITING_RUNNER_LIMIT_EXCEEDED",
            "TERMINATED_BY_USER",
            "VOLUME_ERROR",
            "GATEWAY_ERROR",
            "SCALED_DOWN",
            "DONE_BY_RUNNER",
            "ABORTED_BY_USER",
            "TERMINATED_BY_SERVER",
            "INACTIVITY_DURATION_EXCEEDED",
            "CONTAINER_EXITED_WITH_ERROR",
            "PORTS_BINDING_FAILED",
            "CREATING_CONTAINER_ERROR",
            "EXECUTOR_ERROR",
            "MAX_DURATION_EXCEEDED",
        ],
        affected_columns=[
            TableReference(
                table_schema="public", table_name="jobs", column_name="termination_reason"
            )
        ],
        enum_values_to_rename=[],
    )
