from typing import Literal, Optional

from dstack._internal.server.services.ides.base import IDE
from dstack._internal.server.services.ides.cursor import CursorDesktop
from dstack._internal.server.services.ides.vscode import VSCodeDesktop
from dstack._internal.server.services.ides.windsurf import WindsurfDesktop

_IDELiteral = Literal["vscode", "cursor", "windsurf"]

_ide_literal_to_ide_class_map: dict[_IDELiteral, type[IDE]] = {
    "vscode": VSCodeDesktop,
    "cursor": CursorDesktop,
    "windsurf": WindsurfDesktop,
}


def get_ide(ide_literal: _IDELiteral) -> Optional[IDE]:
    ide_class = _ide_literal_to_ide_class_map.get(ide_literal)
    if ide_class is None:
        return None
    return ide_class()
