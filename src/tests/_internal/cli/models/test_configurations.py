import pytest
from pydantic import ValidationError

from dstack._internal.cli.models.configurations import (
    PresetConfiguration,
    PresetModelBase,
    PresetModelRepo,
)

pytestmark = pytest.mark.windows


class TestPresetConfiguration:
    def test_schema_documents_supported_input(self):
        assert all(
            field.field_info.description for field in PresetConfiguration.__fields__.values()
        )
        assert all(field.field_info.description for field in PresetModelBase.__fields__.values())
        assert all(field.field_info.description for field in PresetModelRepo.__fields__.values())
        assert {"type": "string"} in PresetConfiguration.schema()["properties"]["model"]["anyOf"]

    def test_parses_string_as_exact_repo(self):
        configuration = PresetConfiguration(model="Qwen/Qwen3.5-27B")

        assert isinstance(configuration.model, PresetModelRepo)
        assert configuration.model.exact_repo == "Qwen/Qwen3.5-27B"
        assert configuration.model.api_model_name == "Qwen/Qwen3.5-27B"
        assert not configuration.model.allows_variant_selection

    def test_parses_base_model(self):
        configuration = PresetConfiguration(model={"base": "Qwen/Qwen3.5-27B"})

        assert isinstance(configuration.model, PresetModelBase)
        assert configuration.model.exact_repo is None
        assert configuration.model.api_model_name == "Qwen/Qwen3.5-27B"
        assert configuration.model.allows_variant_selection

    def test_parses_exact_repo_with_client_facing_name(self):
        configuration = PresetConfiguration(
            model={
                "repo": "community/Qwen3.5-27B-GPTQ-Int4",
                "name": "Qwen/Qwen3.5-27B",
            }
        )

        assert configuration.model.exact_repo == "community/Qwen3.5-27B-GPTQ-Int4"
        assert configuration.model.api_model_name == "Qwen/Qwen3.5-27B"

    def test_rejects_ambiguous_model_object(self):
        with pytest.raises(ValidationError):
            PresetConfiguration(model={"base": "Qwen/base", "repo": "Qwen/repo"})

    def test_parses_top_level_base_shorthand(self):
        configuration = PresetConfiguration(base="Qwen/Qwen3.5-27B")

        assert isinstance(configuration.model, PresetModelBase)
        assert configuration.model.api_model_name == "Qwen/Qwen3.5-27B"
        assert configuration.base is None

    def test_parses_top_level_repo_shorthand(self):
        configuration = PresetConfiguration(repo="community/Qwen3.5-27B-GPTQ-Int4")

        assert isinstance(configuration.model, PresetModelRepo)
        assert configuration.model.exact_repo == "community/Qwen3.5-27B-GPTQ-Int4"
        assert configuration.repo is None

    def test_shorthand_round_trips_through_dict(self):
        configuration = PresetConfiguration(base="Qwen/Qwen3.5-27B")

        round_tripped = PresetConfiguration.parse_obj(configuration.dict())

        assert round_tripped.model == configuration.model

    def test_rejects_combined_base_and_repo_shorthand(self):
        with pytest.raises(ValidationError):
            PresetConfiguration(base="Qwen/base", repo="Qwen/repo")

    def test_rejects_shorthand_combined_with_model(self):
        with pytest.raises(ValidationError):
            PresetConfiguration(base="Qwen/base", model={"repo": "Qwen/repo"})

    def test_requires_model(self):
        with pytest.raises(ValidationError):
            PresetConfiguration()
