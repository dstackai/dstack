"""Add InstanceModel.provisioning_job_id for placeholder instances.

Revision ID: a1b2c3d4e5f6
Revises: 94fcd7e38b7e
Create Date: 2026-04-22 12:00:00.000000+00:00

"""

import sqlalchemy_utils
from alembic import op
from sqlalchemy import Column

# revision identifiers, used by Alembic.
revision = "a1b2c3d4e5f6"
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
