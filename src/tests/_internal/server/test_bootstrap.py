import logging
import os
import sys

import pytest

from dstack._internal.server import bootstrap


class TestSetUpProcess:
    @pytest.fixture(autouse=True)
    def isolate_process_state(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(bootstrap, "_is_process_set_up", False)
        monkeypatch.delenv("GRPC_ENABLE_FORK_SUPPORT", raising=False)
        monkeypatch.delenv("GRPC_VERBOSITY", raising=False)
        monkeypatch.delitem(sys.modules, "grpc", raising=False)

    def test_sets_grpc_defaults(self):
        bootstrap.set_up_process()
        assert os.environ["GRPC_ENABLE_FORK_SUPPORT"] == "false"
        assert os.environ["GRPC_VERBOSITY"] == "ERROR"
        assert bootstrap.is_process_set_up()

    def test_keeps_grpc_settings_from_environment(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("GRPC_ENABLE_FORK_SUPPORT", "true")
        monkeypatch.setenv("GRPC_VERBOSITY", "DEBUG")
        bootstrap.set_up_process()
        assert os.environ["GRPC_ENABLE_FORK_SUPPORT"] == "true"
        assert os.environ["GRPC_VERBOSITY"] == "DEBUG"

    def test_warns_if_grpc_already_imported(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ):
        monkeypatch.setitem(sys.modules, "grpc", object())
        with caplog.at_level(logging.WARNING, logger=bootstrap.__name__):
            bootstrap.set_up_process()
        assert "grpc was imported before bootstrap.set_up_process()" in caplog.text
        assert bootstrap.is_process_set_up()

    def test_no_warning_if_grpc_already_imported_with_setting_from_environment(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ):
        monkeypatch.setitem(sys.modules, "grpc", object())
        monkeypatch.setenv("GRPC_ENABLE_FORK_SUPPORT", "false")
        with caplog.at_level(logging.WARNING, logger=bootstrap.__name__):
            bootstrap.set_up_process()
        assert caplog.text == ""
