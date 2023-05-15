from dstack.utils.common import merge_workflow_data


def test_none_override():
    data = {"foo": "aaa", "bar": None, "buzz": 1.2}
    r = merge_workflow_data(data, None)
    assert r == data


def test_join():
    r = merge_workflow_data({"foo": "aaa"}, {"bar": 1.2})
    assert r == {"foo": "aaa", "bar": 1.2}


def test_plain_override():
    r = merge_workflow_data({"foo": "aaa", "bar": 123456}, {"bar": 1.2})
    assert r == {"foo": "aaa", "bar": 1.2}


def test_deep_override():
    r = merge_workflow_data(
        {"foo": "aaa", "gpu": {"name": "V100", "count": 1}}, {"gpu": {"name": "A100"}}
    )
    assert r == {"foo": "aaa", "gpu": {"name": "A100", "count": 1}}


def test_no_mutations():
    data = {"foo": {"bar": "123"}}
    override = {"buzz": 123, "foo": {"addon": True}}
    r = merge_workflow_data(data, override)
    assert r == {"foo": {"bar": "123", "addon": True}, "buzz": 123}
    r["buzz"] = 567
    r["foo"]["bar"] = None
    assert data == {"foo": {"bar": "123"}}
    assert override == {"buzz": 123, "foo": {"addon": True}}
