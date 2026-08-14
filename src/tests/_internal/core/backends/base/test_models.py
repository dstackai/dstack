from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from dstack._internal.core.backends.gcp.models import GCPServiceAccountFileCreds
from dstack._internal.core.backends.kubernetes.models import KubeconfigFileConfig
from dstack._internal.core.backends.slurm.models import SlurmPrivateKeyFileConfig


class TestFillData:
    def test_reads_data_from_file(self, tmp_path: Path):
        creds_file = tmp_path / "creds.json"
        creds_file.write_text("file-contents")

        creds = GCPServiceAccountFileCreds.model_validate({"filename": str(creds_file)})

        assert creds.data == "file-contents"

    def test_keeps_data_and_does_not_read_the_file(self, tmp_path: Path):
        creds = GCPServiceAccountFileCreds.model_validate(
            {"filename": str(tmp_path / "missing"), "data": "explicit-contents"}
        )

        assert creds.data == "explicit-contents"

    def test_missing_file_rejected(self, tmp_path: Path):
        with pytest.raises(ValidationError, match="No such file"):
            GCPServiceAccountFileCreds.model_validate({"filename": str(tmp_path / "missing")})

    @pytest.mark.parametrize(
        "filename",
        [
            pytest.param({"a": 1}, id="dict"),
            pytest.param(["/tmp/x"], id="list"),
            pytest.param(True, id="bool"),
        ],
    )
    def test_malformed_filename_reported_as_validation_error(self, filename: Any):
        # A `before` validator would hand these straight to `open()`, raising `TypeError`.
        with pytest.raises(ValidationError):
            GCPServiceAccountFileCreds.model_validate({"filename": filename})

    @pytest.mark.parametrize(
        "obj",
        [
            pytest.param("just-a-string", id="str"),
            pytest.param(["filename", "/tmp/x"], id="list"),
            pytest.param(12, id="int"),
        ],
    )
    def test_non_dict_input_reported_as_validation_error(self, obj: Any):
        # A `before` validator would call `.get()` on these, raising `AttributeError`.
        with pytest.raises(ValidationError):
            GCPServiceAccountFileCreds.model_validate(obj)

    @pytest.mark.parametrize(
        ["model", "message"],
        [
            pytest.param(
                GCPServiceAccountFileCreds, "Either `filename` or `data`", id="gcp-empty-filename"
            ),
            pytest.param(
                KubeconfigFileConfig, "Either `filename` or `data`", id="kubernetes-empty-filename"
            ),
        ],
    )
    def test_empty_filename_without_data_rejected(self, model: type, message: str):
        with pytest.raises(ValidationError, match=message):
            model.model_validate({"filename": ""})

    def test_custom_field_names(self, tmp_path: Path):
        key_file = tmp_path / "key"
        key_file.write_text("private-key")

        config = SlurmPrivateKeyFileConfig.model_validate({"path": str(key_file)})

        assert config.content == "private-key"

    def test_unset_path_without_content_rejected(self):
        with pytest.raises(ValidationError, match="Either `path` or `content`"):
            SlurmPrivateKeyFileConfig.model_validate({})
