from importlib.util import find_spec
from typing import List, Optional

from rich import print
from rich.prompt import Prompt

_is_termios_available = find_spec("termios") is not None


def ask_choice(
    title: str,
    labels: List[str],
    values: List[str],
    selected_value: Optional[str],
    show_choices: Optional[bool] = None,
) -> str:
    if selected_value not in values:
        selected_value = None
    if _is_termios_available:
        from simple_term_menu import TerminalMenu

        print(
            f"[sea_green3 bold]?[/sea_green3 bold] [bold]{title}[/bold] "
            "[gray46]Use arrows to move, type to filter[/gray46]"
        )
        try:
            cursor_index = values.index(selected_value) if selected_value else None
        except ValueError:
            cursor_index = None
        terminal_menu = TerminalMenu(
            menu_entries=labels,
            menu_cursor_style=["fg_red", "bold"],
            menu_highlight_style=["fg_red", "bold"],
            search_key=None,
            search_highlight_style=["fg_purple"],
            cursor_index=cursor_index,
        )
        chosen_menu_index = terminal_menu.show()
        chosen_menu_label = labels[chosen_menu_index].replace("[", "\\[")
        print(f"[sea_green3 bold]✓[/sea_green3 bold] [grey74]{chosen_menu_label}[/grey74]")
        return values[chosen_menu_index]
    else:
        if len(values) < 6 and show_choices is None or show_choices is True:
            return Prompt.ask(
                prompt=f"[sea_green3 bold]?[/sea_green3 bold] [bold]{title}[/bold]",
                choices=values,
                default=selected_value,
            )
        else:
            value = Prompt.ask(
                prompt=f"[sea_green3 bold]?[/sea_green3 bold] [bold]{title}[/bold]",
                default=selected_value,
            )
            if value in values:
                return value
            else:
                print(
                    f"[red]Please select one of the available options: \\[{', '.join(values)}][/red]"
                )
                return ask_choice(title, labels, values, selected_value, show_choices)
