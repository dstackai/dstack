import pytest
from pydantic import ValidationError

from dstack._internal.cli.models.endpoints import (
    EndpointConfiguration,
    EndpointModelBase,
    EndpointModelRepo,
)

pytestmark = pytest.mark.windows


class TestEndpointConfiguration:
    def test_schema_documents_supported_input(self):
        assert all(
            field.field_info.description for field in EndpointConfiguration.__fields__.values()
        )
        assert all(field.field_info.description for field in EndpointModelBase.__fields__.values())
        assert all(field.field_info.description for field in EndpointModelRepo.__fields__.values())
        assert {"type": "string"} in EndpointConfiguration.schema()["properties"]["model"]["anyOf"]

    def test_parses_string_as_exact_repo(self):
        configuration = EndpointConfiguration(model="Qwen/Qwen3.5-27B")

        assert isinstance(configuration.model, EndpointModelRepo)
        assert configuration.model.exact_repo == "Qwen/Qwen3.5-27B"
        assert configuration.model.api_model_name == "Qwen/Qwen3.5-27B"
        assert not configuration.model.allows_variant_selection

    def test_parses_base_model(self):
        configuration = EndpointConfiguration(model={"base": "Qwen/Qwen3.5-27B"})

        assert isinstance(configuration.model, EndpointModelBase)
        assert configuration.model.exact_repo is None
        assert configuration.model.api_model_name == "Qwen/Qwen3.5-27B"
        assert configuration.model.allows_variant_selection

    def test_parses_exact_repo_with_client_facing_name(self):
        configuration = EndpointConfiguration(
            model={
                "repo": "community/Qwen3.5-27B-GPTQ-Int4",
                "name": "Qwen/Qwen3.5-27B",
            }
        )

        assert configuration.model.exact_repo == "community/Qwen3.5-27B-GPTQ-Int4"
        assert configuration.model.api_model_name == "Qwen/Qwen3.5-27B"

    def test_rejects_ambiguous_model_object(self):
        with pytest.raises(ValidationError):
            EndpointConfiguration(model={"base": "Qwen/base", "repo": "Qwen/repo"})
