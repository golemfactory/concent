from logging import getLogger
from unittest import TestCase

import mock
from golem_messages import dump
from golem_messages import load
from golem_messages import message
from golem_messages.factories import tasks

from common.logging import Message
from common.logging import serialize_message_to_dictionary
from common.logging import replace_element_to_unavailable_instead_of_none
from common.testing_helpers import generate_ecc_key_pair


(PROVIDER_PRIVATE_KEY,  PROVIDER_PUBLIC_KEY)  = generate_ecc_key_pair()
(REQUESTOR_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY) = generate_ecc_key_pair()


logger = getLogger(__name__)


class ReplaceElementToUnavailableInsteadOfNoneTestCase(TestCase):

    def test_that_all_none_should_be_changed_to_unavailable_when_only_args_given(self):  # pylint: disable=no-self-use
        mock_message = mock.create_autospec(spec=Message)
        m = mock.Mock()
        decorated = replace_element_to_unavailable_instead_of_none(m)
        decorated(None, 1, 'any string', mock_message, None, None, PROVIDER_PRIVATE_KEY)
        m.assert_called_once_with('-not available-', 1, 'any string', mock_message, '-not available-', '-not available-', PROVIDER_PRIVATE_KEY)

    def test_that_all_none_should_be_changed_to_unavailable_when_only_kwargs_given(self):  # pylint: disable=no-self-use
        mock_message = mock.create_autospec(spec=Message)
        m = mock.Mock()
        decorated = replace_element_to_unavailable_instead_of_none(m)
        decorated(a=None, b=1, c='any string', d=mock_message, e=None, f=None, g=PROVIDER_PRIVATE_KEY)
        m.assert_called_once_with(a='-not available-', b=1, c='any string', d=mock_message, e='-not available-', f='-not available-',
                                  g=PROVIDER_PRIVATE_KEY)

    def test_that_all_none_should_be_changed_to_unavailable_when_args_and_kwargs_given(self):  # pylint: disable=no-self-use
        mock_message = mock.create_autospec(spec=Message)
        m = mock.Mock()
        decorated = replace_element_to_unavailable_instead_of_none(m)
        decorated(None, 1, 'any string', mock_message, e=None, f=None, g=PROVIDER_PRIVATE_KEY)
        m.assert_called_once_with('-not available-', 1, 'any string', mock_message, e='-not available-', f='-not available-',
                                  g=PROVIDER_PRIVATE_KEY)


class SerializeMessageToDictionaryTestCase(TestCase):

    def setUp(self):
        super().setUp()

        compute_task_def = tasks.ComputeTaskDefFactory()
        task_to_compute = tasks.TaskToComputeFactory(
            compute_task_def=compute_task_def
        )
        serialized_task_to_compute = dump(task_to_compute, REQUESTOR_PRIVATE_KEY, PROVIDER_PUBLIC_KEY)
        deserialized_task_to_compute = load(serialized_task_to_compute, PROVIDER_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY,
                                            check_time=False)

        self.ack_report_computed_task = message.tasks.AckReportComputedTask()
        self.ack_report_computed_task.report_computed_task = message.ReportComputedTask(
            task_to_compute=deserialized_task_to_compute
        )

    def test_that_fields_uppercase_should_not_be_logged(self):
        self.assertIn('ENCRYPT', dir(self.ack_report_computed_task))
        self.assertIn('HDR_FORMAT', dir(self.ack_report_computed_task))
        dictionary = serialize_message_to_dictionary(self.ack_report_computed_task)
        self.assertNotIn('ENCRYPT', dictionary)
        self.assertNotIn('HDR_FORMAT', dictionary)

    def test_that_callable_fields_should_not_be_logged(self):
        self.assertTrue(callable(getattr(self.ack_report_computed_task, 'validate_ownership')))
        self.assertTrue(callable(getattr(self.ack_report_computed_task, 'verify_owners')))
        dictionary = serialize_message_to_dictionary(self.ack_report_computed_task)
        self.assertNotIn('validate_ownership', dictionary)
        self.assertNotIn('verify_owners', dictionary)

    def test_that_golem_messages_fields_should_be_logged(self):
        self.assertIn('task_to_compute', dir(self.ack_report_computed_task))
        self.assertIn('report_computed_task', dir(self.ack_report_computed_task))
        dictionary = serialize_message_to_dictionary(self.ack_report_computed_task)
        self.assertIn('ReportComputedTask', dictionary)
        self.assertIn('TaskToCompute', str(dictionary))
