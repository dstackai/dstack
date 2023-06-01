from dstack._internal.utils.ignore import GitIgnore


def test_plain_text():
    assert GitIgnore.fnmatch("foo.txt", pattern="foo.txt")
    assert GitIgnore.fnmatch("foo/bar", pattern="foo/bar")
    assert not GitIgnore.fnmatch("foo", pattern="bar")


def test_relative():
    assert GitIgnore.fnmatch("bar/foo", pattern="foo")
    assert not GitIgnore.fnmatch("foo", pattern="bar/foo")


def test_absolute():
    assert GitIgnore.fnmatch("foo", pattern="/foo")
    assert not GitIgnore.fnmatch("bar/foo", pattern="/foo")


def test_glob():
    assert GitIgnore.fnmatch("foo", pattern="f*")
    assert not GitIgnore.fnmatch("fo/o", pattern="f*")
    assert GitIgnore.fnmatch("fo/o", pattern="f*/*")
