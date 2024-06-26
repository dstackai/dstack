"""Add VolumeModel

Revision ID: 98cd9c8b5927
Revises: b4d6ad60db08
Create Date: 2024-06-26 11:22:50.433204

"""

import sqlalchemy as sa
import sqlalchemy_utils
from alembic import op

# revision identifiers, used by Alembic.
revision = "98cd9c8b5927"
down_revision = "b4d6ad60db08"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "volumes",
        sa.Column("id", sqlalchemy_utils.types.uuid.UUIDType(binary=False), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column(
            "project_id", sqlalchemy_utils.types.uuid.UUIDType(binary=False), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_processed_at", sa.DateTime(), nullable=False),
        sa.Column("deleted", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("SUBMITTED", "PROVISIONING", "ACTIVE", "FAILED", name="volumestatus"),
            nullable=False,
        ),
        sa.Column("status_message", sa.Text(), nullable=True),
        sa.Column("configuration", sa.Text(), nullable=False),
        sa.Column("volume_provisioning_data", sa.Text(), nullable=True),
        sa.Column("volume_attachment_data", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_volumes_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_volumes")),
    )
    op.create_table(
        "volumes_attachments",
        sa.Column("volume_id", sqlalchemy_utils.types.uuid.UUIDType(binary=False), nullable=False),
        sa.Column(
            "instace_id", sqlalchemy_utils.types.uuid.UUIDType(binary=False), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["instace_id"],
            ["instances.id"],
            name=op.f("fk_volumes_attachments_instace_id_instances"),
        ),
        sa.ForeignKeyConstraint(
            ["volume_id"], ["volumes.id"], name=op.f("fk_volumes_attachments_volume_id_volumes")
        ),
        sa.PrimaryKeyConstraint("volume_id", "instace_id", name=op.f("pk_volumes_attachments")),
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table("volumes_attachments")
    op.drop_table("volumes")
    # ### end Alembic commands ###
