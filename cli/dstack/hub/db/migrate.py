from alembic import command, config

from dstack.hub.db import Database, data_path
from dstack.hub.db.models import Member, Project, Role, Scope, User, association_table_user_project

alembic_cfg = config.Config()
alembic_cfg.set_main_option("script_location", "dstack.hub:migration")
alembic_cfg.set_main_option(
    "sqlalchemy.url", f"sqlite+aiosqlite:///{str(data_path.absolute())}/sqlite.db"
)


def run_alembic_upgrade(connection, cfg):
    cfg.attributes["connection"] = connection
    command.upgrade(cfg, "head")


async def migrate():
    async with Database.engine.begin() as connection:
        await connection.run_sync(run_alembic_upgrade, alembic_cfg)
