import mock

from django.conf import settings
from django.test import override_settings
from django.db import DatabaseError
from django.test import TransactionTestCase

from celery.exceptions import Retry
from freezegun import freeze_time
from golem_messages.factories.tasks import ReportComputedTaskFactory
from golem_messages.factories.tasks import TaskToComputeFactory

from common.constants import ErrorCode
from common.helpers import get_current_utc_timestamp
from common.helpers import parse_datetime_to_timestamp
from common.helpers import parse_timestamp_to_utc_datetime
from common.testing_helpers import generate_ecc_key_pair
from core.constants import VerificationResult
from core.message_handlers import store_subtask
from core.models import PendingResponse
from core.models import Subtask
from core.tasks import verification_result
from core.tests.utils import ConcentIntegrationTestCase


@override_settings(
    CONCENT_MESSAGING_TIME = 10,
)
class VerifierVerificationResultTaskTest(ConcentIntegrationTestCase):

    multi_db = True

    def setUp(self):
        super().setUp()

        task_id = self._get_uuid()
        subtask_id = self._get_uuid()

        report_computed_task = ReportComputedTaskFactory(
            subtask_id=subtask_id,
            task_id=task_id,
            sign__privkey=self.PROVIDER_PRIVATE_KEY,
            task_to_compute=TaskToComputeFactory(
                sign__privkey=self.REQUESTOR_PRIVATE_KEY
            ),
        )
        self.subtask = store_subtask(
            task_id=task_id,
            subtask_id=subtask_id,
            provider_public_key=self.PROVIDER_PUBLIC_KEY,
            requestor_public_key=self.REQUESTOR_PUBLIC_KEY,
            state=Subtask.SubtaskState.ADDITIONAL_VERIFICATION,
            next_deadline=get_current_utc_timestamp() + settings.CONCENT_MESSAGING_TIME,
            task_to_compute=report_computed_task.task_to_compute,
            report_computed_task=report_computed_task
        )

    def test_that_quering_for_subtask_with_accepted_state_should_log_warning_and_finish_task(self):
        Subtask.objects.filter(subtask_id=self.subtask.subtask_id).update(state=Subtask.SubtaskState.ACCEPTED.name)  # pylint: disable=no-member

        with mock.patch('core.tasks.logger.warning') as logging_warning_mock:
            verification_result(  # pylint: disable=no-value-for-parameter
                self.subtask.subtask_id,
                VerificationResult.MATCH.name,
            )
        logging_warning_mock.assert_called()
        self.assertIn(f'SUBTASK_ID: {self.subtask.subtask_id}. Verification has timed out',  str(logging_warning_mock.call_args_list))

    def test_that_quering_for_subtask_with_failed_state_should_log_error_and_finish_task(self):
        Subtask.objects.filter(subtask_id=self.subtask.subtask_id).update(state=Subtask.SubtaskState.FAILED.name)  # pylint: disable=no-member

        with mock.patch('core.tasks.logger.warning') as logging_warning_mock:
            verification_result(  # pylint: disable=no-value-for-parameter
                self.subtask.subtask_id,
                VerificationResult.MATCH.name,
            )

        logging_warning_mock.assert_called()
        self.assertIn(f'Verification result for subtask with ID {self.subtask.subtask_id} must have been already processed', str(logging_warning_mock.call_args_list))

    def test_that_quering_for_subtask_with_other_than_additional_verification_state_should_log_error_and_finish_task(self):
        Subtask.objects.filter(subtask_id=self.subtask.subtask_id).update(state=Subtask.SubtaskState.REPORTED.name)  # pylint: disable=no-member

        with mock.patch('core.tasks.logger.error') as logging_error_mock:
            verification_result(  # pylint: disable=no-value-for-parameter
                self.subtask.subtask_id,
                VerificationResult.MATCH.name,
            )

        logging_error_mock.assert_called()
        self.assertIn('Subtask is in state REPORTED instead in states ACCEPTED', str(logging_error_mock.call_args_list))

    def test_that_verification_result_mismatch_should_add_pending_messages_subtask_results_rejected(self):
        with freeze_time(parse_timestamp_to_utc_datetime(get_current_utc_timestamp())):
            verification_result(  # pylint: disable=no-value-for-parameter
                self.subtask.subtask_id,
                VerificationResult.MISMATCH.name,
            )

        self.subtask.refresh_from_db()
        self.assertEqual(self.subtask.state_enum, Subtask.SubtaskState.FAILED)
        self.assertEqual(self.subtask.next_deadline, None)
        self.assertEqual(PendingResponse.objects.count(), 2)
        self.assertTrue(PendingResponse.objects.filter(client=self.subtask.provider).exists())
        self.assertTrue(PendingResponse.objects.filter(client=self.subtask.requestor).exists())

    def test_that_verification_result_error_should_add_pending_messages_subtask_results_settled_and_change_subtask_state_to_accepted(self):
        with freeze_time(parse_timestamp_to_utc_datetime(get_current_utc_timestamp())):
            with mock.patch('core.tasks.logger.info') as logging_info_mock:
                verification_result(  # pylint: disable=no-value-for-parameter
                    self.subtask.subtask_id,
                    VerificationResult.ERROR.name,
                    'test',
                    ErrorCode.REQUEST_BODY_NOT_EMPTY.name,
                )

        self.subtask.refresh_from_db()
        self.assertEqual(self.subtask.state_enum, Subtask.SubtaskState.ACCEPTED)
        self.assertEqual(self.subtask.next_deadline, None)
        self.assertEqual(PendingResponse.objects.count(), 2)
        self.assertTrue(PendingResponse.objects.filter(client=self.subtask.provider).exists())
        self.assertTrue(PendingResponse.objects.filter(client=self.subtask.requestor).exists())

        self.assertEqual(logging_info_mock.call_count, 3)
        self.assertIn(f'SUBTASK_ID: {self.subtask.subtask_id}. Verification_result_task starts. Result: ERROR', str(logging_info_mock.call_args_list))
        self.assertIn(f'SUBTASK_ID: {self.subtask.subtask_id}. Verification_result_task ends. Result: ERROR', str(logging_info_mock.call_args_list))

    def test_that_verification_result_match_should_add_pending_messages_subtask_results_settled_and_change_subtask_state_to_accepted(self):
        with freeze_time(parse_timestamp_to_utc_datetime(get_current_utc_timestamp())):
            verification_result(  # pylint: disable=no-value-for-parameter
                self.subtask.subtask_id,
                VerificationResult.MATCH.name,
            )

        self.subtask.refresh_from_db()
        self.assertEqual(self.subtask.state_enum, Subtask.SubtaskState.ACCEPTED)
        self.assertEqual(self.subtask.next_deadline, None)
        self.assertEqual(PendingResponse.objects.count(), 2)
        self.assertTrue(PendingResponse.objects.filter(client=self.subtask.provider).exists())
        self.assertTrue(PendingResponse.objects.filter(client=self.subtask.requestor).exists())

    def test_that_verification_result_after_deadline_should_add_pending_messages_subtask_results_settled_and_change_subtask_state_to_accepted(self):
        with freeze_time(
            parse_timestamp_to_utc_datetime(
                parse_datetime_to_timestamp(self.subtask.next_deadline) + 1
            )
        ):
            verification_result(  # pylint: disable=no-value-for-parameter
                self.subtask.subtask_id,
                VerificationResult.MATCH.name,
            )

        self.subtask.refresh_from_db()
        self.assertEqual(self.subtask.state_enum, Subtask.SubtaskState.ACCEPTED)
        self.assertEqual(self.subtask.next_deadline, None)
        self.assertEqual(PendingResponse.objects.count(), 2)
        self.assertTrue(PendingResponse.objects.filter(client=self.subtask.provider).exists())
        self.assertTrue(PendingResponse.objects.filter(client=self.subtask.requestor).exists())


