import logging
from datetime import datetime
from typing import TYPE_CHECKING, Callable, Iterable, List, Optional, Union

from rich.logging import RichHandler
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
        path: Optional[str] = None,
        line_no: Optional[int] = None,
        link_path: Optional[str] = None,
    ) -> "ConsoleRenderable":
        from rich.containers import Renderables

        row: List["RenderableType"] = []
        log_time = log_time or console.get_datetime()
        time_format = time_format
        if callable(time_format):
            log_time_display = time_format(log_time)
        else:
            log_time_display = Text(log_time.strftime(time_format), end=" ", style="log.time")
        if log_time_display == self._last_time:
            row.append(Text(" " * len(log_time_display)))
        else:
            row.append(log_time_display)
            self._last_time = log_time_display
        level.end = " " * (9 - len(level))
        level.style = "log.level"
        row.append(level)

        path_text = Text(style="log.path", overflow="fold", end=" ")
        path_text.append(path, style=f"link file://{link_path}" if link_path else "")
        if line_no:
            path_text.append(":")
            path_text.append(
                f"{line_no}",
                style=f"link file://{link_path}#{line_no}" if link_path else "",
            )
        row.append(path_text)
        row.extend(message_renderable)

        return Renderables(row)


class DstackRichHandler(RichHandler):
    __log_render = DstackLogRender()

    def emit(self, record: logging.LogRecord) -> None:
        """Invoked by logging."""
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

        message_renderable = self.render_message(record, message)
        path = record.name
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

        try:
            self.console.print(log_renderable, soft_wrap=True)
        except Exception:
            self.handleError(record)
