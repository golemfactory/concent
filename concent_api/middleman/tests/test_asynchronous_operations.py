from asyncio import CancelledError
from asyncio import IncompleteReadError
from asyncio import Queue
from asyncio import sleep
import datetime
from collections import OrderedDict

from contextlib import suppress
from logging import Logger

import pytest
from assertpy import assert_that
from django.conf import settings
from django.test import override_settings
from freezegun import freeze_time
from mock import create_autospec
from mock import Mock
from mock import patch

from golem_messages.cryptography import ecdsa_sign
from golem_messages.message import Ping

from common.helpers import parse_datetime_to_timestamp
from common.helpers import sign_message
from common.testing_helpers import generate_ecc_key_pair
from middleman.constants import AUTHENTICATION_CHALLENGE_SIZE
from middleman.constants import HEARTBEAT_INTERVAL
from middleman.constants import HEARTBEAT_REQUEST_ID
from middleman.constants import MessageTrackerItem
from middleman.constants import RequestQueueItem
from middleman.constants import ResponseQueueItem
from middleman.asynchronous_operations import create_error_frame
from middleman.asynchronous_operations import discard_entries_for_lost_messages
from middleman.asynchronous_operations import heartbeat_producer
from middleman.asynchronous_operations import is_authenticated
from middleman.asynchronous_operations import request_consumer
from middleman.asynchronous_operations import request_producer
from middleman.asynchronous_operations import response_consumer
from middleman.asynchronous_operations import response_producer
from middleman.utils import QueuePool
from middleman_protocol.constants import ErrorCode
from middleman_protocol.constants import MIDDLEMAN_EXCEPTION_TO_ERROR_CODE_MAP
from middleman_protocol.constants import PayloadType
from middleman_protocol.exceptions import BrokenEscapingInFrameMiddlemanProtocolError
from middleman_protocol.exceptions import FrameInvalidMiddlemanProtocolError
from middleman_protocol.exceptions import PayloadTypeInvalidMiddlemanProtocolError
from middleman_protocol.exceptions import SignatureInvalidMiddlemanProtocolError
from middleman_protocol.message import AbstractFrame
from middleman_protocol.message import AuthenticationChallengeFrame
from middleman_protocol.message import AuthenticationResponseFrame
from middleman_protocol.message import ErrorFrame
from middleman_protocol.message import GolemMessageFrame
from middleman_protocol.message import HeartbeatFrame
from middleman_protocol.registry import create_middleman_protocol_message
from middleman_protocol.stream import append_frame_separator
from middleman_protocol.stream import escape_encode_raw_message
from middleman_protocol.tests.utils import async_stream_actor_mock
from middleman_protocol.tests.utils import prepare_mocked_reader
from middleman_protocol.tests.utils import prepare_mocked_writer

(CONCENT_PRIVATE_KEY, CONCENT_PUBLIC_KEY) = generate_ecc_key_pair()
(SIGNING_SERVICE_PRIVATE_KEY, SIGNING_SERVICE_PUBLIC_KEY) = generate_ecc_key_pair()
(WRONG_SIGNING_SERVICE_PRIVATE_KEY, WRONG_SIGNING_SERVICE_PUBLIC_KEY) = generate_ecc_key_pair()
FROZEN_DATE_AND_TIME = "2012-01-14 12:00:01"
FROZEN_TIMESTAMP = parse_datetime_to_timestamp(datetime.datetime.strptime(FROZEN_DATE_AND_TIME, "%Y-%m-%d %H:%M:%S"))


async def get_item(queue):
    await sleep(0.000001)
    item = await queue.get()
    queue.task_done()
    return item


def _get_mocked_reader(message, request_id, sign_as, **kwargs):
    protocol_message = create_middleman_protocol_message(PayloadType.GOLEM_MESSAGE, message, request_id)
    data_to_send = append_frame_separator(
        escape_encode_raw_message(
            protocol_message.serialize(sign_as)
        )
    )
    mocked_reader = prepare_mocked_reader(data_to_send, **kwargs)
    return mocked_reader


