import pytest

from dstack._internal.core.models.common import EntityReference


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
