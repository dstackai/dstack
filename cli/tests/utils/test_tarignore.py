from dstack.core.repo.local import TarIgnore


def test_plain_text():
    assert TarIgnore.fnmatch("foo.txt", pattern="foo.txt")
    assert TarIgnore.fnmatch("foo/bar", pattern="foo/bar")
    assert not TarIgnore.fnmatch("foo", pattern="bar")


def test_relative():
    assert TarIgnore.fnmatch("bar/foo", pattern="foo")
    assert not TarIgnore.fnmatch("foo", pattern="bar/foo")


def test_absolute():
    assert TarIgnore.fnmatch("foo", pattern="/foo")
    assert not TarIgnore.fnmatch("bar/foo", pattern="/foo")


def test_glob():
    assert TarIgnore.fnmatch("foo", pattern="f*")
    assert not TarIgnore.fnmatch("fo/o", pattern="f*")
    assert TarIgnore.fnmatch("fo/o", pattern="f*/*")
