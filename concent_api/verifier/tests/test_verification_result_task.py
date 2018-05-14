import mock

from django.conf import settings
from django.db import DatabaseError
from django.test import TransactionTestCase

from celery.exceptions import Retry
from golem_messages.factories.tasks import TaskToComputeFactory

from core.message_handlers import store_subtask
from core.models import PendingResponse
from core.models import Subtask
from core.tests.utils import ConcentIntegrationTestCase
from utils.constants import ErrorCode
from utils.helpers import get_current_utc_timestamp
from utils.testing_helpers import generate_ecc_key_pair
from verifier.constants import VerificationResult
from verifier.constants import VERIFICATION_RESULT_SUBTASK_STATE_ACCEPTED_LOG_MESSAGE
from verifier.constants import VERIFICATION_RESULT_SUBTASK_STATE_FAILED_LOG_MESSAGE
from verifier.constants import VERIFICATION_RESULT_SUBTASK_STATE_UNEXPECTED_LOG_MESSAGE
from verifier.tasks import verification_result


class VerifierVerificationResultTaskTest(ConcentIntegrationTestCase):

    multi_db = True

    def setUp(self):
        super().setUp()
        self.subtask = store_subtask(
            task_id='1',
            subtask_id='8',
            provider_public_key=self.PROVIDER_PUBLIC_KEY,
            requestor_public_key=self.REQUESTOR_PUBLIC_KEY,
            state=Subtask.SubtaskState.ADDITIONAL_VERIFICATION,
            next_deadline=get_current_utc_timestamp() + settings.CONCENT_MESSAGING_TIME,
            task_to_compute=self._get_deserialized_task_to_compute(
                task_id='1',
                subtask_id='8',
            ),
            report_computed_task=self._get_deserialized_report_computed_task(
                subtask_id='8',
            )
        )

    def test_that_quering_for_subtask_with_accepted_state_should_log_warning_and_finish_task(self):
        Subtask.objects.filter(subtask_id=self.subtask.subtask_id).update(state=Subtask.SubtaskState.ACCEPTED.name)  # pylint: disable=no-member

        with mock.patch('verifier.tasks.logger.warning') as logging_warning_mock:
            verification_result(  # pylint: disable=no-value-for-parameter
                self.subtask.subtask_id,
                VerificationResult.MATCH,
            )

        logging_warning_mock.assert_called_once_with(
            VERIFICATION_RESULT_SUBTASK_STATE_ACCEPTED_LOG_MESSAGE.format(self.subtask.subtask_id)
        )

    def test_that_quering_for_subtask_with_failed_state_should_log_error_and_finish_task(self):
        Subtask.objects.filter(subtask_id=self.subtask.subtask_id).update(state=Subtask.SubtaskState.FAILED.name)  # pylint: disable=no-member

        with mock.patch('verifier.tasks.logger.warning') as logging_warning_mock:
            verification_result(  # pylint: disable=no-value-for-parameter
                self.subtask.subtask_id,
                VerificationResult.MATCH,
            )

        logging_warning_mock.assert_called_once_with(
            VERIFICATION_RESULT_SUBTASK_STATE_FAILED_LOG_MESSAGE.format(self.subtask.subtask_id)
        )

    def test_that_quering_for_subtask_with_other_than_additional_verification_state_should_log_error_and_finish_task(self):
        Subtask.objects.filter(subtask_id=self.subtask.subtask_id).update(state=Subtask.SubtaskState.REPORTED.name)  # pylint: disable=no-member

        with mock.patch('verifier.tasks.logger.error') as logging_error_mock:
            verification_result(  # pylint: disable=no-value-for-parameter
                self.subtask.subtask_id,
                VerificationResult.MATCH,
            )

        logging_error_mock.assert_called_once_with(
            VERIFICATION_RESULT_SUBTASK_STATE_UNEXPECTED_LOG_MESSAGE.format(
                self.subtask.subtask_id,
                Subtask.SubtaskState.REPORTED.name,  # pylint: disable=no-member
            )
        )

    def test_that_verification_result_mismatch_should_add_pending_messages_subtask_results_rejected(self):
        verification_result(  # pylint: disable=no-value-for-parameter
            self.subtask.subtask_id,
            VerificationResult.MISMATCH,
        )

        self.subtask.refresh_from_db()
        self.assertEqual(self.subtask.state_enum, Subtask.SubtaskState.FAILED)
        self.assertEqual(self.subtask.next_deadline, None)
        self.assertEqual(PendingResponse.objects.count(), 2)
        self.assertTrue(PendingResponse.objects.filter(client=self.subtask.provider).exists())
        self.assertTrue(PendingResponse.objects.filter(client=self.subtask.requestor).exists())

    def test_that_verification_result_error_should_add_pending_messages_subtask_results_settled_and_change_subtask_state_to_accepted(self):
        with mock.patch('verifier.tasks.logger.info') as logging_info_mock:
            verification_result(  # pylint: disable=no-value-for-parameter
                self.subtask.subtask_id,
                VerificationResult.ERROR,
                'test',
                ErrorCode.REQUEST_BODY_NOT_EMPTY,
            )

        self.subtask.refresh_from_db()
        self.assertEqual(self.subtask.state_enum, Subtask.SubtaskState.ACCEPTED)
        self.assertEqual(self.subtask.next_deadline, None)
        self.assertEqual(PendingResponse.objects.count(), 2)
        self.assertTrue(PendingResponse.objects.filter(client=self.subtask.provider).exists())
        self.assertTrue(PendingResponse.objects.filter(client=self.subtask.requestor).exists())

        self.assertEqual(logging_info_mock.call_count, 3)
        self.assertEqual(
            logging_info_mock.call_args_list[1][0][0],
            f'verification_result_task processing error result with: '
            f'SUBTASK_ID {self.subtask.subtask_id} -- RESULT {VerificationResult.ERROR} -- ERROR MESSAGE test -- ERROR CODE {ErrorCode.REQUEST_BODY_NOT_EMPTY}'
        )

    def test_that_verification_result_match_should_add_pending_messages_subtask_results_settled_and_change_subtask_state_to_accepted(self):
        verification_result(  # pylint: disable=no-value-for-parameter
            self.subtask.subtask_id,
            VerificationResult.MATCH,
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

        self.subtask = store_subtask(
            task_id='1',
            subtask_id='8',
            provider_public_key=self.PROVIDER_PUBLIC_KEY,
            requestor_public_key=self.REQUESTOR_PUBLIC_KEY,
            state=Subtask.SubtaskState.ADDITIONAL_VERIFICATION,
            next_deadline=get_current_utc_timestamp() + settings.CONCENT_MESSAGING_TIME,
            task_to_compute=TaskToComputeFactory(
                task_id='1',
                subtask_id='8',
            )
        )

    def test_that_verification_result_querying_locked_row_should_reschedule_task(self):
        with mock.patch('verifier.tasks.Subtask.objects.select_for_update', side_effect=DatabaseError()):
            # Exception is raised because task is executed directly as a function.
            with self.assertRaises(Retry):
                verification_result(  # pylint: disable=no-value-for-parameter
                    self.subtask.subtask_id,
                    VerificationResult.MATCH,
                )
