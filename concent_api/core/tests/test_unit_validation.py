from unittest import TestCase

import mock

from golem_messages.message.tasks import ReportComputedTask
from golem_messages.message.tasks import SubtaskResultsRejected
from golem_messages.message.tasks import TaskToCompute

from core.constants import ETHEREUM_ADDRESS_LENGTH
from core.exceptions import Http400
from core.validation import validate_ethereum_addresses
from core.validation import validate_golem_message_subtask_results_rejected
from core.validation import validate_subtask_price_task_to_compute


def mocked_message_with_price(price):
    message_with_price = mock.create_autospec(spec=TaskToCompute, spec_set=True)
    message_with_price.price = price
    return message_with_price


class TestValidateGolemMessageSubtaskResultsRejected(TestCase):
    def test_that_exception_is_raised_when_subtask_results_rejected_is_of_wrong_type(self):
        with self.assertRaises(Http400):
            validate_golem_message_subtask_results_rejected(None)

    def test_that_exception_is_raised_when_subtask_results_rejected_contains_invalid_task_to_compute(self):
        report_computed_task = ReportComputedTask(task_to_compute=TaskToCompute())
        subtask_results_rejected = SubtaskResultsRejected(report_computed_task=report_computed_task)
        with self.assertRaises(Http400):
            validate_golem_message_subtask_results_rejected(subtask_results_rejected)


class ValidatorsTest(TestCase):
    def test_that_function_raises_http400_when_ethereum_addres_has_wrong_type(self):
        with self.assertRaises(Http400):
            validate_ethereum_addresses(int('1' * ETHEREUM_ADDRESS_LENGTH), 'a' * ETHEREUM_ADDRESS_LENGTH)

        with self.assertRaises(Http400):
            validate_ethereum_addresses('a' * ETHEREUM_ADDRESS_LENGTH, int('1' * ETHEREUM_ADDRESS_LENGTH))

        with self.assertRaises(Http400):
            validate_ethereum_addresses(int('1' * ETHEREUM_ADDRESS_LENGTH), int('1' * ETHEREUM_ADDRESS_LENGTH))

    def test_that_function_raises_http400_when_ethereum_addres_has_wrong_length(self):
        with self.assertRaises(Http400):
            validate_ethereum_addresses('a' * 5, 'b' * 5)

        with self.assertRaises(Http400):
            validate_ethereum_addresses('a' * 5, 'b' * ETHEREUM_ADDRESS_LENGTH)

        with self.assertRaises(Http400):
            validate_ethereum_addresses('a' * ETHEREUM_ADDRESS_LENGTH, 'b' * 5)

    def test_that_function_raise_http400_when_price_is_not_int(self):
        with self.assertRaises(Http400):
            validate_subtask_price_task_to_compute(mocked_message_with_price('5'))

    def test_that_function_raise_http400_when_price_is_negative(self):
        with self.assertRaises(Http400):
            validate_subtask_price_task_to_compute(mocked_message_with_price(-5))

    def test_that_function_will_not_return_anything_when_price_is_zero(self):  # pylint: disable=no-self-use
        validate_subtask_price_task_to_compute(mocked_message_with_price(0))
