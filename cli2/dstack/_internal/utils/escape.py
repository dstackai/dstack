from typing import Dict


class UnescapeError(Exception):
    pass


class Escaper:
    """
    Generic escaping for strings.

    `escape_char` is doubled
    Key from `chars` is replaced with `escape_char` and corresponding value

    >>> esc = Escaper({"/": "."}, escape_char="$")
    >>> esc.escape("foo/bar")
    'foo$.bar'
    >>> esc.escape("foo/$bar")
    'foo$.$$bar'
    >>> esc.unescape("foo$/bar")
    Traceback (most recent call last):
    escape.UnescapeError: ('Unknown escape sequence', '$/')
    """

    def __init__(self, chars: Dict[str, str], escape_char: str):
        assert escape_char not in chars.keys()
        assert escape_char not in chars.values()
        assert len(chars) == len(set(chars.values()))
        self.chars = chars
        self.escape_char = escape_char

    def escape(self, value: str) -> str:
        output = value.replace(self.escape_char, 2 * self.escape_char)
        for k, v in self.chars.items():
            output = output.replace(k, f"{self.escape_char}{v}")
        return output

    def unescape(self, value: str) -> str:
        inv = {v: k for k, v in self.chars.items()}
        inv[self.escape_char] = self.escape_char
        parts = []
        start = 0
        while start < len(value):
            esc = value.find(self.escape_char, start)
            if esc == -1:
                parts.append(value[start:])
                break
            parts.append(value[start:esc])
            if esc + 1 >= len(value):
                raise UnescapeError("Unexpected EOL")
            elif value[esc + 1] not in inv:
                raise UnescapeError(f"Unknown escape sequence", value[esc : esc + 2])
            else:
                parts.append(inv[value[esc + 1]])
            start = esc + 2
        return "".join(parts)


_head_escaper = Escaper(chars={"/": "."}, escape_char="~")


def escape_head(v: str) -> str:
    return _head_escaper.escape(v)


def unescape_head(v: str) -> str:
    return _head_escaper.unescape(v)
