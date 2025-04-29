import itertools
from importlib import import_module

from backports.entry_points_selectable import entry_points  # backport for Python 3.9

from dstack._internal.core.errors import ServerClientError
from dstack._internal.utils.logging import get_logger
from dstack.plugins import ApplyPolicy, ApplySpec, Plugin

logger = get_logger(__name__)


_PLUGINS: list[Plugin] = []


def load_plugins(enabled_plugins: list[str]):
    _PLUGINS.clear()
    plugins_entrypoints = entry_points(group="dstack.plugins")
    plugins_to_load = enabled_plugins.copy()
    for entrypoint in plugins_entrypoints:
        if entrypoint.name not in enabled_plugins:
            logger.info(
                ("Found not enabled plugin %s. Plugin will not be loaded."),
                entrypoint.name,
            )
            continue
        try:
            module_path, _, class_name = entrypoint.value.partition(":")
            module = import_module(module_path)
        except ImportError:
            logger.warning(
                (
                    "Failed to load plugin %s when importing %s."
                    " Ensure the module is on the import path."
                ),
                entrypoint.name,
                entrypoint.value,
            )
            continue
        plugin_class = getattr(module, class_name, None)
        if plugin_class is None:
            logger.warning(
                ("Failed to load plugin %s: plugin class %s not found in module %s."),
                entrypoint.name,
                class_name,
                module_path,
            )
            continue
        if not issubclass(plugin_class, Plugin):
            logger.warning(
                ("Failed to load plugin %s: plugin class %s is not a subclass of Plugin."),
                entrypoint.name,
                class_name,
            )
            continue
        plugins_to_load.remove(entrypoint.name)
        _PLUGINS.append(plugin_class())
        logger.info("Loaded plugin %s", entrypoint.name)
    if plugins_to_load:
        logger.warning("Enabled plugins not found: %s", plugins_to_load)


def apply_plugin_policies(user: str, project: str, spec: ApplySpec) -> ApplySpec:
    policies = _get_apply_policies()
    for policy in policies:
        try:
            spec = policy.on_apply(user=user, project=project, spec=spec)
        except ValueError as e:
            msg = None
            if len(e.args) > 0:
                msg = e.args[0]
            raise ServerClientError(msg)
    return spec


def _get_apply_policies() -> list[ApplyPolicy]:
    return list(itertools.chain(*[p.get_apply_policies() for p in _PLUGINS]))
