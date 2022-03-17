import json
import tempfile
from datetime import datetime
from pathlib import Path
from unittest import TestCase

import dstack.logger as log
from dstack.config import YamlConfig, configure


class TestLogger(TestCase):
    def test_simple_log(self):
        my_logger = log.InMemoryLogger()
        log.enable(logger=my_logger)
        self.assertTrue(log.debug(data={"test": 123}, url="api/test"))
        self.assertTrue(log.debug(data="hello", x=10, y=20))
        lines = my_logger.io.getvalue().splitlines()
        self.assertEqual(2, len(lines))
        d = json.loads(lines[0])
        self.assertTrue("time" in d)
        self.assertEqual(123, d["data"]["test"])
        self.assertEqual("api/test", d["url"])
        d = json.loads(lines[1])
        self.assertTrue("time" in d)
        self.assertEqual(10, d["x"])
        self.assertEqual(20, d["y"])
        log.disable()
        self.assertFalse(log.debug(test="test"))

    def test_log_to_file(self):
        file = Path(tempfile.gettempdir()) / "dstack.log"
        my_logger = log.FileLogger(str(file.resolve()))
        log.enable(logger=my_logger)
        log.debug(message="test message")
        log.debug(message="second message")
        with open(file.resolve(), "r") as f:
            lines = f.readlines()
        d0 = json.loads(lines[0])
        d1 = json.loads(lines[1])
        self.assertEqual("test message", d0["message"])
        self.assertEqual("second message", d1["message"])

    def test_none(self):
        my_logger = log.InMemoryLogger()
        log.enable(logger=my_logger)
        log.debug(data=None, extra=None)

    def test_default_log_file_location(self):
        dstack_path = Path(tempfile.gettempdir()) / ".dstack"
        config_path = dstack_path / "config.yaml"
        config = YamlConfig({}, config_path.resolve())
        configure(config)
        log.enable()
        if isinstance(log.get_logger(), log.FileLogger):
            expected_path = dstack_path / "logs" / datetime.now().strftime('%Y-%m-%d.log')
            self.assertEqual(str(expected_path.resolve()), log.get_logger().filename)
        else:
            self.fail("logger must be a FileLogger")

    def test_debug_with_erasure(self):
        d = {"id": "741fa660-3880-416e-a959-11111111111",
             "timestamp": 1587723588670, "client": "dstack-py",
             "version": "0.3.0",
             "os": {"sysname": "Darwin", "release": "19.3.0",
                    "version": "Darwin Kernel Version 19.3.0: Thu Jan  9 20:58:23 PST 2020;",
                    "machine": "x86_64"},
             "message": "my message",
             "attachments": [{
                 "data": "test data",
                 "type": "image/svg",
                 "description": "My first plot",
                 "params": {
                     "x": 10,
                     "y": 20}
             }, {
                 "data": "test data 2",
                 "type": "image/svg",
                 "description": "My second plot",
                 "params": {
                     "x": 100,
                     "y": 200}
             }],
             "stack": "user/my_stack"}
        my_logger = log.InMemoryLogger()
        # test default level ERASE_BINARY_DATA | ERASE_PARAM_VALUES
        log.enable(logger=my_logger)
        log.debug(func=log.erase_sensitive_data, data=d, extra="extra")
        d1 = json.loads(my_logger.io.getvalue())
        data = d1["data"]
        for i in [0, 1]:
            self.assertTrue(data["attachments"][i]["data"].startswith("erased"))
            self.assertTrue(data["attachments"][i]["params"]["x"].startswith("erased"))
            self.assertTrue(data["attachments"][i]["params"]["y"].startswith("erased"))
        self.assertEqual("extra", d1["extra"])

    def test_erase_sensitive_data(self):
        d = {"id": "741fa660-3880-416e-a959-cc58ac8d2d94",
             "timestamp": 1587723588670, "client": "dstack-py",
             "version": "0.3.0",
             "os": {"sysname": "Darwin", "release": "19.3.0",
                    "version": "Darwin Kernel Version 19.3.0: Thu Jan  9 20:58:23 PST 2020;",
                    "machine": "x86_64"},
             "message": "my message", "attachments": [{
                "data": "test data",
                "type": "image/svg",
                "description": "My first plot",
                "params": {
                    "x": 10,
                    "y": 20}}],
             "stack": "user/my_stack"}
        res = log.erase_sensitive_data(d, log.ERASE_BINARY_DATA)
        self.assertTrue(res["attachments"][0]["data"].startswith("erased"))

        res = log.erase_sensitive_data(d, log.ERASE_PARAM_VALUES)
        self.assertFalse(res["attachments"][0]["data"].startswith("erased"))
        self.assertTrue(res["attachments"][0]["params"]["x"].startswith("erased"))
        self.assertTrue(res["attachments"][0]["params"]["y"].startswith("erased"))

        res = log.erase_sensitive_data(d, log.ERASE_PARAM_NAMES)
        self.assertEqual({10, 20},
                         {res["attachments"][0]["params"]["erased0"],
                          res["attachments"][0]["params"]["erased1"]})

        res = log.erase_sensitive_data(d, log.ERASE_DESCRIPTION)
        self.assertTrue(res["attachments"][0]["description"].startswith("erased"))

        res = log.erase_sensitive_data(d, log.ERASE_STACK_NAME)
        self.assertTrue(res["stack"].startswith("erased"))

        res = log.erase_sensitive_data(d, log.ERASE_PUSH_MESSAGE)
        self.assertTrue(res["message"].startswith("erased"))

        # to be sure all data is okay
        self.assertEqual("my message", d["message"])
        self.assertEqual(10, d["attachments"][0]["params"]["x"])
        self.assertEqual(20, d["attachments"][0]["params"]["y"])
        self.assertEqual("My first plot", d["attachments"][0]["description"])
        self.assertFalse(d["attachments"][0]["data"].startswith("erased"))
        self.assertEqual("user/my_stack", d["stack"])

    def test_erase_token(self):
        headers = {"User-Agent": "python-requests/2.23.0", 
                   "Accept-Encoding": "gzip, deflate", 
                   "Accept": "*/*", 
                   "Connection": "keep-alive", 
                   "Authorization": "Bearer 22231d03-2ea7-22ac-1177-11119b347e0f", 
                   "Content-Type": "application/json; charset=utf-8", 
                   "Content-Length": "20718"}
        self.assertEqual("Bearer ********************************7e0f", log.erase_token(headers)["Authorization"])
