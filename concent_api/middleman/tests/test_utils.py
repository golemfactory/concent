from logging import Logger

import asyncio
import pytest
from assertpy import assert_that
from freezegun import freeze_time
from mock import create_autospec
from mock import patch
from mock import sentinel

from golem_messages.message import Ping

from common.helpers import get_current_utc_timestamp
from middleman.constants import ResponseQueueItem
from middleman.utils import QueuePool
from middleman.utils import validate_connection_to_queue_mapping


class TestQueuePoolInitialization:  # pylint: disable=no-self-use
    def test_that_queue_pool_is_created_with_given_params(self, event_loop):
        initial_data = {1: asyncio.Queue(loop=event_loop)}
        loop = event_loop
        logger = create_autospec(spec=Logger, spec_set=True)

        queue_pool = QueuePool(initial_data, loop, logger)

        assert_that(queue_pool).is_equal_to(initial_data)
        assert_that(queue_pool.loop).is_equal_to(loop)
        assert_that(queue_pool.logger).is_equal_to(logger)

    @patch("middleman.utils.asyncio")
    @patch("middleman.utils.getLogger", return_value=sentinel.logger)
    def test_that_queue_pool_is_created_with_default_params(self, _mocked_get_logger, mocked_asyncio):
        mocked_asyncio.get_event_loop.return_value = sentinel.loop

        queue_pool = QueuePool()

        assert_that(queue_pool).is_equal_to({})
        assert_that(queue_pool.loop).is_equal_to(sentinel.loop)
        assert_that((queue_pool.logger)).is_equal_to(sentinel.logger)


class TestQueuePoolOperations:
    @pytest.fixture(autouse=True)
    def setUp(self, event_loop):
        self.first_index = 1
        self.second_index = 2
        ping_message = Ping()
        resposne_queue_items = [
            ResponseQueueItem(ping_message, 777, get_current_utc_timestamp()),
            ResponseQueueItem(ping_message, 888, get_current_utc_timestamp()),
            ResponseQueueItem(ping_message, 1001, get_current_utc_timestamp()),
            ResponseQueueItem(ping_message, 1007, get_current_utc_timestamp()),
        ]
        first_queue = asyncio.Queue(loop=event_loop)
        second_queue = asyncio.Queue(loop=event_loop)

        self.number_of_items_in_first_queue = 3
        event_loop.run_until_complete(self._populate_queues(first_queue, resposne_queue_items, second_queue))

        self.initial_dict = {
            self.first_index: first_queue,
            self.second_index: second_queue,
        }
        self.logger_mock = create_autospec(spec=Logger, spec_set=True)
        self.queue_pool = QueuePool(self.initial_dict, event_loop, self.logger_mock)

    def test_that_when_already_existing_connection_is_added_exception_is_thrown(self):
        with pytest.raises(KeyError):
            self.queue_pool[1] = asyncio.Queue()

    def test_that_when_already_existing_connection_is_added_during_update_exception_is_thrown(self):
        with pytest.raises(KeyError):
            self.queue_pool.update(self.initial_dict)

    def test_that_deleting_mapping_with_non_empty_queue_logs_untretrived_queue_items(self, event_loop):
        async def inner():
            with freeze_time("2018-09-01 11:48:04"):
                del self.queue_pool[self.first_index]
                await asyncio.sleep(0.0001)

                assert_that(self.queue_pool.keys()).does_not_contain(self.first_index)
                assert_that(self.logger_mock.info.call_count).is_equal_to(self.number_of_items_in_first_queue)

        event_loop.run_until_complete(inner())

    def test_that_popping_mapping_with_non_empty_queue_logs_unretrieved_queue_items(self, event_loop):
        async def inner():
            with freeze_time("2018-09-01 11:48:04"):
                retrived_item = self.queue_pool.pop(self.second_index)
                await asyncio.sleep(0.0001)

                assert_that(retrived_item.empty()).is_true()
                assert_that(self.queue_pool.keys()).does_not_contain(self.second_index)
                assert_that(self.logger_mock.info.call_count).is_equal_to(1)

        event_loop.run_until_complete(inner())

    def test_that_using_popitem_on_mapping_with_non_empty_queue_logs_unretrieved_queue_items(self, event_loop):
        async def inner():
            with freeze_time("2018-09-01 11:48:04"):
                index, queue = self.queue_pool.popitem()
                await asyncio.sleep(0.0001)

                assert_that(queue.empty()).is_true()
                assert_that(self.queue_pool.keys()).does_not_contain(index)
                assert_that(self.logger_mock.info.call_count).is_equal_to(1)

        event_loop.run_until_complete(inner())

    async def _populate_queues(self, first_queue, resposne_queue_items, second_queue):
        for item in resposne_queue_items[:self.number_of_items_in_first_queue]:
            await first_queue.put(item)
        for item in resposne_queue_items[self.number_of_items_in_first_queue:]:
            await second_queue.put(item)


@pytest.mark.parametrize(
    "key, value", [
        ("this_is_not_int", asyncio.Queue()),
        (123.4, asyncio.Queue()),
        (777, "this_is_not_a_queue"),
        (888, sentinel.queue),
    ]
)
def test_validate_connection_to_queue_mapping(key, value):
    with pytest.raises(ValueError):
        validate_connection_to_queue_mapping(key, value)
