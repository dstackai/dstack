"""Migrate InstanceStatus.CREATING and InstanceStatus.STARTING to InstanceStatus.PROVISIONING

Revision ID: ed0ca30e13bb
Revises: 1a48dfe44a40
Create Date: 2024-02-28 05:47:42.993913

"""

# revision identifiers, used by Alembic.
revision = "ed0ca30e13bb"
down_revision = "1a48dfe44a40"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass
    # op.execute(
    #     sa.sql.text(
    #         "UPDATE instances SET status = 'PROVISIONING' WHERE status = 'CREATING' OR status = 'STARTING'"
    #     )
    # )


def downgrade() -> None:
    pass
    # op.execute(
    #     sa.sql.text("UPDATE instances SET status = 'STARTING' WHERE status = 'PROVISIONING'")
    # )
