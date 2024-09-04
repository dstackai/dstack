"""Introduce runs processing

Revision ID: 4b4319398164
Revises: b88d55c2a07d
Create Date: 2024-03-01 14:30:28.918255

"""

import sqlalchemy as sa
import sqlalchemy_utils
from alembic import op

# revision identifiers, used by Alembic.
revision = "4b4319398164"
down_revision = "b88d55c2a07d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("runs", schema=None) as batch_op:
        # last_processed_at is nullable=False later
        batch_op.add_column(sa.Column("last_processed_at", sa.DateTime(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "gateway_id", sqlalchemy_utils.types.uuid.UUIDType(binary=False), nullable=True
            )
        )
        run_termination_reason_enum = sa.Enum(
            "ALL_JOBS_DONE",
            "JOB_FAILED",
            "RETRY_LIMIT_EXCEEDED",
            "STOPPED_BY_USER",
            "ABORTED_BY_USER",
            "SERVER_ERROR",
            name="runterminationreason",
        )
        run_termination_reason_enum.create(op.get_bind(), checkfirst=True)
        batch_op.add_column(
            sa.Column(
                "termination_reason",
                run_termination_reason_enum,
                nullable=True,
            )
        )
        batch_op.add_column(sa.Column("service_spec", sa.String(length=4000), nullable=True))
        batch_op.create_foreign_key(
            batch_op.f("fk_runs_gateway_id_gateways"),
            "gateways",
            ["gateway_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.execute("UPDATE runs SET last_processed_at = submitted_at")
    op.execute(
        "UPDATE runs SET "
        "  status = 'TERMINATED' "
        "WHERE id NOT IN ( "
        "  SELECT run_id FROM jobs "
        "  WHERE status NOT IN ('TERMINATED', 'ABORTED', 'FAILED', 'DONE') "
        ")"
    )
    with op.batch_alter_table("runs", schema=None) as batch_op:
        batch_op.alter_column("last_processed_at", nullable=False)

    job_termination_reason_enum = sa.Enum(
        "FAILED_TO_START_DUE_TO_NO_CAPACITY",
        "INTERRUPTED_BY_NO_CAPACITY",
        "WAITING_RUNNER_LIMIT_EXCEEDED",
        "TERMINATED_BY_USER",
        "GATEWAY_ERROR",
        "SCALED_DOWN",
        "DONE_BY_RUNNER",
        "ABORTED_BY_USER",
        "TERMINATED_BY_SERVER",
        "CONTAINER_EXITED_WITH_ERROR",
        "PORTS_BINDING_FAILED",
        name="jobterminationreason",
    )
    job_termination_reason_enum.create(op.get_bind(), checkfirst=True)

    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.alter_column(
            "error_code",
            new_column_name="termination_reason",
            type_=job_termination_reason_enum,
            postgresql_using=("error_code::VARCHAR::jobterminationreason"),
        )
        # replica_num is nullable=False later
        batch_op.add_column(sa.Column("replica_num", sa.Integer(), nullable=True))
        batch_op.drop_column("removed")
    batch_op.execute("UPDATE jobs SET replica_num = 0")
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.alter_column("replica_num", nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.alter_column(
            "termination_reason",
            new_column_name="error_code",
            type_=sa.VARCHAR(length=34),
        )
        batch_op.add_column(
            # all jobs will get not removed
            sa.Column("removed", sa.BOOLEAN(), server_default=sa.false(), nullable=False)
        )
        batch_op.drop_column("replica_num")

    with op.batch_alter_table("runs", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("fk_runs_gateway_id_gateways"), type_="foreignkey")
        batch_op.drop_column("service_spec")
        batch_op.drop_column("termination_reason")
        batch_op.drop_column("gateway_id")
        batch_op.drop_column("last_processed_at")
    op.execute("UPDATE runs SET status = 'SUBMITTED'")
    op.execute("UPDATE jobs SET removed = TRUE")

    run_termination_reason_enum = sa.Enum(
        "ALL_JOBS_DONE",
        "JOB_FAILED",
        "RETRY_LIMIT_EXCEEDED",
        "STOPPED_BY_USER",
        "ABORTED_BY_USER",
        "SERVER_ERROR",
        name="runterminationreason",
    )
    run_termination_reason_enum.drop(op.get_bind(), checkfirst=True)

    job_termination_reason_enum = sa.Enum(
        "FAILED_TO_START_DUE_TO_NO_CAPACITY",
        "INTERRUPTED_BY_NO_CAPACITY",
        "WAITING_RUNNER_LIMIT_EXCEEDED",
        "TERMINATED_BY_USER",
        "GATEWAY_ERROR",
        "SCALED_DOWN",
        "DONE_BY_RUNNER",
        "ABORTED_BY_USER",
        "TERMINATED_BY_SERVER",
        "CONTAINER_EXITED_WITH_ERROR",
        "PORTS_BINDING_FAILED",
        name="jobterminationreason",
    )
    job_termination_reason_enum.drop(op.get_bind(), checkfirst=True)
