import mock

from django.conf import settings
from django.db import DatabaseError
from django.test import override_settings
from django.test import TransactionTestCase

from celery.exceptions import Retry
from golem_messages.factories.tasks import ReportComputedTaskFactory
from golem_messages.factories.tasks import TaskToComputeFactory

from common.helpers import get_current_utc_timestamp
from common.testing_helpers import generate_ecc_key_pair
from core.tests.constants_for_tests import ZERO_SIGNATURE
from core.exceptions import SubtaskStatusError
from core.message_handlers import store_subtask
from core.models import Subtask
from core.tasks import result_upload_finished
from core.tests.utils import ConcentIntegrationTestCase


@override_settings(
    CONCENT_MESSAGING_TIME = 10,
)
class VerifierVerificationResultTaskTest(ConcentIntegrationTestCase):

    multi_db = True

    def setUp(self):
        super().setUp()

        self.task_to_compute = self._get_deserialized_task_to_compute()

        self.subtask = store_subtask(
            task_id=self.task_to_compute.task_id,
            subtask_id=self.task_to_compute.subtask_id,
            provider_public_key=self.PROVIDER_PUBLIC_KEY,
            requestor_public_key=self.REQUESTOR_PUBLIC_KEY,
            state=Subtask.SubtaskState.ADDITIONAL_VERIFICATION,
            next_deadline=get_current_utc_timestamp() + settings.CONCENT_MESSAGING_TIME,
            task_to_compute=self.task_to_compute,
            report_computed_task=self._get_deserialized_report_computed_task(
                task_to_compute=self.task_to_compute,
            )
        )

    def test_that_result_upload_finished_should_change_result_upload_finished_field_on_subtask(self):
        assert self.subtask.result_upload_finished is False

        result_upload_finished(self.subtask.subtask_id)  # pylint: disable=no-value-for-parameter

        self.subtask.refresh_from_db()
        self.assertTrue(self.subtask.result_upload_finished)

    def test_that_result_upload_finished_should_raise_exception_for_non_existing_subtask(self):
        with self.assertRaises(Subtask.DoesNotExist):
            result_upload_finished(self._get_uuid('3'))  # pylint: disable=no-value-for-parameter

    def test_that_result_upload_finished_should_raise_exception_for_subtask_with_reported_state(self):
        self.subtask.state = Subtask.SubtaskState.FORCING_REPORT.name  # pylint: disable=no-member
        self.subtask.save()

        with self.assertRaises(SubtaskStatusError):
            result_upload_finished(self.subtask.subtask_id)  # pylint: disable=no-value-for-parameter

    def test_that_result_upload_finished_should_raise_exception_for_subtask_with_failed_state(self):
        self.task_to_compute = self._get_deserialized_task_to_compute()

        self.subtask = store_subtask(
            task_id=self.task_to_compute.task_id,
            subtask_id=self.task_to_compute.subtask_id,
            provider_public_key=self.PROVIDER_PUBLIC_KEY,
            requestor_public_key=self.REQUESTOR_PUBLIC_KEY,
            state=Subtask.SubtaskState.FAILED,
            next_deadline=None,
            task_to_compute=self.task_to_compute,
            report_computed_task=self._get_deserialized_report_computed_task(
                task_to_compute=self.task_to_compute,
            )
        )
        with mock.patch('core.tasks.logging.log') as log_info:
            result_upload_finished(self.subtask.subtask_id)  # pylint: disable=no-value-for-parameter
        self.assertIn('result_upload_finished called for Subtask, but it has status FAILED', str(log_info.call_args))

    def test_that_result_upload_finished_should_raise_exception_for_subtask_with_other_than_forcing_result_transfer_state(self):
        self.subtask.state = Subtask.SubtaskState.ADDITIONAL_VERIFICATION.name  # pylint: disable=no-member
        self.subtask.save()

        with mock.patch('core.tasks.logging.log') as log_warning:
            result_upload_finished(self.subtask.subtask_id)  # pylint: disable=no-value-for-parameter

        log_warning.assert_called()
        self.assertIn('instead of `FORCING_RESULT_TRANSFER', str(log_warning.call_args))
        self.assertIn('LoggingLevel.WARNING', str(log_warning.call_args))


class CoreResultUploadFinishedTaskTransactionTest(TransactionTestCase):

    multi_db = True

    def setUp(self):
        super().setUp()

        (self.PROVIDER_PRIVATE_KEY, self.PROVIDER_PUBLIC_KEY) = generate_ecc_key_pair()
        (self.REQUESTOR_PRIVATE_KEY, self.REQUESTOR_PUBLIC_KEY) = generate_ecc_key_pair()

        self.task_to_compute = TaskToComputeFactory(sig=ZERO_SIGNATURE)

        self.subtask = store_subtask(
            task_id=self.task_to_compute.task_id,
            subtask_id=self.task_to_compute.subtask_id,
            provider_public_key=self.PROVIDER_PUBLIC_KEY,
            requestor_public_key=self.REQUESTOR_PUBLIC_KEY,
            state=Subtask.SubtaskState.ADDITIONAL_VERIFICATION,
            next_deadline=get_current_utc_timestamp() + settings.CONCENT_MESSAGING_TIME,
            task_to_compute=self.task_to_compute,
            report_computed_task=ReportComputedTaskFactory(
                task_to_compute=self.task_to_compute,
            )
        )

    def test_that_result_upload_finished_querying_locked_row_should_reschedule_task(self):
        with mock.patch('core.tasks.Subtask.objects.select_for_update', side_effect=DatabaseError()):
            # Exception is raised because task is executed directly as a function.
            with self.assertRaises(Retry):
                result_upload_finished(self.subtask.subtask_id)  # pylint: disable=no-value-for-parameter
