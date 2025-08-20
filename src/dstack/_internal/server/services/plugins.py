import itertools
from importlib import import_module
from typing import Dict

from backports.entry_points_selectable import entry_points  # backport for Python 3.9

from dstack._internal.core.errors import ServerClientError
from dstack._internal.utils.common import run_async
from dstack._internal.utils.logging import get_logger
from dstack.plugins import ApplyPolicy, ApplySpec, Plugin

logger = get_logger(__name__)


_PLUGINS: list[Plugin] = []

_BUILTIN_PLUGINS: Dict[str, str] = {"rest_plugin": "dstack.plugins.builtin.rest_plugin:RESTPlugin"}


class PluginEntrypoint:
    def __init__(self, name: str, import_path: str, is_builtin: bool = False):
        self.name = name
        self.import_path = import_path
        self.is_builtin = is_builtin

    def load(self):
        module_path, _, class_name = self.import_path.partition(":")
        try:
            module = import_module(module_path)
            plugin_class = getattr(module, class_name, None)
            if plugin_class is None:
                logger.warning(
                    ("Failed to load plugin %s: plugin class %s not found in module %s."),
                    self.name,
                    class_name,
                    module_path,
                )
                return None
            if not issubclass(plugin_class, Plugin):
                logger.warning(
                    ("Failed to load plugin %s: plugin class %s is not a subclass of Plugin."),
                    self.name,
                    class_name,
                )
                return None
            return plugin_class()
        except ImportError:
            logger.warning(
                (
                    "Failed to load plugin %s when importing %s."
                    " Ensure the module is on the import path."
                ),
                self.name,
                self.import_path,
            )
            return None


def load_plugins(enabled_plugins: list[str]):
    _PLUGINS.clear()
    entrypoints: dict[str, PluginEntrypoint] = {}
    plugins_to_load = enabled_plugins.copy()
    for entrypoint in entry_points(group="dstack.plugins"):  # type: ignore[call-arg]
        if entrypoint.name not in enabled_plugins:
            logger.info(
                ("Found not enabled plugin %s. Plugin will not be loaded."),
                entrypoint.name,
            )
            continue
        else:
            entrypoints[entrypoint.name] = PluginEntrypoint(
                entrypoint.name, entrypoint.value, is_builtin=False
            )

    for name, import_path in _BUILTIN_PLUGINS.items():
        if name not in enabled_plugins:
            logger.info(
                ("Found not enabled builtin plugin %s. Plugin will not be loaded."),
                name,
            )
        else:
            entrypoints[name] = PluginEntrypoint(name, import_path, is_builtin=True)

    for plugin_name, plugin_entrypoint in entrypoints.items():
        plugin_instance = plugin_entrypoint.load()
        if plugin_instance is not None:
            _PLUGINS.append(plugin_instance)
            plugins_to_load.remove(plugin_name)
            logger.info("Loaded plugin %s", plugin_name)

    if plugins_to_load:
        logger.warning("Enabled plugins not found: %s", plugins_to_load)


async def apply_plugin_policies(user: str, project: str, spec: ApplySpec) -> ApplySpec:
    policies = _get_apply_policies()
    for policy in policies:
        try:
            spec = await run_async(policy.on_apply, user=user, project=project, spec=spec)
        except ValueError as e:
            msg = None
            if len(e.args) > 0:
                msg = e.args[0]
            raise ServerClientError(msg)
    return spec


def _get_apply_policies() -> list[ApplyPolicy]:
    return list(itertools.chain(*[p.get_apply_policies() for p in _PLUGINS]))
