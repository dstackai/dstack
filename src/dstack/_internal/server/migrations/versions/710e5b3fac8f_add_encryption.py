"""Add encryption

Revision ID: 710e5b3fac8f
Revises: c00090eaef21
Create Date: 2024-08-15 10:24:30.113834

"""

import hashlib

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "710e5b3fac8f"
down_revision = "c00090eaef21"
branch_labels = None
depends_on = None


ENCODED_PREFIX = "enc:identity:noname:"


def upgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("token_hash", sa.String(length=2000), nullable=True))
        batch_op.create_unique_constraint(batch_op.f("uq_users_token_hash"), ["token_hash"])

    batch_update_params = []
    result = op.get_bind().execute(sa.text("SELECT id, token FROM users"))
    for row in result:
        token_hash = hashlib.sha256(row.token.encode()).hexdigest()
        batch_update_params.append({"token_hash": token_hash, "id": row.id})
    if batch_update_params:
        op.get_bind().execute(
            sa.text("UPDATE users SET token_hash = :token_hash WHERE id = :id"),
            batch_update_params,
        )

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.alter_column("token_hash", nullable=False)

    op.execute(f"UPDATE backends SET auth = '{ENCODED_PREFIX}' || auth")
    op.execute(f"UPDATE users SET token = '{ENCODED_PREFIX}' || token")


def downgrade() -> None:
    # Assumes all rows decrypted to 'enc:identity:' before downgrading
    op.execute(f"UPDATE users SET token = SUBSTRING(token, {len(ENCODED_PREFIX) + 1})")
    op.execute(f"UPDATE backends SET auth = SUBSTRING(auth, {len(ENCODED_PREFIX) + 1})")

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("uq_users_token_hash"), type_="unique")
        batch_op.drop_column("token_hash")
