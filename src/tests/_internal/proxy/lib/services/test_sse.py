import pytest

from dstack._internal.proxy.lib.services.model_proxy.sse import SSEDecoder


class TestSSEDecoder:
    @pytest.mark.parametrize("step", [1, 2, 3, 17, 4096])
    def test_fragmentation_utf8_crlf_comments_and_multiple_events(self, step):
        wire = ': keepalive\r\ndata: {"text":"привет"}\r\n\r\ndata: first\ndata: second\n\ndata: [DONE]\n\n'.encode()
        parser = SSEDecoder()
        events = []
        for start in range(0, len(wire), step):
            events.extend(parser.feed(wire[start : start + step]))
        parser.finish()
        assert events == ['{"text":"привет"}', "first\nsecond", "[DONE]"]

    def test_bounds_unfinished_events_and_rejects_truncated_utf8(self):
        parser = SSEDecoder(max_event_bytes=16)
        with pytest.raises(ValueError):
            parser.feed(b"data: " + b"x" * 17)
        parser = SSEDecoder()
        parser.feed(b"data: partial")
        with pytest.raises(ValueError):
            parser.finish()
        parser = SSEDecoder()
        parser.feed(b"data: \xd0")
        with pytest.raises(ValueError):
            parser.finish()
