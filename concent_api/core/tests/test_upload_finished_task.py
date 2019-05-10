import mock

from django.conf import settings
from freezegun import freeze_time
from golem_messages.factories.concents import SubtaskResultsVerifyFactory
from golem_messages.factories.tasks import TaskToComputeFactory, ReportComputedTaskFactory, \
    SubtaskResultsRejectedFactory
from golem_messages.message.tasks import SubtaskResultsRejected

from common.helpers import get_current_utc_timestamp
from common.helpers import parse_datetime_to_timestamp
from common.helpers import parse_timestamp_to_utc_datetime
from core.message_handlers import store_subtask
from core.models import PendingResponse
from core.models import Subtask
from core.tasks import upload_finished
from core.tests.utils import ConcentIntegrationTestCase


class UploadFinishedTaskTest(ConcentIntegrationTestCase):

    multi_db = True

    def setUp(self):
        super().setUp()
        task_to_compute = TaskToComputeFactory(sign__privkey=self.REQUESTOR_PRIVATE_KEY)
        report_computed_task = ReportComputedTaskFactory(
            subtask_id=task_to_compute.subtask_id,
            task_to_compute=task_to_compute,
            sign__privkey=self.PROVIDER_PRIVATE_KEY,
        )
        subtask_results_rejected = SubtaskResultsRejectedFactory(
            reason=SubtaskResultsRejected.REASON.VerificationNegative,
            report_computed_task=report_computed_task,
        )
        subtask_results_verify = SubtaskResultsVerifyFactory(
            subtask_results_rejected=subtask_results_rejected,
        )

        self.subtask = store_subtask(
            task_id=task_to_compute.task_id,
            subtask_id=task_to_compute.subtask_id,
            provider_public_key=self.PROVIDER_PUBLIC_KEY,
            requestor_public_key=self.REQUESTOR_PUBLIC_KEY,
            state=Subtask.SubtaskState.VERIFICATION_FILE_TRANSFER,
            next_deadline=get_current_utc_timestamp() + settings.CONCENT_MESSAGING_TIME,
            task_to_compute=task_to_compute,
            report_computed_task=report_computed_task,
            subtask_results_rejected=subtask_results_rejected,
            subtask_results_verify=subtask_results_verify,
        )

    def test_that_scheduling_task_for_subtask_with_accepted_or_failed_or_additional_verification_state_should_log_warning_and_finish_task(self):
        for state in [
            Subtask.SubtaskState.ACCEPTED,
            Subtask.SubtaskState.FAILED,
            Subtask.SubtaskState.ADDITIONAL_VERIFICATION,
        ]:
            Subtask.objects.filter(subtask_id=self.subtask.subtask_id).update(state=state.name)  # pylint: disable=no-member
            self.subtask.refresh_from_db()

            with mock.patch('core.tasks.logging.log') as logging_warning_mock:
                upload_finished(self.subtask.subtask_id)  # pylint: disable=no-value-for-parameter

            logging_warning_mock.assert_called()
            self.assertIn(f'Subtask is expected to be in `VERIFICATION_FILE_TRANSFER` state, but was in {self.subtask.state}.', str(logging_warning_mock.mock_calls))

    def test_that_scheduling_task_for_subtask_with_unexpected_state_should_log_error_and_finish_task(self):
        Subtask.objects.filter(subtask_id=self.subtask.subtask_id).update(state=Subtask.SubtaskState.REPORTED.name)  # pylint: disable=no-member
        self.subtask.refresh_from_db()

        with mock.patch('core.tasks.logging.log') as logging_error_mock:
            upload_finished(self.subtask.subtask_id)  # pylint: disable=no-value-for-parameter

        logging_error_mock.assert_called()
        self.assertIn(f'Subtask is expected to be in `VERIFICATION_FILE_TRANSFER` state, but was in {self.subtask.state}.', str(logging_error_mock.mock_calls))

    def test_that_scheduling_task_for_subtask_before_deadline_should_change_subtask_state_and_schedule_upload_acknowledged_task(self):
        with freeze_time(
            parse_timestamp_to_utc_datetime(
                parse_datetime_to_timestamp(self.subtask.next_deadline) - 2
            )
        ):
            with mock.patch('core.tasks.transaction.on_commit') as transaction_on_commit:
                upload_finished(self.subtask.subtask_id)  # pylint: disable=no-value-for-parameter

        self.subtask.refresh_from_db()
        self.assertEqual(self.subtask.state_enum, Subtask.SubtaskState.ADDITIONAL_VERIFICATION)
        transaction_on_commit.assert_called_once()

    def test_that_scheduling_task_for_subtask_after_deadline_should_process_timeout(self):
        datetime = parse_timestamp_to_utc_datetime(get_current_utc_timestamp() + settings.CONCENT_MESSAGING_TIME + 1)
        with freeze_time(datetime):
            upload_finished(self.subtask.subtask_id)  # pylint: disable=no-value-for-parameter

        self.subtask.refresh_from_db()
        self.assertEqual(self.subtask.state_enum, Subtask.SubtaskState.FAILED)
        self.assertEqual(self.subtask.next_deadline, None)
        self.assertEqual(PendingResponse.objects.count(), 2)
        self.assertTrue(PendingResponse.objects.filter(client=self.subtask.provider).exists())
        self.assertTrue(PendingResponse.objects.filter(client=self.subtask.requestor).exists())
