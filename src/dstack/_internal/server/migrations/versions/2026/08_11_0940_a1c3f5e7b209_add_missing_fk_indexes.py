"""Add missing foreign key indexes

Revision ID: a1c3f5e7b209
Revises: ecc9e8a0bfac
Create Date: 2026-08-11 09:40:00.000000+00:00

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "a1c3f5e7b209"
down_revision = "ecc9e8a0bfac"
branch_labels = None
depends_on = None


INDEXES = [
    ("ix_jobs_instance_id", "jobs", "instance_id"),
    ("ix_backends_project_id", "backends", "project_id"),
    ("ix_members_project_id", "members", "project_id"),
    ("ix_instances_compute_group_id", "instances", "compute_group_id"),
    ("ix_runs_fleet_id", "runs", "fleet_id"),
]


def _drop_indexes() -> None:
    for index_name, table_name, _ in INDEXES:
        op.drop_index(
            index_name,
            table_name=table_name,
            if_exists=True,
            postgresql_concurrently=True,
        )


def upgrade() -> None:
    with op.get_context().autocommit_block():
        _drop_indexes()
        for index_name, table_name, column_name in INDEXES:
            op.create_index(
                index_name,
                table_name,
                [column_name],
                unique=False,
                postgresql_concurrently=True,
            )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        _drop_indexes()
