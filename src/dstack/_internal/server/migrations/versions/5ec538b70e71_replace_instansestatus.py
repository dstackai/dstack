"""Replace InstanseStatus

Revision ID: 5ec538b70e71
Revises: 555138b1f77f
Create Date: 2024-03-13 10:48:29.923617

"""

# revision identifiers, used by Alembic.
revision = "5ec538b70e71"
down_revision = "555138b1f77f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass
    # op.execute(
    #     sa.sql.text(
    #         "UPDATE instances SET status = 'PROVISIONING' WHERE status = 'CREATING' OR status = 'STARTING'"
    #     )
    # )
    # op.execute(sa.sql.text("UPDATE instances SET status = 'IDLE' WHERE status = 'READY'"))


def downgrade() -> None:
    pass
    # op.execute(
    #     sa.sql.text("UPDATE instances SET status = 'STARTING' WHERE status = 'PROVISIONING'")
    # )
    # op.execute(sa.sql.text("UPDATE instances SET status = 'READY' WHERE status = 'IDLE'"))
