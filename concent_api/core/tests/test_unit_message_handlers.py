from unittest import TestCase

from django.conf import settings
from django.test import override_settings
from django.test.utils import freeze_time
from golem_messages import message

from common.helpers import parse_timestamp_to_utc_datetime
from core.exceptions import GolemMessageValidationError
from core.message_handlers import are_items_unique
from core.message_handlers import update_subtask
from core.message_handlers import store_subtask
from core.models import Subtask
from core.tests.utils import ConcentIntegrationTestCase
from core.tests.utils import parse_iso_date_to_timestamp
from core.utils import hex_to_bytes_convert
from core.validation import validate_reject_report_computed_task


class TestMessageHandlers(TestCase):
    def test_that_function_returns_true_when_ids_are_diffrent(self):
        response = are_items_unique([1, 2, 3, 4, 5])
        self.assertTrue(response)

    def test_that_function_returns_false_when_ids_are_the_same(self):
        response = are_items_unique([1, 2, 3, 2, 5])
        self.assertFalse(response)


@override_settings(
    CONCENT_MESSAGING_TIME=10,  # seconds
)
class TestSubtaskStoreAndUpdate(ConcentIntegrationTestCase):
    def setUp(self):
        super().setUp()
        self.compute_task_def = self._get_deserialized_compute_task_def(
            task_id='1',
            deadline="2017-12-01 11:00:00"
        )

        self.task_to_compute_timestamp = "2017-12-01 10:00:00"
        self.task_to_compute = self._get_deserialized_task_to_compute(
            timestamp=self.task_to_compute_timestamp,
            compute_task_def=self.compute_task_def,
        )

        self.report_computed_task_timestamp = "2017-12-01 11:01:00"
        self.report_computed_task = self._get_deserialized_report_computed_task(
            timestamp=self.report_computed_task_timestamp,
            task_to_compute=self.task_to_compute,
        )

        with freeze_time(self.task_to_compute_timestamp):
            self.force_get_task_result = message.concents.ForceGetTaskResult(
                report_computed_task=self.report_computed_task,
            )

        self.provider_public_key = hex_to_bytes_convert(self.task_to_compute.provider_public_key)
        self.requestor_public_key = hex_to_bytes_convert(self.task_to_compute.requestor_public_key)

    def test_that_messages_are_stored_with_correct_timestamps(self):
        subtask = store_subtask(
            task_id=self.task_to_compute.compute_task_def['task_id'],
            subtask_id=self.task_to_compute.compute_task_def['subtask_id'],
            provider_public_key=self.provider_public_key,
            requestor_public_key=self.requestor_public_key,
            state=Subtask.SubtaskState.FORCING_REPORT,
            next_deadline=int(self.task_to_compute.compute_task_def['deadline']) + settings.CONCENT_MESSAGING_TIME,
            task_to_compute=self.task_to_compute,
            report_computed_task=self.report_computed_task,
        )
        self.assertEqual(
            parse_iso_date_to_timestamp(subtask.task_to_compute.timestamp.isoformat()),
            parse_iso_date_to_timestamp(self.task_to_compute_timestamp)
        )
        self.assertEqual(
            parse_iso_date_to_timestamp(subtask.report_computed_task.timestamp.isoformat()),
            parse_iso_date_to_timestamp(self.report_computed_task_timestamp)
        )

    def test_that_update_subtask_passes_validations_from_passive_to_active_state(self):
        subtask = store_subtask(
            task_id=self.task_to_compute.compute_task_def['task_id'],
            subtask_id=self.task_to_compute.compute_task_def['subtask_id'],
            provider_public_key=self.provider_public_key,
            requestor_public_key=self.requestor_public_key,
            state=Subtask.SubtaskState.REPORTED,
            next_deadline=None,
            task_to_compute=self.task_to_compute,
            report_computed_task=self.report_computed_task,
        )
        subtask_state = Subtask.objects.get(subtask_id=self.task_to_compute.compute_task_def['subtask_id']).state
        self.assertEqual(subtask_state, Subtask.SubtaskState.REPORTED.name)
        self.assertEqual(subtask.next_deadline, None)

        next_deadline = int(self.task_to_compute.compute_task_def['deadline']) + settings.CONCENT_MESSAGING_TIME
        update_subtask(
            subtask=subtask,
            state=Subtask.SubtaskState.FORCING_RESULT_TRANSFER,
            next_deadline=next_deadline,
            force_get_task_result=self.force_get_task_result,
            set_next_deadline=True,
        )
        subtask_state = Subtask.objects.get(subtask_id=self.task_to_compute.compute_task_def['subtask_id']).state
        self.assertEqual(subtask_state, Subtask.SubtaskState.FORCING_RESULT_TRANSFER.name)
        self.assertEqual(subtask.next_deadline, parse_timestamp_to_utc_datetime(next_deadline))

    def test_that_update_subtask_passes_validations_from_active_to_passive_state(self):
        next_deadline = int(self.task_to_compute.compute_task_def['deadline']) + settings.CONCENT_MESSAGING_TIME
        subtask = store_subtask(
            task_id=self.task_to_compute.compute_task_def['task_id'],
            subtask_id=self.task_to_compute.compute_task_def['subtask_id'],
            provider_public_key=self.provider_public_key,
            requestor_public_key=self.requestor_public_key,
            state=Subtask.SubtaskState.FORCING_REPORT,
            next_deadline=next_deadline,
            task_to_compute=self.task_to_compute,
            report_computed_task=self.report_computed_task,
        )
        subtask_state = Subtask.objects.get(subtask_id=self.task_to_compute.compute_task_def['subtask_id']).state
        self.assertEqual(subtask_state, Subtask.SubtaskState.FORCING_REPORT.name)
        self.assertEqual(subtask.next_deadline, parse_timestamp_to_utc_datetime(next_deadline))

        update_subtask(
            subtask=subtask,
            state=Subtask.SubtaskState.REPORTED,
            next_deadline=None,
            set_next_deadline=True,
        )
        subtask_state = Subtask.objects.get(subtask_id=self.task_to_compute.compute_task_def['subtask_id']).state
        self.assertEqual(subtask_state, Subtask.SubtaskState.REPORTED.name)
        self.assertEqual(subtask.next_deadline, None)


class TestValidateRejectReportComputedTask(ConcentIntegrationTestCase):

    def test_that_validation_passes_if_correct_message_given(self):
        correct_reject_reported_computed_task = self._get_deserialized_reject_report_computed_task(
            reason=message.tasks.RejectReportComputedTask.REASON.SubtaskTimeLimitExceeded,
            task_to_compute=self._get_deserialized_task_to_compute()
        )
        validate_reject_report_computed_task(correct_reject_reported_computed_task)

    def test_that_validation_raises_error_if_invalid_reason_instance_given(self):
        incorrect_reject_reported_computed_task = self._get_deserialized_reject_report_computed_task(
            reason=message.tasks.CannotAssignTask.REASON.NotMyTask,
            task_to_compute=self._get_deserialized_task_to_compute()
        )
        with self.assertRaises(GolemMessageValidationError):
            validate_reject_report_computed_task(incorrect_reject_reported_computed_task)

    def test_that_validation_raises_error_if_reason_is_none(self):
        incorrect_reject_reported_computed_task = self._get_deserialized_reject_report_computed_task(
            reason=None,
            task_to_compute=self._get_deserialized_task_to_compute()
        )
        with self.assertRaises(GolemMessageValidationError):
            validate_reject_report_computed_task(incorrect_reject_reported_computed_task)
