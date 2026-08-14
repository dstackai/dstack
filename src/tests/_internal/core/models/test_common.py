import pytest

from dstack._internal.core.models.common import EntityReference, pop_null_field


class TestEntityReferenceParse:
    @pytest.mark.parametrize(
        "value, expected",
        [
            ("fleet", EntityReference(project=None, name="fleet")),
            ("project/fleet", EntityReference(project="project", name="fleet")),
            (
                EntityReference(project="proj", name="fleet"),
                EntityReference(project="proj", name="fleet"),
            ),
        ],
    )
    def test_valid(self, value, expected):
        assert EntityReference.parse(value) == expected

    @pytest.mark.parametrize(
        "value",
        ["", "/name", "name/", "/", "a/b/c"],
    )
    def test_invalid(self, value: str):
        with pytest.raises(ValueError, match="Invalid entity reference"):
            EntityReference.parse(value)


class TestPopNullField:
    def test_drops_null_field_at_top_level(self):
        values = {"router": None, "backend": "aws"}
        assert pop_null_field(values, "router") == {"backend": "aws"}

    def test_drops_null_field_in_nested_dict(self):
        values = {"spec": {"configuration": {"router": None, "backend": "aws"}}}
        assert pop_null_field(values, "spec", "configuration", "router") == {
            "spec": {"configuration": {"backend": "aws"}}
        }

    def test_leaves_non_null_field_untouched(self):
        values = {"configuration": {"router": "some-router"}}
        assert pop_null_field(values, "configuration", "router") == {
            "configuration": {"router": "some-router"}
        }

    def test_field_absent(self):
        values = {"configuration": {"backend": "aws"}}
        assert pop_null_field(values, "configuration", "router") == {
            "configuration": {"backend": "aws"}
        }

    def test_intermediate_path_missing(self):
        values = {"backend": "aws"}
        assert pop_null_field(values, "configuration", "router") == {"backend": "aws"}

    def test_intermediate_path_not_a_dict(self):
        values = {"configuration": None}
        assert pop_null_field(values, "configuration", "router") == {"configuration": None}

    def test_top_level_not_a_dict(self):
        values = "not-a-dict"
        assert pop_null_field(values, "configuration", "router") == "not-a-dict"
