from asyncio import StreamReader
from asyncio import StreamWriter

import pytest
from assertpy import assert_that
from mock import Mock

from middleman_protocol import constants
from middleman_protocol import exceptions
from middleman_protocol.constants import ESCAPE_CHARACTER
from middleman_protocol.constants import ESCAPE_SEQUENCES
from middleman_protocol.constants import FRAME_SEPARATOR
from middleman_protocol.stream_async import handle_frame_receive_async
from middleman_protocol.stream_async import map_exception_to_error_code
from middleman_protocol.stream_async import send_over_stream_async
from middleman_protocol.testing_utils import async_stream_actor_mock

SOME_BYTES = b'1234567890qwerty'

MESSAGE = SOME_BYTES + FRAME_SEPARATOR

MESSAGE_WITH_ESCAPE_CHARACTER_SEQUENCE = SOME_BYTES + ESCAPE_SEQUENCES[ESCAPE_CHARACTER] + FRAME_SEPARATOR


def _run_test_in_event_loop(event_loop, coroutine, *args):
    task = event_loop.create_task(coroutine(*args))
    event_loop.run_until_complete(task)
    return task


class TestHandleFrameReceiveAsync:
    def test_that_when_data_with_no_escape_sequence_and_separator_is_received_unescaped_data_is_returned(self, event_loop):
        mocked_reader = self._prepare_mocked_reader(MESSAGE)

        task = _run_test_in_event_loop(event_loop, handle_frame_receive_async, mocked_reader)

        assert_that(task.done()).is_true()
        mocked_reader.readuntil.mock.assert_called_once_with(FRAME_SEPARATOR)
        assert_that(task.result()).is_equal_to(SOME_BYTES)

    def test_that_when_data_with_escaped_sequence_and_separator_is_received_unescaped_data_is_returned(self, event_loop):
        mocked_reader = self._prepare_mocked_reader(MESSAGE_WITH_ESCAPE_CHARACTER_SEQUENCE)

        task = _run_test_in_event_loop(event_loop, handle_frame_receive_async, mocked_reader)

        assert_that(task.done()).is_true()
        mocked_reader.readuntil.mock.assert_called_once_with(FRAME_SEPARATOR)
        assert_that(task.result()).is_equal_to(SOME_BYTES + ESCAPE_CHARACTER)

    @staticmethod
    def _prepare_mocked_reader(return_sequence):
        mocked_reader = Mock(spec_set=StreamReader)
        mocked_reader.readuntil = async_stream_actor_mock(return_value=return_sequence)
        return mocked_reader


@pytest.mark.parametrize(
    "exception, expected_error_code", (
        (exceptions.PayloadTypeInvalidMiddlemanProtocolError, constants.ErrorCode.InvalidPayload),
        (exceptions.RequestIdInvalidTypeMiddlemanProtocolError, constants.ErrorCode.InvalidFrame),
        (exceptions.SignatureInvalidMiddlemanProtocolError, constants.ErrorCode.InvalidFrameSignature),
        (exceptions.PayloadInvalidMiddlemanProtocolError, constants.ErrorCode.InvalidPayload),
        (exceptions.FrameInvalidMiddlemanProtocolError, constants.ErrorCode.InvalidFrame),
        (exceptions.MiddlemanProtocolError, constants.ErrorCode.Unknown),
        (Exception, constants.ErrorCode.Unknown),
    )
)
def test_that_middleman_protocol_exceptions_are_correctly_mapped_to_error_codes(exception, expected_error_code):
    assert_that(map_exception_to_error_code(exception)).is_equal_to(expected_error_code)


class TestSendOverStreamAsync:
    def test_that_sent_data_is_escaped_and_contains_frame_separator(self, event_loop):
        mocked_writer = self._prepare_mocked_writer()

        task = _run_test_in_event_loop(event_loop, send_over_stream_async, SOME_BYTES + ESCAPE_CHARACTER, mocked_writer)

        assert_that(task.done()).is_true()
        mocked_writer.write.assert_called_once_with(SOME_BYTES + ESCAPE_SEQUENCES[ESCAPE_CHARACTER] + FRAME_SEPARATOR)
        mocked_writer.drain.mock.assert_called_once_with()

    @staticmethod
    def _prepare_mocked_writer():
        mocked_writer = Mock(spec_set=StreamWriter)
        mocked_writer.drain = async_stream_actor_mock()
        return mocked_writer
