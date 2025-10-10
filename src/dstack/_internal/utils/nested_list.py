from dataclasses import dataclass, field
from typing import Optional


@dataclass
class NestedListItem:
    label: str
    children: list["NestedListItem"] = field(default_factory=list)

    def render(self, indent: int = 0, visited: Optional[set[int]] = None) -> str:
        if visited is None:
            visited = set()

        item_id = id(self)
        if item_id in visited:
            raise ValueError(f"Cycle detected at item: {self.label}")

        visited.add(item_id)
        prefix = "  " * indent + "- "
        output = f"{prefix}{self.label}\n"
        for child in self.children:
            # `visited.copy()` so that we only detect cycles within each path,
            # rather than duplicate items in unrelated paths
            output += child.render(indent + 1, visited.copy())
        return output


@dataclass
class NestedList:
    """
    A nested list that can be rendered in Markdown-like format:

    - Item 1
    - Item 2
      - Item 2.1
      - Item 2.2
        - Item 2.2.1
    - Item 3
    """

    children: list[NestedListItem] = field(default_factory=list)

    def render(self) -> str:
        output = ""
        for child in self.children:
            output += child.render()
        return output
