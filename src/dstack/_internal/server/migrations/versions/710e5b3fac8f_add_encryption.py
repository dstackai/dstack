"""Add encryption

Revision ID: 710e5b3fac8f
Revises: c00090eaef21
Create Date: 2024-08-15 10:24:30.113834

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "710e5b3fac8f"
down_revision = "c00090eaef21"
branch_labels = None
depends_on = None


ENCODED_PREFIX = "enc:identity:"


def upgrade() -> None:
    op.execute(f"UPDATE backends SET auth = '{ENCODED_PREFIX}' || auth")


def downgrade() -> None:
    # Assumes all rows decrypted to 'enc:identity:' before downgrading
    op.execute(f"UPDATE backends SET auth = SUBSTRING(auth, {len(ENCODED_PREFIX) + 1})")
