import sys
from pathlib import Path
from types import ModuleType

from dstack._internal.server import settings


class TestServerDirIsolation:
    """
    Guards the invariant that lets one fixture redirect all server state: paths under
    `settings.SERVER_DIR_PATH` are derived on access, never bound at import time.
    """

    def test_server_dir_is_redirected(self):
        assert settings.DSTACK_DIR_PATH not in settings.SERVER_DIR_PATH.parents, (
            "the `server_dir` fixture is not in effect, so tests share the real"
            " ~/.dstack/server with each other and with any locally running server"
        )

    def test_no_server_path_is_derived_at_import_time(self):
        """
        A module-level `X = SERVER_DIR_PATH / "y"` captures the real path at import, before
        any fixture can redirect it. Covers already-imported modules, which is everything
        the test suite reaches.
        """
        offenders = []
        for module in list(sys.modules.values()):
            if not isinstance(module, ModuleType):
                continue
            name = getattr(module, "__name__", "")
            if not name.startswith("dstack._internal.server"):
                continue
            for attr, value in list(vars(module).items()):
                if isinstance(value, Path) and settings.DSTACK_DIR_PATH in value.parents:
                    offenders.append(f"{name}.{attr} = {value}")
        assert not offenders, (
            "derive server paths on access (a function) so that patching SERVER_DIR_PATH"
            f" redirects them; bound at import time: {sorted(offenders)}"
        )