@freeze_time(FROZEN_DATE_AND_TIME)
class TestRequestProducer:

    @pytest.fixture(autouse=True)
    def setUp(self, event_loop):
        self.golem_message = Ping()
        self.connection_id = 1
        self.request_id = 777
        self.queue = Queue(loop=event_loop)
        self.response_queue = Queue(loop=event_loop)

    @pytest.mark.asyncio
    async def test_that_when_valid_frame_is_received_a_new_item_is_added_to_the_queue(self, event_loop):
        with override_settings(
            CONCENT_PRIVATE_KEY=CONCENT_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY=CONCENT_PUBLIC_KEY,
        ):
            mocked_reader = _get_mocked_reader(self.golem_message, self.request_id, settings.CONCENT_PRIVATE_KEY)

            producer_task = event_loop.create_task(
                request_producer(self.queue, self.response_queue, mocked_reader, self.connection_id)
            )
            item = await get_item(self.queue)
            producer_task.cancel()

            assert_that(item.connection_id).is_equal_to(self.connection_id)
            assert_that(item.concent_request_id).is_equal_to(self.request_id)
            assert_that(item.message).is_equal_to(self.golem_message)
            assert_that(item.timestamp).is_equal_to(FROZEN_TIMESTAMP)

    @pytest.mark.asyncio
    async def test_that_when_client_terminates_connection_coroutine_ends(self, event_loop):
        with override_settings(
            CONCENT_PRIVATE_KEY=CONCENT_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY=CONCENT_PUBLIC_KEY,
        ):
            some_bytes = b"some bytes"
            mocked_reader = prepare_mocked_reader(some_bytes, side_effect=IncompleteReadError(some_bytes, 777))

            producer_task = event_loop.create_task(
                request_producer(self.queue, self.response_queue, mocked_reader, self.connection_id)
            )
            await producer_task

            assert_that(self.queue.empty()).is_true()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "exception", (
            FrameInvalidMiddlemanProtocolError,
            BrokenEscapingInFrameMiddlemanProtocolError,
            SignatureInvalidMiddlemanProtocolError,
            PayloadTypeInvalidMiddlemanProtocolError
        )
    )
    async def test_that_when_invalid_frame_is_received_error_frame_is_returned_via_queue(self, exception, event_loop):
        with override_settings(
            CONCENT_PRIVATE_KEY=CONCENT_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY=CONCENT_PUBLIC_KEY,
        ):
            mocked_reader = _get_mocked_reader(self.golem_message, self.request_id, settings.CONCENT_PRIVATE_KEY, side_effect=exception)
            producer_task = event_loop.create_task(
                request_producer(self.queue, self.response_queue, mocked_reader, self.connection_id)
            )
            item = await get_item(self.response_queue)
            producer_task.cancel()

            assert_that(item.concent_request_id).is_equal_to(0)
            assert_that(item.message).is_instance_of(ErrorFrame)
            assert_that(item.timestamp).is_equal_to(FROZEN_TIMESTAMP)


