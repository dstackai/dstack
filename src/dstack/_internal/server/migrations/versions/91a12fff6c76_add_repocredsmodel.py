"""Add RepoCredsModel

Revision ID: 91a12fff6c76
Revises: 82b32a135ea2
Create Date: 2024-11-14 10:31:07.112472

"""

import sqlalchemy as sa
import sqlalchemy_utils
from alembic import op

# revision identifiers, used by Alembic.
revision = "91a12fff6c76"
down_revision = "82b32a135ea2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "repo_creds",
        sa.Column("id", sqlalchemy_utils.types.uuid.UUIDType(binary=False), nullable=False),
        sa.Column("repo_id", sqlalchemy_utils.types.uuid.UUIDType(binary=False), nullable=False),
        sa.Column("user_id", sqlalchemy_utils.types.uuid.UUIDType(binary=False), nullable=False),
        sa.Column("creds", sa.String(length=10000), nullable=False),
        sa.ForeignKeyConstraint(
            ["repo_id"], ["repos.id"], name=op.f("fk_repo_creds_repo_id_repos"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_repo_creds_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_repo_creds")),
        sa.UniqueConstraint("repo_id", "user_id", name="uq_repo_creds_repo_id_user_id"),
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table("repo_creds")
    # ### end Alembic commands ###
