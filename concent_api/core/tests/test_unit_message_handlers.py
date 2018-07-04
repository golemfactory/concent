import threading
from threading import Thread
import time
from unittest import TestCase

from django.test import TransactionTestCase

from core.message_handlers import are_items_unique
from core.tests.test_utils import DatabaseHandler
from core.tests.test_utils import StoreOrUpdateSubtaskTest


class TestMessageHandlers(TestCase):
    def test_that_function_returns_true_when_ids_are_diffrent(self):
        response = are_items_unique([1, 2, 3, 4, 5])
        self.assertTrue(response)

    def test_that_function_returns_false_when_ids_are_the_same(self):
        response = are_items_unique([1, 2, 3, 2, 5])
        self.assertFalse(response)


class TestEnsureRetryOfLockedCalls(TransactionTestCase):

    def setUp(self):
        super().setUp()
        self.hepler1 = StoreOrUpdateSubtaskTest(task_id='g112d', subtask_id='hrff4')
        self.hepler2 = StoreOrUpdateSubtaskTest(task_id='h5575', subtask_id='ddfg3')
        self.hepler3 = StoreOrUpdateSubtaskTest(task_id='poipd', subtask_id='jj435')

    def test_that_ensure_retry_of_locked_calls_should_handle_multiprocessing_calls(self):
        """
        This test checks, if when a function handling with database is calling multiple times in the same time (by
        different processes), decorator prevents of crash caused by race condition. Instead of crash processed
        should call function one by one. Database lock is created only for particular element, not the whole database
        """

        for i in range(5):  # pylint: disable=unused-variable
            t = Thread(target=self.hepler1.run_store_or_update_subtask, args=())
            t.start()

        for i in range(3):  # pylint: disable=unused-variable
            t = Thread(target=self.hepler1.run_store_or_update_subtask, args=())
            t.start()
            t = Thread(target=self.hepler2.run_store_or_update_subtask, args=())
            t.start()
            t = Thread(target=self.hepler3.run_store_or_update_subtask, args=())
            t.start()

        time.sleep(1)
        self.assertEqual(threading.active_count(), 1)
        database_handler = DatabaseHandler()
        database_handler.deactivate_communication_with_database()
