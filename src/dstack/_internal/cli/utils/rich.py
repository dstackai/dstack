import logging
from datetime import datetime
from types import TracebackType
from typing import TYPE_CHECKING, Callable, Iterable, List, Optional, Union

from rich.console import Group
from rich.live import Live
from rich.logging import RichHandler
from rich.spinner import Spinner
from rich.text import Text
from rich.traceback import Traceback

if TYPE_CHECKING:
    from rich.console import Console, ConsoleRenderable, RenderableType

FormatTimeCallable = Callable[[datetime], Text]


class DstackLogRender:
    _last_time: Optional[Text] = None

    def __call__(
        self,
        console: "Console",
        message_renderable: Iterable["ConsoleRenderable"],
        log_time: Optional[datetime] = None,
        time_format: Union[str, FormatTimeCallable] = "[%x %X]",
        level: Text = Text(),
    ) -> "ConsoleRenderable":
        from rich.table import Table

        output = Table.grid(padding=(0, 1))
        output.expand = True
        output.add_column(style="log.time")
        output.add_column(style="log.level", width=8)
        output.add_column(ratio=1, style="log.message", overflow="fold")
        row: List["RenderableType"] = []
        log_time = log_time or console.get_datetime()
        time_format = time_format
        if callable(time_format):
            log_time_display = time_format(log_time)
        else:
            log_time_display = Text(log_time.strftime(time_format))
        if log_time_display == self._last_time:
            row.append(Text(" " * len(log_time_display)))
        else:
            row.append(log_time_display)
            self._last_time = log_time_display
        row.append(level)
        row.extend(message_renderable)

        output.add_row(*row)
        return output


class DstackRichHandler(RichHandler):
    __log_render = DstackLogRender()

    def emit(self, record: logging.LogRecord) -> None:
        """Invoked by logging."""
        show_path = True
        if isinstance(record.args, dict):
            if "show_path" in record.args:
                show_path = record.args["show_path"]
        message = self.format(record)
        traceback = None
        if self.rich_tracebacks and record.exc_info and record.exc_info != (None, None, None):
            exc_type, exc_value, exc_traceback = record.exc_info
            assert exc_type is not None
            assert exc_value is not None
            traceback = Traceback.from_exception(
                exc_type,
                exc_value,
                exc_traceback,
                width=self.tracebacks_width,
                extra_lines=self.tracebacks_extra_lines,
                theme=self.tracebacks_theme,
                word_wrap=self.tracebacks_word_wrap,
                show_locals=self.tracebacks_show_locals,
                locals_max_length=self.locals_max_length,
                locals_max_string=self.locals_max_string,
                suppress=self.tracebacks_suppress,
            )
            message = record.getMessage()
            if self.formatter:
                record.message = record.getMessage()
                formatter = self.formatter
                if hasattr(formatter, "usesTime") and formatter.usesTime():
                    record.asctime = formatter.formatTime(record, formatter.datefmt)
                message = formatter.formatMessage(record)

        if show_path:
            message = self.prepend_path(message, record)
        setattr(record, "markup", True)
        message_renderable = self.render_message(record, message)
        level = self.get_level_text(record)
        time_format = None if self.formatter is None else self.formatter.datefmt
        log_time = datetime.fromtimestamp(record.created)

        log_renderable = self.__log_render(
            self.console,
            [message_renderable] if not traceback else [message_renderable, traceback],
            log_time=log_time,
            time_format=time_format,
            level=level,
        )

        try:
            self.console.print(log_renderable)
        except Exception:
            self.handleError(record)

    def prepend_path(self, message, record):
        path = ""
        if self.enable_link_path and record.pathname:
            path = path + f"[link=file://{record.pathname}"
            path = path + "]"
        path = path + record.name
        if self.enable_link_path and record.pathname:
            path = path + "[/link]"
        if record.lineno:
            if self.enable_link_path and record.pathname:
                path = path + f"[link=file://{record.pathname}#{record.lineno}]"
            path = path + f":{record.lineno}"
            if self.enable_link_path and record.pathname:
                path = path + "[/link]"
        message = f"[log.path]{path}[/] " + message
        return message


class MultiItemStatus:
    """An alternative to rich.status.Status that allows extra renderables below the spinner"""

    def __init__(self, status: "RenderableType", *, console: Optional["Console"] = None) -> None:
        self._spinner = Spinner("dots", text=status, style="status.spinner")
        self._live = Live(
            renderable=self._spinner,
            console=console,
            refresh_per_second=12.5,
            transient=True,
        )

    def update(self, *renderables: "RenderableType") -> None:
        self._live.update(renderable=Group(self._spinner, *renderables))

    def __enter__(self) -> "MultiItemStatus":
        self._live.start()
        return self

    def __exit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        self._live.stop()
