"""Replace InstanceStatus.READY with InstanceStatus.IDLE

Revision ID: b88d55c2a07d
Revises: ed0ca30e13bb
Create Date: 2024-02-28 06:15:32.172109

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "b88d55c2a07d"
down_revision = "ed0ca30e13bb"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.sql.text("UPDATE instances SET status = 'READY' WHERE status = 'IDLE'"))


def downgrade() -> None:
    op.execute(sa.sql.text("UPDATE instances SET status = 'IDLE' WHERE status = 'READY'"))
