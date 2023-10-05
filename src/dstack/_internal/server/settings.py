import os
from pathlib import Path

DSTACK_DIR_PATH = Path("~/.dstack/").expanduser()

SERVER_DIR_PATH = DSTACK_DIR_PATH / "server"

SERVER_CONFIG_FILE_PATH = SERVER_DIR_PATH / "config.yaml"

SERVER_DATA_DIR_PATH = SERVER_DIR_PATH / "data"
SERVER_DATA_DIR_PATH.mkdir(parents=True, exist_ok=True)
DATABASE_URL = f"sqlite+aiosqlite:///{str(SERVER_DATA_DIR_PATH.absolute())}/sqlite.db"


SERVER_HOST = os.getenv("DSTACK_SERVER_HOST")
SERVER_PORT = os.getenv("DSTACK_SERVER_PORT")
SERVER_URL = f"http://{SERVER_HOST}:{SERVER_PORT}"


ROOT_LOG_LEVEL = os.getenv("DSTACK_SERVER_ROOT_LOG_LEVEL", "ERROR").upper()
LOG_LEVEL = os.getenv("DSTACK_SERVER_LOG_LEVEL", "ERROR").upper()

DEFAULT_PROJECT_NAME = "main"
DEFAULT_GATEWAY_NAME = "default-gateway"

LOCAL_BACKEND_ENABLED = os.getenv("DSTACK_LOCAL_BACKEND_ENABLED") is not None
