import unittest
from dataclasses import dataclass
from typing import List

from dstack.backend.base.logs import fix_urls
from dstack.core.job import AppSpec

localhost = "127.0.0.1"


@dataclass
class JobMock:
    host_name: str
    app_specs: List[AppSpec]


class TestFixUrls(unittest.TestCase):
    def test_empty_mapping(self):
        log = b"http://0.0.0.0:3001/qwerty"
        expected = b"http://127.0.0.1:3001/qwerty"
        job = JobMock("host.name", [AppSpec(port=3001, app_name="qwerty")])
        self.assertEqual(expected, fix_urls(log, job, {}, hostname=localhost))

    def test_default_hostname(self):
        log = b"http://0.0.0.0:3001/qwerty"
        expected = b"http://host.name:3001/qwerty"
        job = JobMock("host.name", [AppSpec(port=3001, app_name="qwerty")])
        self.assertEqual(expected, fix_urls(log, job, {}))

    def test_unique_mapping(self):
        log = b"http://0.0.0.0:3001/qwerty"
        expected = b"http://127.0.0.1:5501/qwerty"
        job = JobMock("host.name", [AppSpec(port=3001, app_name="qwerty")])
        self.assertEqual(
            expected, fix_urls(log, job, {4000: 5000, 3001: 5501}, hostname=localhost)
        )

    def test_with_query_params(self):
        log = b"http://0.0.0.0:3001/qwerty"
        expected = b"http://127.0.0.1:5501/qwerty?q=foobar"
        job = JobMock(
            "host.name",
            [AppSpec(port=3001, app_name="qwerty", url_query_params={"q": "foobar"})],
        )
        self.assertEqual(
            expected, fix_urls(log, job, {4000: 5000, 3001: 5501}, hostname=localhost)
        )

    def test_same_url(self):
        log = b"http://0.0.0.0:3001/qwerty and http://0.0.0.0:3001/foobar"
        expected = b"http://127.0.0.1:5501/qwerty and http://127.0.0.1:5501/foobar"
        job = JobMock("host.name", [AppSpec(port=3001, app_name="qwerty")])
        self.assertEqual(
            expected, fix_urls(log, job, {4000: 5000, 3001: 5501}, hostname=localhost)
        )

    def test_different_urls(self):
        log = b"http://0.0.0.0:3001/qwerty and http://0.0.0.0:3002/foobar"
        expected = b"http://127.0.0.1:5501/qwerty and http://127.0.0.1:5502/foobar"
        job = JobMock(
            "host.name",
            [AppSpec(port=3001, app_name="qwerty"), AppSpec(port=3002, app_name="foobar")],
        )
        self.assertEqual(
            expected, fix_urls(log, job, {4000: 5000, 3001: 5501, 3002: 5502}, hostname=localhost)
        )

    def test_circular_mapping(self):
        log = b"http://0.0.0.0:3001/qwerty and http://0.0.0.0:3002/foobar and http://0.0.0.0:3003/asdasd"
        expected = b"http://127.0.0.1:3002/qwerty and http://127.0.0.1:3003/foobar and http://127.0.0.1:3001/asdasd"
        job = JobMock(
            "host.name",
            [
                AppSpec(port=3001, app_name="qwerty"),
                AppSpec(port=3002, app_name="foobar"),
                AppSpec(port=3003, app_name="asdasd"),
            ],
        )
        self.assertEqual(
            expected,
            fix_urls(
                log, job, {4000: 5000, 3001: 3002, 3002: 3003, 3003: 3001}, hostname=localhost
            ),
        )

    def test_fastapi(self):
        log = b"\x1b[32mINFO\x1b[0m:     Uvicorn running on \x1b[1mhttp://0.0.0.0:3615\x1b[0m (Press CTRL+C to quit)"
        expected = b"\x1b[32mINFO\x1b[0m:     Uvicorn running on \x1b[1mhttp://127.0.0.1:53615\x1b[0m (Press CTRL+C to quit)"
        job = JobMock("0.0.0.0", [AppSpec(port=3615, app_name="fastapi")])
        self.assertEqual(expected, fix_urls(log, job, {3615: 53615}, hostname=localhost))