@freeze_time(FROZEN_DATE_AND_TIME)
class TestRequestConsumer:

    @pytest.fixture(autouse=True)
    def setUp(self, event_loop):
        self.mocked_writer = prepare_mocked_writer()
        self.message_tracker = OrderedDict({})
        self.golem_message = Ping()
        sign_message(self.golem_message, CONCENT_PRIVATE_KEY)
        self.connection_id = 4
        self.request_id = 888
        self.queue = Queue(loop=event_loop)
        self.queue_pool = QueuePool(
            {self.connection_id: Queue(loop=event_loop)},
            loop=event_loop,
        )
        self.signing_service_request_id = 1
        self.request_queue_item = RequestQueueItem(
            self.connection_id,
            self.request_id,
            self.golem_message,
            FROZEN_TIMESTAMP
        )

    @pytest.mark.asyncio
    async def test_that_when_connection_id_no_longer_exists_corresponding_item_is_dropped(self,  event_loop):
        with patch("middleman.asynchronous_operations.logger") as mocked_logger:
            with override_settings(
                CONCENT_PRIVATE_KEY=CONCENT_PRIVATE_KEY,
                CONCENT_PUBLIC_KEY=CONCENT_PUBLIC_KEY,
            ):
                await self.queue.put(self.request_queue_item)
                consumer_task = event_loop.create_task(
                    request_consumer(
                        self.queue,
                        QueuePool({}),
                        self.message_tracker,
                        self.mocked_writer
                    )
                )
                await self.queue.join()
                consumer_task.cancel()

                assert_that(self.message_tracker).is_empty()
                mocked_logger.info.assert_called_once_with(
                    f"No matching queue for connection id: {self.request_queue_item.connection_id}"
                )
                self.mocked_writer.assert_not_called()

    @pytest.mark.asyncio
    async def test_that_when_connection_exists_item_from_the_queue_is_sent_via_writer(self, event_loop):
        with patch("middleman.asynchronous_operations.logger") as mocked_logger:
            with override_settings(
                CONCENT_PRIVATE_KEY=CONCENT_PRIVATE_KEY,
                CONCENT_PUBLIC_KEY=CONCENT_PUBLIC_KEY,
            ):
                expected_data = append_frame_separator(
                    escape_encode_raw_message(
                        GolemMessageFrame(self.golem_message, self.signing_service_request_id).serialize(CONCENT_PRIVATE_KEY)
                    )
                )

                await self.queue.put(self.request_queue_item)
                consumer_task = event_loop.create_task(
                    request_consumer(
                        self.queue,
                        self.queue_pool,
                        self.message_tracker,
                        self.mocked_writer
                    )
                )
                await self.queue.join()
                consumer_task.cancel()

                assert_that(self.message_tracker[self.signing_service_request_id]).is_equal_to(
                    MessageTrackerItem(
                        self.request_id,
                        self.connection_id,
                        self.golem_message,
                        FROZEN_TIMESTAMP
                    )
                )
                mocked_logger.debug.assert_not_called()
                self.mocked_writer.write.assert_called_once_with(expected_data)
                self.mocked_writer.drain.mock.assert_called_once_with()


class TestDiscardEntriesForLostMessages:

    @pytest.fixture(autouse=True)
    def setUp(self):
        self.mocked_logger = create_autospec(spec=Logger, spec_set=True)
        self.message_tracker = OrderedDict([
            (4, Mock(spec_set=MessageTrackerItem)),
            (5, Mock(spec_set=MessageTrackerItem)),
            (6, Mock(spec_set=MessageTrackerItem)),
            (999, Mock(spec_set=MessageTrackerItem)),
            (1, Mock(spec_set=MessageTrackerItem)),
        ])
        self.all_initial_keys = list(self.message_tracker.keys())

    def test_that_if_request_id_matches_first_entry_no_messages_are_discarded(self):
        index_of_first_entry = 0
        first_entry_id = self.all_initial_keys[index_of_first_entry]
        discard_entries_for_lost_messages(first_entry_id, self.message_tracker, self.mocked_logger)

        assert_that(self.mocked_logger.call_count).is_equal_to(0)
        assert_that(self.message_tracker.keys()).contains_only(*self.all_initial_keys)

    def test_that_if_request_id_matches_third_entry_two_messages_are_discarded(self):
        index_of_second_entry = 2
        third_entry_id = self.all_initial_keys[index_of_second_entry]
        discard_entries_for_lost_messages(third_entry_id, self.message_tracker, self.mocked_logger)

        assert_that(self.mocked_logger.info.call_count).is_equal_to(2)
        assert_that(self.message_tracker.keys()).contains_only(*self.all_initial_keys[index_of_second_entry:])

    def test_that_if_request_id_matches_last_entry_all_but_one_messages_are_discarded(self):
        initial_count_of_message_tracker_items = len(self.message_tracker)
        index_of_last_entry = -1
        last_entry_id = self.all_initial_keys[index_of_last_entry]

        discard_entries_for_lost_messages(last_entry_id, self.message_tracker, self.mocked_logger)

        assert_that(self.mocked_logger.info.call_count).is_equal_to(initial_count_of_message_tracker_items - 1)
        assert_that(self.message_tracker.keys()).contains_only(*self.all_initial_keys[index_of_last_entry:])

    def test_that_if_request_id_matches_no_entry_no_messages_are_discarded_and_warning_is_logged(self):
        non_existing_request_id = 777
        discard_entries_for_lost_messages(non_existing_request_id, self.message_tracker, self.mocked_logger)

        assert_that(self.mocked_logger.info.call_count).is_equal_to(0)
        assert_that(self.mocked_logger.warning.call_count).is_equal_to(1)
        assert_that(self.message_tracker).contains_only(*self.all_initial_keys)


