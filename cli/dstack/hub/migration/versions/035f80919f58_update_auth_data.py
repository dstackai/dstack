"""update_auth_data

Revision ID: 035f80919f58
Revises: 3b900659c822
Create Date: 2023-05-25 10:06:27.191618

"""
import json

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "035f80919f58"
down_revision = "3b900659c822"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    results = conn.execute(sa.text("SELECT name, backend, auth FROM projects"))
    for name, backend, auth in results:
        if backend == "local":
            continue
        auth_data = json.loads(auth)
        if backend == "aws":
            auth_data["type"] = "access_key"
        elif backend == "azure":
            auth_data["type"] = "client"
        elif backend == "gcp":
            auth_data = {
                "type": "service_account",
                "filename": auth_data["credentials_filename"],
                "data": auth_data["credentials"],
            }
        conn.execute(
            sa.text("UPDATE projects SET auth=:auth WHERE name=:name"),
            {"name": name, "auth": json.dumps(auth_data)},
        )


def downgrade() -> None:
    conn = op.get_bind()
    results = conn.execute(sa.text("SELECT name, backend, auth FROM projects"))
    for name, backend, auth in results:
        if backend == "local":
            continue
        auth_data = json.loads(auth)
        if auth_data["type"] == "default":
            conn.execute(sa.text("DELETE FROM projects WHERE name=:name"), {"name": name})
            continue
        if backend == "aws":
            del auth_data["type"]
        elif backend == "azure":
            del auth_data["type"]
        elif backend == "gcp":
            auth_data = {
                "credentials_filename": auth_data["filename"],
                "credentials": auth_data["data"],
            }
        conn.execute(
            sa.text("UPDATE projects SET auth=:auth WHERE name=:name"),
            {"name": name, "auth": json.dumps(auth_data)},
        )
