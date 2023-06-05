from dstack._internal.utils.escape import Escaper

esc = Escaper({"/": "."}, escape_char="$")


def test_plain():
    s = "foobar"
    escaped = esc.escape(s)
    assert escaped == s
    assert esc.unescape(escaped) == s


def test_escape_char_only():
    s = "foo$bar"
    escaped = esc.escape(s)
    assert escaped == "foo$$bar"
    assert esc.unescape(escaped) == s


def test_single_escape():
    s = "foo/bar"
    escaped = esc.escape(s)
    assert escaped == "foo$.bar"
    assert esc.unescape(escaped) == s


def test_double_escape():
    s = "foo$/bar"
    escaped = esc.escape(s)
    assert escaped == "foo$$$.bar"
    assert esc.unescape(escaped) == s
