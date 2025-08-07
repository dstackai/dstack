"""Add instance health

Revision ID: 728b1488b1b4
Revises: 25479f540245
Create Date: 2025-08-01 14:56:20.466990

"""

import sqlalchemy as sa
import sqlalchemy_utils
from alembic import op

import dstack._internal.server.models

# revision identifiers, used by Alembic.
revision = "728b1488b1b4"
down_revision = "25479f540245"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "instance_health_checks",
        sa.Column("id", sqlalchemy_utils.types.uuid.UUIDType(binary=False), nullable=False),
        sa.Column(
            "instance_id", sqlalchemy_utils.types.uuid.UUIDType(binary=False), nullable=False
        ),
        sa.Column("collected_at", dstack._internal.server.models.NaiveDateTime(), nullable=False),
        sa.Column("status", sa.VARCHAR(length=100), nullable=False),
        sa.Column("response", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["instance_id"],
            ["instances.id"],
            name=op.f("fk_instance_health_checks_instance_id_instances"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_instance_health_checks")),
    )
    with op.batch_alter_table("instances", schema=None) as batch_op:
        batch_op.add_column(sa.Column("health", sa.VARCHAR(length=100), nullable=True))
    op.execute("UPDATE instances SET health = 'HEALTHY'")
    with op.batch_alter_table("instances", schema=None) as batch_op:
        batch_op.alter_column("health", existing_type=sa.VARCHAR(length=100), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("instances", schema=None) as batch_op:
        batch_op.drop_column("health")

    op.drop_table("instance_health_checks")
