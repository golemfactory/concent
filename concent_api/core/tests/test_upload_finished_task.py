import mock

from django.conf import settings
from freezegun import freeze_time

from core.message_handlers import store_subtask
from core.models import PendingResponse
from core.models import Subtask
from core.tasks import upload_finished
from core.tests.utils import ConcentIntegrationTestCase
from common.helpers import get_current_utc_timestamp
from common.helpers import parse_datetime_to_timestamp
from common.helpers import parse_timestamp_to_utc_datetime


class UploadFinishedTaskTest(ConcentIntegrationTestCase):

    multi_db = True

    def setUp(self):
        super().setUp()
        self.task_to_compute = self._get_deserialized_task_to_compute(task_id='1', subtask_id='8', )
        self.report_computed_task = self._get_deserialized_report_computed_task(
            task_to_compute=self.task_to_compute,
        )
        self.subtask = store_subtask(
            task_id=self._get_uuid(),
            subtask_id=self._get_uuid(),
            provider_public_key=self.PROVIDER_PUBLIC_KEY,
            requestor_public_key=self.REQUESTOR_PUBLIC_KEY,
            state=Subtask.SubtaskState.VERIFICATION_FILE_TRANSFER,
            next_deadline=get_current_utc_timestamp() + settings.CONCENT_MESSAGING_TIME,
            task_to_compute=self.task_to_compute,
            report_computed_task=self.report_computed_task
        )

    def test_that_scheduling_task_for_subtask_with_accepted_or_failed_or_additional_verification_state_should_log_warning_and_finish_task(self):
        for state in [
            Subtask.SubtaskState.ACCEPTED,
            Subtask.SubtaskState.FAILED,
            Subtask.SubtaskState.ADDITIONAL_VERIFICATION,
        ]:
            Subtask.objects.filter(subtask_id=self.subtask.subtask_id).update(state=state.name)  # pylint: disable=no-member
            self.subtask.refresh_from_db()

            with mock.patch('core.tasks.logging.warning') as logging_warning_mock:
                upload_finished(self.subtask.subtask_id)  # pylint: disable=no-value-for-parameter

            logging_warning_mock.assert_called_once_with(
                f'Subtask with ID {self.subtask.subtask_id} is expected to be in `VERIFICATION_FILE_TRANSFER` state, but was in {self.subtask.state}.'
            )

    def test_that_scheduling_task_for_subtask_with_unexpected_state_should_log_error_and_finish_task(self):
        Subtask.objects.filter(subtask_id=self.subtask.subtask_id).update(state=Subtask.SubtaskState.REPORTED.name)  # pylint: disable=no-member
        self.subtask.refresh_from_db()

        with mock.patch('core.tasks.logging.error') as logging_error_mock:
            upload_finished(self.subtask.subtask_id)  # pylint: disable=no-value-for-parameter

        logging_error_mock.assert_called_once_with(
            f'Subtask with ID {self.subtask.subtask_id} is expected to be in `VERIFICATION_FILE_TRANSFER` state, but was in {self.subtask.state}.'
        )

    def test_that_scheduling_task_for_subtask_before_deadline_should_change_subtask_state_and_schedule_upload_acknowledged_task(self):
        with freeze_time(parse_timestamp_to_utc_datetime(self.subtask.next_deadline.timestamp() - 1)):
            with mock.patch('core.tasks.tasks.upload_acknowledged.delay') as upload_acknowledged_delay_mock:
                upload_finished(self.subtask.subtask_id)  # pylint: disable=no-value-for-parameter

        self.subtask.refresh_from_db()
        self.assertEqual(self.subtask.state_enum, Subtask.SubtaskState.ADDITIONAL_VERIFICATION)
        upload_acknowledged_delay_mock.assert_called_once_with(
            subtask_id=self.subtask.subtask_id,
            source_file_size=self.report_computed_task.task_to_compute.size,
            source_package_hash=self.report_computed_task.task_to_compute.package_hash,
            result_file_size=self.report_computed_task.size,
            result_package_hash=self.report_computed_task.package_hash,
        )

    def test_that_scheduling_task_for_subtask_after_deadline_should_process_timeout(self):
        datetime = parse_timestamp_to_utc_datetime(get_current_utc_timestamp() + settings.CONCENT_MESSAGING_TIME + 1)
        with freeze_time(datetime):
            with mock.patch('core.tasks.payments_service.make_force_payment_to_provider', autospec=True) as payment_function_mock, \
                    mock.patch('core.tasks.update_timed_out_subtask'):
                upload_finished(self.subtask.subtask_id)  # pylint: disable=no-value-for-parameter

        self.subtask.refresh_from_db()
        self.assertEqual(self.subtask.state_enum, Subtask.SubtaskState.FAILED)
        self.assertEqual(self.subtask.next_deadline, None)
        self.assertEqual(PendingResponse.objects.count(), 2)
        self.assertTrue(PendingResponse.objects.filter(client=self.subtask.provider).exists())
        self.assertTrue(PendingResponse.objects.filter(client=self.subtask.requestor).exists())
        payment_function_mock.assert_called_once_with(
            requestor_eth_address=self.task_to_compute.requestor_ethereum_address,
            provider_eth_address=self.task_to_compute.provider_ethereum_address,
            value=self.task_to_compute.price,
            payment_ts=parse_datetime_to_timestamp(datetime),
        )
