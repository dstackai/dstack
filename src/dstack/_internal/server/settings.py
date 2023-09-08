from pathlib import Path

DSTACK_DIR_PATH = Path("~/.dstack/").expanduser()

DSTACK_SERVER_DIR_PATH = DSTACK_DIR_PATH / "server"

DSTACK_SERVER_DATA_DIR_PATH = DSTACK_SERVER_DIR_PATH / "data"
DSTACK_SERVER_DATA_DIR_PATH.mkdir(parents=True, exist_ok=True)
DATABASE_URL = f"sqlite+aiosqlite:///{str(DSTACK_SERVER_DATA_DIR_PATH.absolute())}/sqlite.db"