class VerifierVerificationResultTaskTransactionTest(TransactionTestCase):

    multi_db = True

    def setUp(self):
        super().setUp()

        (self.PROVIDER_PRIVATE_KEY, self.PROVIDER_PUBLIC_KEY) = generate_ecc_key_pair()
        (self.REQUESTOR_PRIVATE_KEY, self.REQUESTOR_PUBLIC_KEY) = generate_ecc_key_pair()

        task_to_compute = TaskToComputeFactory(sign__privkey=self.REQUESTOR_PRIVATE_KEY)

        self.subtask = store_subtask(
            task_id=task_to_compute.task_id,
            subtask_id=task_to_compute.subtask_id,
            provider_public_key=self.PROVIDER_PUBLIC_KEY,
            requestor_public_key=self.REQUESTOR_PUBLIC_KEY,
            state=Subtask.SubtaskState.ADDITIONAL_VERIFICATION,
            next_deadline=get_current_utc_timestamp() + settings.CONCENT_MESSAGING_TIME,
            task_to_compute=task_to_compute,
            report_computed_task=ReportComputedTaskFactory(
                subtask_id=task_to_compute.subtask_id,
                task_to_compute=task_to_compute,
                sign__privkey=self.PROVIDER_PRIVATE_KEY,
            )
        )

    def test_that_verification_result_querying_locked_row_should_reschedule_task(self):
        with mock.patch('core.tasks.Subtask.objects.select_for_update', side_effect=DatabaseError()):
            # Exception is raised because task is executed directly as a function.
            with self.assertRaises(Retry):
                verification_result(  # pylint: disable=no-value-for-parameter
                    self.subtask.subtask_id,
                    VerificationResult.MATCH.name,
                )