ERROR_CODES_MAP = MIDDLEMAN_EXCEPTION_TO_ERROR_CODE_MAP
ERROR_CODES_MAP[Exception] = ErrorCode.Unknown


@pytest.mark.parametrize(
    "exception, error_code", zip(ERROR_CODES_MAP.keys(), ERROR_CODES_MAP.values())
)
def test_that_error_frame_is_created_correctly(exception, error_code):
    error_frame = create_error_frame(exception)

    assert_that(error_frame.payload[0]).is_equal_to(error_code)
    assert_that(error_frame.request_id).is_equal_to(0)  # TODO: update after this constant is added to MiddlemanProtocol


@freeze_time(FROZEN_DATE_AND_TIME)
class TestResponseProducer:

    @pytest.fixture(autouse=True)
    def setUp(self, event_loop):
        self.connection_id_1 = 7
        self.connection_id_2 = 8
        self.connection_id_3 = 13
        self.connection_id_4 = 14
        self.ss_request_id_1 = 17
        self.ss_request_id_2 = 19
        self.ss_request_id_3 = 20
        self.ss_request_id_4 = 21
        self.golem_message = Ping()
        self.golem_message_from_ss = Ping()
        self.concent_request_id = 777
        self.different_concent_request_id = 777
        self.message_tracker = OrderedDict([
            (self.ss_request_id_1, MessageTrackerItem(self.concent_request_id, self.connection_id_1, self.golem_message, FROZEN_TIMESTAMP)),
            (self.ss_request_id_2, MessageTrackerItem(self.concent_request_id, self.connection_id_2, self.golem_message, FROZEN_TIMESTAMP)),
            (self.ss_request_id_3, MessageTrackerItem(self.different_concent_request_id, self.connection_id_3, self.golem_message, FROZEN_TIMESTAMP)),
            (self.ss_request_id_4, MessageTrackerItem(self.different_concent_request_id, self.connection_id_4, self.golem_message, FROZEN_TIMESTAMP)),
        ])
        self.response_queue_pool = QueuePool(
            {
                self.connection_id_1: Queue(loop=event_loop),
                self.connection_id_4: Queue(loop=event_loop),
            }
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "exception", (
            FrameInvalidMiddlemanProtocolError,
            BrokenEscapingInFrameMiddlemanProtocolError,
            SignatureInvalidMiddlemanProtocolError,
            PayloadTypeInvalidMiddlemanProtocolError
        )
    )
    async def test_that_if_received_message_is_invalid_it_is_dropped_and_info_is_logged(self, exception, event_loop):
        with patch("middleman.asynchronous_operations.logger") as mocked_logger:
            with override_settings(
                CONCENT_PRIVATE_KEY=CONCENT_PRIVATE_KEY,
                CONCENT_PUBLIC_KEY=CONCENT_PUBLIC_KEY,
                SIGNING_SERVICE_PUBLIC_KEY=SIGNING_SERVICE_PUBLIC_KEY
            ):
                mocked_reader = _get_mocked_reader(
                    self.golem_message_from_ss,
                    self.ss_request_id_1,
                    SIGNING_SERVICE_PRIVATE_KEY,
                    side_effect=exception
                )

                task = event_loop.create_task(
                    response_producer(
                        self.response_queue_pool,
                        mocked_reader,
                        self.message_tracker
                    )
                )
                await sleep(0.001)
                task.cancel()

                assert_that(mocked_logger.info.mock_calls[0][1][0]).contains("Received invalid message")

    @pytest.mark.asyncio
    async def test_that_if_received_messages_request_id_is_not_in_message_tracker_it_is_dropped_and_info_is_logged(self, event_loop):
        with patch("middleman.asynchronous_operations.logger") as mocked_logger:
            with override_settings(
                CONCENT_PRIVATE_KEY=CONCENT_PRIVATE_KEY,
                CONCENT_PUBLIC_KEY=CONCENT_PUBLIC_KEY,
                SIGNING_SERVICE_PUBLIC_KEY=SIGNING_SERVICE_PUBLIC_KEY
            ):
                invalid_id = 12345
                mocked_reader = _get_mocked_reader(
                    self.golem_message_from_ss,
                    invalid_id,
                    SIGNING_SERVICE_PRIVATE_KEY,
                )

                task = event_loop.create_task(
                    response_producer(
                        self.response_queue_pool,
                        mocked_reader,
                        self.message_tracker
                    )
                )
                await sleep(0.001)
                task.cancel()

                assert_that(mocked_logger.info.mock_calls[0][1]).contains(
                    f"There is no entry in Message Tracker for request ID = {invalid_id}, skipping..."
                )

    @pytest.mark.asyncio
    async def test_that_if_response_queue_for_corresponding_connection_no_longer_exists_entry_is_removed_from_tracker(self, event_loop):
        with patch("middleman.asynchronous_operations.logger") as mocked_logger:
            with override_settings(
                CONCENT_PRIVATE_KEY=CONCENT_PRIVATE_KEY,
                CONCENT_PUBLIC_KEY=CONCENT_PUBLIC_KEY,
                SIGNING_SERVICE_PUBLIC_KEY=SIGNING_SERVICE_PUBLIC_KEY
            ):
                mocked_reader = _get_mocked_reader(
                    self.golem_message_from_ss,
                    self.ss_request_id_2,
                    SIGNING_SERVICE_PRIVATE_KEY,
                )

                producer_task = event_loop.create_task(
                    response_producer(
                        self.response_queue_pool,
                        mocked_reader,
                        self.message_tracker
                    )
                )
                await sleep(0.001)
                producer_task.cancel()

                assert_that(self.message_tracker.keys()).does_not_contain(*(self.ss_request_id_2,))
                assert_that(mocked_logger.info.mock_calls[0][1]).contains(
                    f"Response queue for {self.connection_id_2} doesn't exist anymore, skipping..."
                )

    @pytest.mark.asyncio
    async def test_that_lost_messages_are_discarded_and_valid_message_is_sent_via_response_queue(self, event_loop):
        with patch("middleman.asynchronous_operations.logger"):
            with override_settings(
                CONCENT_PRIVATE_KEY=CONCENT_PRIVATE_KEY,
                CONCENT_PUBLIC_KEY=CONCENT_PUBLIC_KEY,
                SIGNING_SERVICE_PUBLIC_KEY=SIGNING_SERVICE_PUBLIC_KEY
            ):
                mocked_reader = _get_mocked_reader(
                    self.golem_message_from_ss,
                    self.ss_request_id_4,
                    SIGNING_SERVICE_PRIVATE_KEY,
                )

                producer_task = event_loop.create_task(
                    response_producer(
                        self.response_queue_pool,
                        mocked_reader,
                        self.message_tracker
                    )
                )
                item = await get_item(self.response_queue_pool[self.connection_id_4])  # type: ResponseQueueItem
                producer_task.cancel()

                assert_that(self.message_tracker).is_empty()
                assert_that(item.concent_request_id).is_equal_to(self.different_concent_request_id)
                assert_that(item.message).is_equal_to(self.golem_message_from_ss)
                assert_that(item.timestamp).is_equal_to(FROZEN_TIMESTAMP)

    @pytest.mark.asyncio
    async def test_that_if_signing_service_closes_connection_coroutine_ends(self, event_loop):
        with patch("middleman.asynchronous_operations.logger") as mocked_logger:
            with override_settings(
                CONCENT_PRIVATE_KEY=CONCENT_PRIVATE_KEY,
                CONCENT_PUBLIC_KEY=CONCENT_PUBLIC_KEY,
                SIGNING_SERVICE_PUBLIC_KEY=SIGNING_SERVICE_PUBLIC_KEY
            ):
                some_bytes = b"some bytes"
                mocked_reader = prepare_mocked_reader(some_bytes, side_effect=IncompleteReadError(some_bytes, 777))
                initial_message_tracker = OrderedDict(self.message_tracker)
                producer_task = event_loop.create_task(
                    response_producer(self.response_queue_pool, mocked_reader, self.message_tracker)
                )
                await producer_task

                assert_that(self.message_tracker).is_equal_to(initial_message_tracker)
                assert_that(self.response_queue_pool[self.connection_id_1].empty()).is_true()
                assert_that(self.response_queue_pool[self.connection_id_4].empty()).is_true()
                assert_that(mocked_logger.info.mock_calls[0][1][0]).contains(
                    "Signing Service has closed the connection"
                )


