from asyncio import StreamReader
from assertpy import assert_that
from mock import MagicMock
from mock import Mock

from middleman_protocol.constants import ESCAPE_CHARACTER
from middleman_protocol.constants import ESCAPE_SEQUENCES
from middleman_protocol.constants import FRAME_SEPARATOR
from middleman_protocol.stream_async import handle_frame_receive_async

SOME_BYTES = b'1234567890qwerty'

MESSAGE = SOME_BYTES + FRAME_SEPARATOR

MESSAGE_WITH_ESCAPE_CHARACTER_SEQUENCE = SOME_BYTES + ESCAPE_SEQUENCES[ESCAPE_CHARACTER] + FRAME_SEPARATOR


def async_stream_reader_mock(*args, **kwargs):
    m = MagicMock(*args, **kwargs)

    async def mock_coro(*a, **kw):
        return m(*a, **kw)

    mock_coro.mock = m
    return mock_coro


class TestHandleFrameReceiveAsync:
    def test_that_when_data_with_no_escape_sequence_and_separator_is_received_unescaped_data_is_returned(self, event_loop):
        mocked_reader = self._prepare_mocked_reader(MESSAGE)

        task = self._run_test_in_event_loop(event_loop, mocked_reader)

        assert_that(task.done()).is_true()
        mocked_reader.readuntil.mock.assert_called_once_with(FRAME_SEPARATOR)
        assert_that(task.result()).is_equal_to(SOME_BYTES)

    def test_that_when_data_with_escaped_sequence_and_separator_is_received_unescaped_data_is_returned(self, event_loop):
        mocked_reader = self._prepare_mocked_reader(MESSAGE_WITH_ESCAPE_CHARACTER_SEQUENCE)

        task = self._run_test_in_event_loop(event_loop, mocked_reader)

        assert_that(task.done()).is_true()
        mocked_reader.readuntil.mock.assert_called_once_with(FRAME_SEPARATOR)
        assert_that(task.result()).is_equal_to(SOME_BYTES + ESCAPE_CHARACTER)

    @staticmethod
    def _run_test_in_event_loop(event_loop, mocked_reader):
        task = event_loop.create_task(handle_frame_receive_async(mocked_reader))
        event_loop.run_until_complete(task)
        return task

    @staticmethod
    def _prepare_mocked_reader(return_sequence):
        mocked_reader = Mock(spec_set=StreamReader)
        mocked_reader.readuntil = async_stream_reader_mock(return_value=return_sequence)
        return mocked_reader