class VerificationResultAssertionTest(ConcentIntegrationTestCase):

    multi_db = True

    def setUp(self):
        super().setUp()

        (self.PROVIDER_PRIVATE_KEY, self.PROVIDER_PUBLIC_KEY) = generate_ecc_key_pair()
        (self.REQUESTOR_PRIVATE_KEY, self.REQUESTOR_PUBLIC_KEY) = generate_ecc_key_pair()

        task_to_compute = TaskToComputeFactory(sign__privkey=self.REQUESTOR_PRIVATE_KEY)

        self.subtask = store_subtask(
            task_id=task_to_compute.task_id,
            subtask_id=task_to_compute.subtask_id,
            provider_public_key=self.PROVIDER_PUBLIC_KEY,
            requestor_public_key=self.REQUESTOR_PUBLIC_KEY,
            state=Subtask.SubtaskState.ADDITIONAL_VERIFICATION,
            next_deadline=get_current_utc_timestamp() + settings.CONCENT_MESSAGING_TIME,
            task_to_compute=task_to_compute,
            report_computed_task=ReportComputedTaskFactory(
                subtask_id=task_to_compute.subtask_id,
                task_to_compute=task_to_compute,
                sign__privkey=self.PROVIDER_PRIVATE_KEY,
            )
        )

    def test_that_assertion_in_verification_result_method_doesnt_rise_exception_when_empty_string_is_passed_in_error_message(self):
        try:
            verification_result(  # pylint: disable=no-value-for-parameter
                self.subtask.subtask_id,
                VerificationResult.ERROR.name,
                '',
                'error_code',
            )
        except Exception:  # pylint: disable=broad-except
            self.fail()

    def test_that_assertion_in_verification_result_method_doesnt_rise_exception_when_empty_string_is_passed_in_error_code(self):
        try:
            verification_result(  # pylint: disable=no-value-for-parameter
                self.subtask.subtask_id,
                VerificationResult.ERROR.name,
                'error_message',
                '',
            )
        except Exception:  # pylint: disable=broad-except
            self.fail()