class TestResponseConsumer:
    @pytest.mark.asyncio
    async def test_that_received_item_received_via_response_queue_is_sent_to_concent(self, event_loop):
        with override_settings(
            CONCENT_PRIVATE_KEY=CONCENT_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY=CONCENT_PUBLIC_KEY,
            SIGNING_SERVICE_PUBLIC_KEY=SIGNING_SERVICE_PUBLIC_KEY
        ):
            connection_id = 11
            concent_request_id = 77
            response_queue = Queue(loop=event_loop)
            golem_message = Ping()
            response_queue_item = ResponseQueueItem(golem_message, concent_request_id, FROZEN_TIMESTAMP)
            expected_data = append_frame_separator(
                escape_encode_raw_message(
                    GolemMessageFrame(golem_message, concent_request_id).serialize(settings.CONCENT_PRIVATE_KEY)
                )
            )
            mocked_writer = prepare_mocked_writer()

            await response_queue.put(response_queue_item)
            consumer_task = event_loop.create_task(
                response_consumer(
                    response_queue,
                    mocked_writer,
                    connection_id
                )
            )
            await response_queue.join()
            consumer_task.cancel()

            mocked_writer.write.assert_called_once_with(expected_data)
            mocked_writer.drain.mock.assert_called_once_with()


