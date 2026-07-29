import json

from dstack._internal.core.models.configurations import DstackConfiguration, ServiceConfiguration
from dstack._internal.core.models.profiles import ProfilesConfig
from dstack._internal.utils.json_schema import add_extra_schema_types


class TestAddExtraSchemaTypes:
    def test_ref_becomes_any_of(self):
        prop = {"$ref": "#/definitions/Foo"}
        add_extra_schema_types(prop, extra_types=[{"type": "string"}])
        assert prop == {"anyOf": [{"$ref": "#/definitions/Foo"}, {"type": "string"}]}

    def test_all_of_keeps_first_ref_only(self):
        prop = {"allOf": [{"$ref": "#/definitions/Foo"}]}
        add_extra_schema_types(prop, extra_types=[{"type": "integer"}])
        assert prop == {"anyOf": [{"$ref": "#/definitions/Foo"}, {"type": "integer"}]}

    def test_any_of_is_extended_in_place(self):
        prop = {"anyOf": [{"type": "integer"}]}
        add_extra_schema_types(prop, extra_types=[{"type": "string"}])
        assert prop == {"anyOf": [{"type": "integer"}, {"type": "string"}]}

    def test_type_is_wrapped(self):
        prop = {"type": "integer"}
        add_extra_schema_types(prop, extra_types=[{"type": "string"}])
        assert prop == {"anyOf": [{"type": "integer"}, {"type": "string"}]}

    def test_other_keys_are_preserved(self):
        prop = {"title": "Model", "description": "d", "$ref": "#/definitions/Foo"}
        add_extra_schema_types(prop, extra_types=[{"type": "string"}])
        assert prop["title"] == "Model"
        assert prop["description"] == "d"

    def test_discriminated_one_of_stays_grouped_with_its_discriminator(self):
        # A `Field(discriminator=...)` union renders as `oneOf` plus a sibling `discriminator`.
        # The two must move into the same `anyOf` member: a `discriminator` only applies to a
        # keyword whose every member carries the tag, so flattening the extra types in beside
        # the refs would produce an invalid schema.
        prop = {
            "title": "Model",
            "oneOf": [{"$ref": "#/definitions/Foo"}, {"$ref": "#/definitions/Bar"}],
            "discriminator": {"propertyName": "format", "mapping": {}},
        }
        add_extra_schema_types(prop, extra_types=[{"type": "string"}])
        assert prop == {
            "title": "Model",
            "anyOf": [
                {
                    "oneOf": [{"$ref": "#/definitions/Foo"}, {"$ref": "#/definitions/Bar"}],
                    "discriminator": {"propertyName": "format", "mapping": {}},
                },
                {"type": "string"},
            ],
        }

    def test_one_of_without_discriminator(self):
        prop = {"oneOf": [{"$ref": "#/definitions/Foo"}]}
        add_extra_schema_types(prop, extra_types=[{"type": "string"}])
        assert prop == {"anyOf": [{"oneOf": [{"$ref": "#/definitions/Foo"}]}, {"type": "string"}]}


class TestSchemaGeneration:
    """
    Guards the schemas CI generates and the docs build consumes. Nothing else in the suite
    exercises `schema_json()`, so a `schema_extra` hook that cannot handle the shape pydantic
    emits for a field fails only in CI.
    """

    def test_dstack_configuration_schema_is_generated(self):
        assert json.loads(DstackConfiguration.schema_json())["definitions"]

    def test_profiles_config_schema_is_generated(self):
        assert json.loads(ProfilesConfig.schema_json())["definitions"]

    def test_service_model_accepts_both_the_shorthand_and_the_tagged_forms(self):
        prop = json.loads(ServiceConfiguration.schema_json())["properties"]["model"]
        tagged, shorthand = prop["anyOf"]
        assert shorthand == {"type": "string"}
        assert tagged["discriminator"]["propertyName"] == "format"
        assert tagged["oneOf"]
