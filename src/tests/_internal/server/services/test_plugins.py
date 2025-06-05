import logging
from importlib import import_module
from importlib.metadata import EntryPoint
from unittest.mock import MagicMock, patch

import pytest

from dstack._internal.server.services.plugins import _PLUGINS, load_plugins
from dstack.plugins import Plugin
from dstack.plugins.builtin.rest_plugin import RESTPlugin


class DummyPlugin1(Plugin):
    pass


class DummyPlugin2(Plugin):
    pass


class NotAPlugin:
    pass


@pytest.fixture(autouse=True)
def clear_plugins():
    _PLUGINS.clear()
    yield
    _PLUGINS.clear()


class TestLoadPlugins:
    @patch("dstack._internal.server.services.plugins.entry_points")
    @patch("dstack._internal.server.services.plugins.import_module")
    @pytest.mark.parametrize(
        ["plugin_name", "plugin_module_path", "plugin_class"],
        [
            ("plugin1", "dummy.plugins", DummyPlugin1),
            ("rest_plugin", "dstack.plugins.builtin.rest_plugin", RESTPlugin),
        ],
    )
    def test_load_single_plugin(
        self,
        mock_import_module,
        mock_entry_points,
        caplog,
        plugin_name,
        plugin_module_path,
        plugin_class,
    ):
        mock_entry_points.return_value = [
            EntryPoint(
                name=plugin_name,
                value=f"{plugin_module_path}:{plugin_class.__name__}",
                group="dstack.plugins",
            )
        ]
        mock_module = MagicMock()
        setattr(mock_module, plugin_class.__name__, plugin_class)
        # if it's a built-in plugin, do the real import
        mock_import_module.side_effect = (
            lambda module_path: import_module(module_path)
            if module_path.startswith("dstack.plugins.builtin")
            else mock_module
        )

        with caplog.at_level(logging.INFO):
            load_plugins([plugin_name])

        assert len(_PLUGINS) == 1
        assert isinstance(_PLUGINS[0], plugin_class)
        mock_entry_points.assert_called_once_with(group="dstack.plugins")
        mock_import_module.assert_called_once_with(plugin_module_path)
        assert f"Loaded plugin {plugin_name}" in caplog.text

    @patch("dstack._internal.server.services.plugins.entry_points")
    @patch("dstack._internal.server.services.plugins.import_module")
    @pytest.mark.parametrize(
        ["plugin_names", "plugin_module_paths", "plugin_classes"],
        [
            (
                ["plugin1", "plugin2"],
                ["dummy.plugins", "dummy.plugins"],
                [DummyPlugin1, DummyPlugin2],
            ),
            (
                ["plugin1", "plugin2", "rest_plugin"],
                ["dummy.plugins", "dummy.plugins", "dstack.plugins.builtin.rest_plugin"],
                [DummyPlugin1, DummyPlugin2, RESTPlugin],
            ),
        ],
        ids=["multiple_plugins_without_builtin_plugin", "multiple_plugins_with_builtin_plugin"],
    )
    def test_load_multiple_plugins(
        self,
        mock_import_module,
        mock_entry_points,
        caplog,
        plugin_names,
        plugin_module_paths,
        plugin_classes,
    ):
        mock_entry_points.return_value = [
            EntryPoint(
                name=plugin_name,
                value=f"{plugin_module_path}:{plugin_class.__name__}",
                group="dstack.plugins",
            )
            for plugin_name, plugin_module_path, plugin_class in zip(
                plugin_names, plugin_module_paths, plugin_classes
            )
        ]
        mock_module = MagicMock()

        for plugin_class, plugin_module_path in zip(plugin_classes, plugin_module_paths):
            if not plugin_module_path.startswith("dstack.plugins.builtin"):
                setattr(mock_module, plugin_class.__name__, plugin_class)

        mock_import_module.side_effect = (
            lambda module_path: import_module(module_path)
            if module_path.startswith("dstack.plugins.builtin")
            else mock_module
        )

        with caplog.at_level(logging.INFO):
            load_plugins(plugin_names)

        assert len(_PLUGINS) == len(plugin_names)
        for i, plugin_class in enumerate(plugin_classes):
            assert isinstance(_PLUGINS[i], plugin_class)

        for plugin_name in plugin_names:
            assert f"Loaded plugin {plugin_name}" in caplog.text

    @patch("dstack._internal.server.services.plugins.entry_points")
    @patch("dstack._internal.server.services.plugins.import_module")
    def test_plugin_not_enabled(self, mock_import_module, mock_entry_points, caplog):
        mock_entry_points.return_value = [
            EntryPoint(
                name="plugin1",
                value="dummy.plugins:DummyPlugin1",
                group="dstack.plugins",
            )
        ]

        with caplog.at_level(logging.INFO):
            load_plugins([])  # Enable no plugins

        assert len(_PLUGINS) == 0
        mock_import_module.assert_not_called()
        assert "Found not enabled plugin plugin1" in caplog.text

    @patch("dstack._internal.server.services.plugins.entry_points")
    @patch("dstack._internal.server.services.plugins.import_module")
    def test_enabled_plugin_not_found(self, mock_import_module, mock_entry_points, caplog):
        mock_entry_points.return_value = [
            EntryPoint(
                name="plugin1",
                value="dummy.plugins:DummyPlugin1",
                group="dstack.plugins",
            )
        ]

        with caplog.at_level(logging.INFO):
            load_plugins(["plugin2"])  # Enable a plugin that doesn't have an entry point

        assert len(_PLUGINS) == 0
        mock_import_module.assert_not_called()
        assert "Found not enabled plugin plugin1" in caplog.text
        assert "Enabled plugins not found: ['plugin2']" in caplog.text

    @patch("dstack._internal.server.services.plugins.entry_points")
    @patch(
        "dstack._internal.server.services.plugins.import_module",
        side_effect=ImportError("Module not found"),
    )
    def test_import_error(self, mock_import_module, mock_entry_points, caplog):
        mock_entry_points.return_value = [
            EntryPoint(
                name="plugin1",
                value="dummy.plugins:DummyPlugin1",
                group="dstack.plugins",
            )
        ]

        with caplog.at_level(logging.INFO):
            load_plugins(["plugin1"])

        assert len(_PLUGINS) == 0
        assert (
            "Failed to load plugin plugin1 when importing dummy.plugins:DummyPlugin1"
            in caplog.text
        )
        assert "Enabled plugins not found: ['plugin1']" in caplog.text  # Because loading failed

    @patch("dstack._internal.server.services.plugins.entry_points")
    @patch("dstack._internal.server.services.plugins.import_module")
    def test_class_not_found(self, mock_import_module, mock_entry_points, caplog):
        mock_entry_points.return_value = [
            EntryPoint(
                name="plugin1",
                value="dummy.plugins:NonExistentClass",
                group="dstack.plugins",
            )
        ]
        mock_module = MagicMock()
        # Simulate the class not being present
        del mock_module.NonExistentClass
        mock_import_module.return_value = mock_module

        with caplog.at_level(logging.INFO):
            load_plugins(["plugin1"])

        assert len(_PLUGINS) == 0
        assert (
            "Failed to load plugin plugin1: plugin class NonExistentClass not found" in caplog.text
        )
        assert "Enabled plugins not found: ['plugin1']" in caplog.text

    @patch("dstack._internal.server.services.plugins.entry_points")
    @patch("dstack._internal.server.services.plugins.import_module")
    def test_not_a_plugin_subclass(self, mock_import_module, mock_entry_points, caplog):
        mock_entry_points.return_value = [
            EntryPoint(
                name="plugin1",
                value="dummy.plugins:NotAPlugin",
                group="dstack.plugins",
            )
        ]
        mock_module = MagicMock()
        mock_module.NotAPlugin = NotAPlugin
        mock_import_module.return_value = mock_module

        with caplog.at_level(logging.INFO):
            load_plugins(["plugin1"])

        assert len(_PLUGINS) == 0
        assert (
            "Failed to load plugin plugin1: plugin class NotAPlugin is not a subclass of Plugin"
            in caplog.text
        )
        assert "Enabled plugins not found: ['plugin1']" in caplog.text

    @patch("dstack._internal.server.services.plugins.entry_points")
    @patch("dstack._internal.server.services.plugins.import_module")
    def test_clears_existing_plugins(self, mock_import_module, mock_entry_points):
        # Pre-populate _PLUGINS
        _PLUGINS.append(DummyPlugin1())

        mock_entry_points.return_value = [
            EntryPoint(
                name="plugin2",
                value="dummy.plugins:DummyPlugin2",
                group="dstack.plugins",
            )
        ]
        mock_module = MagicMock()
        mock_module.DummyPlugin2 = DummyPlugin2
        mock_import_module.return_value = mock_module

        load_plugins(["plugin2"])

        assert len(_PLUGINS) == 1  # Should only contain plugin2
        assert isinstance(_PLUGINS[0], DummyPlugin2)

    @patch("dstack._internal.server.services.plugins.entry_points")
    @patch("dstack._internal.server.services.plugins.import_module")
    def test_load_no_plugins_found(self, mock_import_module, mock_entry_points, caplog):
        mock_entry_points.return_value = []  # No entry points found

        with caplog.at_level(logging.INFO):
            load_plugins(["plugin1"])  # Try to enable one

        assert len(_PLUGINS) == 0
        mock_import_module.assert_not_called()
        assert "Enabled plugins not found: ['plugin1']" in caplog.text

    @patch("dstack._internal.server.services.plugins.entry_points")
    @patch("dstack._internal.server.services.plugins.import_module")
    def test_load_no_plugins_enabled(self, mock_import_module, mock_entry_points, caplog):
        mock_entry_points.return_value = [
            EntryPoint(
                name="plugin1",
                value="dummy.plugins:DummyPlugin1",
                group="dstack.plugins",
            )
        ]

        with caplog.at_level(logging.INFO):
            load_plugins([])  # Enable none

        assert len(_PLUGINS) == 0
        mock_import_module.assert_not_called()
        assert "Found not enabled plugin plugin1" in caplog.text
        assert (
            "Enabled plugins not found" not in caplog.text
        )  # Should not warn if none were enabled
