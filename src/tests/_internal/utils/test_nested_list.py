from textwrap import dedent

import pytest

from dstack._internal.utils.nested_list import NestedList, NestedListItem


def test_render_flat_list():
    nested = NestedList(
        children=[NestedListItem("Item 1"), NestedListItem("Item 2"), NestedListItem("Item 3")]
    )
    expected = "- Item 1\n- Item 2\n- Item 3\n"
    assert nested.render() == expected


def test_render_nested_list():
    nested = NestedList(
        children=[
            NestedListItem("Item 1"),
            NestedListItem(
                "Item 2",
                [
                    NestedListItem("Item 2.1"),
                    NestedListItem("Item 2.2", [NestedListItem("Item 2.2.1")]),
                ],
            ),
            NestedListItem("Item 3"),
        ]
    )
    expected = dedent(
        """
        - Item 1
        - Item 2
          - Item 2.1
          - Item 2.2
            - Item 2.2.1
        - Item 3
        """
    ).lstrip()
    assert nested.render() == expected


def test_render_empty_list():
    nested = NestedList()
    assert nested.render() == ""


def test_cycle_detection():
    a = NestedListItem("A")
    b = NestedListItem("B", [a])
    a.children.append(b)  # Introduce a cycle: A → B → A

    nested = NestedList(children=[a])

    with pytest.raises(ValueError, match="Cycle detected at item: A"):
        nested.render()
