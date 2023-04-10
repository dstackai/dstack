from alembic import command, config

from dstack.hub.db import db


async def migrate():
    async with db.engine.begin() as connection:
        await connection.run_sync(_run_alembic_upgrade)


def _run_alembic_upgrade(connection):
    alembic_cfg = config.Config()
    alembic_cfg.set_main_option("script_location", "dstack.hub:migration")
    alembic_cfg.attributes["connection"] = connection
    command.upgrade(alembic_cfg, "head")
