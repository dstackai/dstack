"""Add InstanceModel.provisioning_job_id for placeholder instances.

Revision ID: d5addc51d0c3
Revises: 94fcd7e38b7e
Create Date: 2026-04-22 12:00:00.000000+00:00

"""

import sqlalchemy_utils
from alembic import op
from sqlalchemy import Column

# revision identifiers, used by Alembic.
revision = "d5addc51d0c3"
down_revision = "94fcd7e38b7e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "instances",
        Column(
            "provisioning_job_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("instances", "provisioning_job_id")
