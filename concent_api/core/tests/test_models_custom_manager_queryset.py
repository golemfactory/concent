from assertpy import assert_that
from django.conf import settings
from freezegun import freeze_time

from common.helpers import get_current_utc_timestamp
from core.message_handlers import store_subtask
from core.models import Subtask
from core.tests.utils import ConcentIntegrationTestCase
from core.utils import calculate_subtask_verification_time


class SubtaskWithTimingColumnsManagerQuerySetTest(ConcentIntegrationTestCase):
    def setUp(self):
        super().setUp()

        self.compute_task_def = self._get_deserialized_compute_task_def(
            task_id='1',
            subtask_id='8',
            deadline="2017-12-01 11:00:00+00"
        )
        self.task_to_compute = self._get_deserialized_task_to_compute(
            timestamp="2017-12-01 10:00:00+00",
            compute_task_def=self.compute_task_def,
        )
        self.report_computed_task = self._get_deserialized_report_computed_task(
            timestamp="2017-12-01 10:59:00+00",
            task_to_compute=self.task_to_compute,
        )

        with freeze_time("2017-12-01 11:00:00+00"):
            store_subtask(
                task_id='1',
                subtask_id='8',
                provider_public_key=self.PROVIDER_PUBLIC_KEY,
                requestor_public_key=self.REQUESTOR_PUBLIC_KEY,
                state=Subtask.SubtaskState.FORCING_REPORT,
                next_deadline=get_current_utc_timestamp() + settings.CONCENT_MESSAGING_TIME,
                task_to_compute=self.task_to_compute,
                report_computed_task=self.report_computed_task,
            )

        self.subtask_verification_time = calculate_subtask_verification_time(self.report_computed_task)
        self.download_deadline = 1512127820
        self.maximum_download_time = 4

    def test_subtask_verification_time_query(self):
        assert_that(
            Subtask.objects_with_timing_columns.first().subtask_verification_time
        ).is_equal_to(self.subtask_verification_time)

    def test_download_deadline_query(self):
        assert_that(
            Subtask.objects_with_timing_columns.first().download_deadline
        ).is_equal_to(self.download_deadline)

    def test_maximum_download_time_query(self):
        assert_that(
            Subtask.objects_with_timing_columns.first().maximum_download_time
        ).is_equal_to(self.maximum_download_time)
