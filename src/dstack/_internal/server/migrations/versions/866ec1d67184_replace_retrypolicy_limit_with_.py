"""Replace RetryPolicy.limit with RetryPolicy.duration

Revision ID: 866ec1d67184
Revises: 99b4c8c954ea
Create Date: 2024-04-02 01:42:40.901164

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "866ec1d67184"
down_revision = "99b4c8c954ea"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_context().dialect.name == "sqlite":
        op.execute(
            """
            UPDATE jobs
            SET job_spec_data = json_set(
                job_spec_data,
                '$.retry_policy.duration',
                json_extract(job_spec_data, '$.retry_policy.limit')
            ) WHERE json_type(job_spec_data, '$.retry_policy.limit') IS NOT NULL
            """
        )
        op.execute(
            """
            UPDATE jobs SET
                job_spec_data = json_remove(job_spec_data, '$.retry_policy.limit')
            WHERE json_type(job_spec_data, '$.retry_policy.limit') IS NOT NULL
            """
        )

        op.execute(
            """
            UPDATE runs
            SET run_spec = json_set(
                run_spec,
                '$.profile.retry_policy.duration',
                json_extract(run_spec, '$.profile.retry_policy.limit')
            ) WHERE json_type(run_spec, '$.profile.retry_policy.limit') IS NOT NULL
            """
        )
        op.execute(
            """
            UPDATE runs SET
                run_spec = json_remove(run_spec, '$.profile.retry_policy.limit')
            WHERE json_type(run_spec, '$.profile.retry_policy.limit') IS NOT NULL
            """
        )


def downgrade() -> None:
    if op.get_context().dialect.name == "sqlite":
        op.execute(
            """
            UPDATE jobs
            SET job_spec_data = json_set(
                job_spec_data,
                '$.retry_policy.limit',
                json_extract(job_spec_data, '$.retry_policy.duration')
            ) WHERE json_type(job_spec_data, '$.retry_policy.duration') IS NOT NULL
            """
        )
        op.execute(
            """
            UPDATE jobs SET
                job_spec_data = json_remove(job_spec_data, '$.retry_policy.duration')
            WHERE json_type(job_spec_data, '$.retry_policy.duration') IS NOT NULL
            """
        )

        op.execute(
            """
            UPDATE runs
            SET run_spec = json_set(
                run_spec,
                '$.profile.retry_policy.limit',
                json_extract(run_spec, '$.profile.retry_policy.duration')
            ) WHERE json_type(run_spec, '$.profile.retry_policy.duration') IS NOT NULL
            """
        )
        op.execute(
            """
            UPDATE runs SET
                run_spec = json_remove(run_spec, '$.profile.retry_policy.duration')
            WHERE json_type(run_spec, '$.profile.retry_policy.duration') IS NOT NULL
            """
        )