class TestIsAuthenticated:
    @pytest.fixture(autouse=True)
    def setUp(self):
        self.mocked_writer = prepare_mocked_writer()
        self.request_id = 7
        self.wrong_request_id = 8
        self.mocked_challenge = b'f' * AUTHENTICATION_CHALLENGE_SIZE

    @pytest.mark.asyncio
    async def test_that_if_received_frame_has_wrong_request_id_then_function_returns_false(self):
        with override_settings(
            SIGNING_SERVICE_PRIVATE_KEY=SIGNING_SERVICE_PRIVATE_KEY,
            SIGNING_SERVICE_PUBLIC_KEY=SIGNING_SERVICE_PUBLIC_KEY,
            CONCENT_PRIVATE_KEY=CONCENT_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY=CONCENT_PUBLIC_KEY,
        ):
            with patch("middleman.asynchronous_operations.RequestIDGenerator.generate_request_id", return_value=self.request_id):
                frame_with_wrong_request_id = AuthenticationResponseFrame(
                    payload=ecdsa_sign(
                        WRONG_SIGNING_SERVICE_PRIVATE_KEY,
                        self.mocked_challenge,
                    ),
                    request_id=self.wrong_request_id,
                )
                mocked_reader = self._prepare_mocked_reader(frame_with_wrong_request_id)

                authentication_successful = await is_authenticated(mocked_reader, self.mocked_writer)

                self.mocked_writer.write.assert_called_once()
                assert_that(authentication_successful).is_false()

    @pytest.mark.asyncio
    async def test_that_if_received_frame_is_not_authentication_response_frame_then_function_returns_false(self):
        with override_settings(
            SIGNING_SERVICE_PRIVATE_KEY=SIGNING_SERVICE_PRIVATE_KEY,
            SIGNING_SERVICE_PUBLIC_KEY=SIGNING_SERVICE_PUBLIC_KEY,
            CONCENT_PRIVATE_KEY=CONCENT_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY=CONCENT_PUBLIC_KEY,
        ):
            with patch("middleman.asynchronous_operations.RequestIDGenerator.generate_request_id", return_value=self.request_id):
                wrong_frame = AuthenticationChallengeFrame(b"some_bytes", self.request_id)
                mocked_reader = self._prepare_mocked_reader(wrong_frame)

                authentication_successful = await is_authenticated(mocked_reader, self.mocked_writer)

                self.mocked_writer.write.assert_called_once()
                assert_that(authentication_successful).is_false()

    @pytest.mark.asyncio
    async def test_that_if_received_authentication_response_frame_has_invalid_signature_then_function_returns_false(self):
        with override_settings(
            SIGNING_SERVICE_PRIVATE_KEY=SIGNING_SERVICE_PRIVATE_KEY,
            SIGNING_SERVICE_PUBLIC_KEY=SIGNING_SERVICE_PUBLIC_KEY,
            CONCENT_PRIVATE_KEY=CONCENT_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY=CONCENT_PUBLIC_KEY,
        ):
            with patch("middleman.asynchronous_operations.RequestIDGenerator.generate_request_id", return_value=self.request_id):
                with patch("middleman.asynchronous_operations.create_random_challenge", return_value=self.mocked_challenge):
                    authentication_response_frame = AuthenticationResponseFrame(
                        payload=ecdsa_sign(
                            WRONG_SIGNING_SERVICE_PRIVATE_KEY,
                            self.mocked_challenge,
                        ),
                        request_id=self.request_id,
                    )
                    mocked_reader = self._prepare_mocked_reader(authentication_response_frame)

                    authentication_successful = await is_authenticated(mocked_reader, self.mocked_writer)

                    self.mocked_writer.write.assert_called_once()
                    assert_that(authentication_successful).is_false()

    @pytest.mark.asyncio
    async def test_that_if_authentication_response_frame_has_valid_signature_then_function_returns_true(self):
        with override_settings(
            SIGNING_SERVICE_PRIVATE_KEY=SIGNING_SERVICE_PRIVATE_KEY,
            SIGNING_SERVICE_PUBLIC_KEY=SIGNING_SERVICE_PUBLIC_KEY,
            CONCENT_PRIVATE_KEY=CONCENT_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY=CONCENT_PUBLIC_KEY,
        ):
            with patch("middleman.asynchronous_operations.RequestIDGenerator.generate_request_id", return_value=self.request_id):
                with patch("middleman.asynchronous_operations.create_random_challenge", return_value=self.mocked_challenge):
                    authentication_response_frame = AuthenticationResponseFrame(
                        payload=ecdsa_sign(
                            SIGNING_SERVICE_PRIVATE_KEY,
                            self.mocked_challenge,
                        ),
                        request_id=self.request_id,
                    )
                    mocked_reader = self._prepare_mocked_reader(authentication_response_frame)

                    authentication_successful = await is_authenticated(mocked_reader, self.mocked_writer)

                    self.mocked_writer.write.assert_called_once()
                    assert_that(authentication_successful).is_true()

    @staticmethod
    def _prepare_mocked_reader(frame: AbstractFrame, private_key: bytes = SIGNING_SERVICE_PRIVATE_KEY):
        serialized = frame.serialize(private_key)
        data_to_send = append_frame_separator(escape_encode_raw_message(serialized))
        return prepare_mocked_reader(data_to_send)


def test_heartbeat_producer_sends_heartbeat_in_time_intervals(event_loop):
    with override_settings(
        CONCENT_PRIVATE_KEY=CONCENT_PRIVATE_KEY
    ):
        mocked_writer = prepare_mocked_writer()
        expected_data = append_frame_separator(
            escape_encode_raw_message(
                HeartbeatFrame(None, HEARTBEAT_REQUEST_ID).serialize(CONCENT_PRIVATE_KEY)
            )
        )
        heartbeat_producer_task = event_loop.create_task(
            heartbeat_producer(
                mocked_writer,
            )
        )
        with patch(
            "middleman.asynchronous_operations.sleep",
            new=async_stream_actor_mock(side_effect=lambda _: heartbeat_producer_task.cancel())
        ) as sleep_mock:
            with suppress(CancelledError):
                event_loop.run_until_complete(heartbeat_producer_task)
            mocked_writer.write.assert_called_with(expected_data)
            mocked_writer.drain.mock.assert_called()
            sleep_mock.mock.assert_called_with(HEARTBEAT_INTERVAL)
