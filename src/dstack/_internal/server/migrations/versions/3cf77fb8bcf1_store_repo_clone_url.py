"""Store repo clone URL

Revision ID: 3cf77fb8bcf1
Revises: 91ac5e543037
Create Date: 2024-07-15 23:09:40.150763

"""

import json
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy_utils import UUIDType

# revision identifiers, used by Alembic.
revision = "3cf77fb8bcf1"
down_revision = "91ac5e543037"
branch_labels = None
depends_on = None

repos_table = sa.Table(
    "repos",
    sa.MetaData(),
    # partial description - only columns affected by this migration
    sa.Column("id", UUIDType(binary=False), primary_key=True, default=uuid.uuid4),
    sa.Column("info", sa.String(2000), nullable=False),
    sa.Column("creds", sa.String(5000), nullable=True),
)


def upgrade() -> None:
    select_stmt = sa.select(repos_table.c.id, repos_table.c.info, repos_table.c.creds).where(
        repos_table.c.creds.isnot(None)
    )

    batch_update_params = []

    for row in op.get_bind().execute(select_stmt).all():
        creds = json.loads(row.creds)
        info = json.loads(row.info)

        repo_host_name = info["repo_host_name"]
        repo_port = info.get("repo_port")
        repo_user_name = info["repo_user_name"]
        repo_name = info["repo_name"]

        netloc = f"{repo_host_name}:{repo_port}" if repo_port else repo_host_name

        if creds["protocol"] == "ssh":
            clone_url = f"ssh://git@{netloc}/{repo_user_name}/{repo_name}.git"
        else:
            clone_url = f"https://{netloc}/{repo_user_name}/{repo_name}.git"

        creds["clone_url"] = clone_url
        batch_update_params.append({"_id": row.id, "creds": json.dumps(creds)})

    update_stmt = (
        repos_table.update()
        .where(repos_table.c.id == sa.bindparam("_id"))
        .values(creds=sa.bindparam("creds"))
    )
    if batch_update_params:
        op.get_bind().execute(update_stmt, batch_update_params)


def downgrade() -> None:
    select_stmt = sa.select(repos_table.c.id, repos_table.c.creds).where(
        repos_table.c.creds.isnot(None)
    )

    batch_update_params = []

    for row in op.get_bind().execute(select_stmt).all():
        creds = json.loads(row.creds)
        creds.pop("clone_url", None)
        batch_update_params.append({"_id": row.id, "creds": json.dumps(creds)})

    update_stmt = (
        repos_table.update()
        .where(repos_table.c.id == sa.bindparam("_id"))
        .values(creds=sa.bindparam("creds"))
    )
    if batch_update_params:
        op.get_bind().execute(update_stmt, batch_update_params)
