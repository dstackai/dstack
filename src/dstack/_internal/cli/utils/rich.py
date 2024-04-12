import logging
from datetime import datetime
from typing import TYPE_CHECKING, Callable, Iterable, List, Optional, Union

from rich.logging import RichHandler
from rich.text import Text, TextType
from rich.traceback import Traceback

if TYPE_CHECKING:
    from rich.console import Console, ConsoleRenderable, RenderableType
    from rich.table import Table

FormatTimeCallable = Callable[[datetime], Text]


class LogRender:
    def __init__(
        self,
        show_time: bool = True,
        show_level: bool = True,
        show_path: bool = True,
        time_format: Union[str, FormatTimeCallable] = "[%x %X]",
        omit_repeated_times: bool = True,
        level_width: Optional[int] = 8,
    ) -> None:
        self.show_time = show_time
        self.show_level = show_level
        self.show_path = show_path
        self.time_format = time_format
        self.omit_repeated_times = omit_repeated_times
        self.level_width = level_width
        self._last_time: Optional[Text] = None

    def __call__(
        self,
        console: "Console",
        message_renderable: Iterable["ConsoleRenderable"],
        log_time: Optional[datetime] = None,
        time_format: Optional[Union[str, FormatTimeCallable]] = None,
        level: TextType = "",
        path: Optional[str] = None,
        line_no: Optional[int] = None,
        link_path: Optional[str] = None,
    ) -> "Table":
        from rich.containers import Renderables
        from rich.table import Table

        output = Table.grid(padding=(0, 1))
        output.expand = True
        if self.show_time:
            output.add_column(style="log.time")
        if self.show_level:
            output.add_column(style="log.level", width=self.level_width)
        output.add_column(ratio=1, overflow="ignore")
        row: List["RenderableType"] = []
        if self.show_time:
            log_time = log_time or console.get_datetime()
            time_format = time_format or self.time_format
            if callable(time_format):
                log_time_display = time_format(log_time)
            else:
                log_time_display = Text(log_time.strftime(time_format))
            if log_time_display == self._last_time and self.omit_repeated_times:
                row.append(Text(" " * len(log_time_display)))
            else:
                row.append(log_time_display)
                self._last_time = log_time_display
        if self.show_level:
            row.append(level)

        merged_message_renderable = []
        if self.show_path and path:
            path_text = Text(style="log.path", end=" ")
            path_text.append(path, style=f"link file://{link_path}" if link_path else "")
            if line_no:
                path_text.append(":")
                path_text.append(
                    f"{line_no}",
                    style=f"link file://{link_path}#{line_no}" if link_path else "",
                )
            merged_message_renderable.append(path_text)
        merged_message_renderable.extend(message_renderable)
        row.append(Renderables(merged_message_renderable))

        output.add_row(*row)
        return output


class DstackRichHandler(RichHandler):
    __log_render: Optional[LogRender] = None

    def render(
        self,
        *,
        record: logging.LogRecord,
        traceback: Optional[Traceback],
        message_renderable: "ConsoleRenderable",
    ) -> "ConsoleRenderable":
        self._lazy_init_render()
        path = record.name  # the key difference from RichHandler
        level = self.get_level_text(record)
        time_format = None if self.formatter is None else self.formatter.datefmt
        log_time = datetime.fromtimestamp(record.created)

        log_renderable = self.__log_render(
            self.console,
            [message_renderable] if not traceback else [message_renderable, traceback],
            log_time=log_time,
            time_format=time_format,
            level=level,
            path=path,
            line_no=record.lineno,
            link_path=record.pathname if self.enable_link_path else None,
        )
        return log_renderable

    def _lazy_init_render(self):
        if self.__log_render is None:
            self.__log_render = LogRender()
