from assertpy import assert_that
from django.conf import settings
from django.test import override_settings
import pytest

from golem_messages import constants
from golem_messages.factories.tasks import ReportComputedTaskFactory, TaskToComputeFactory
from common.helpers import get_current_utc_timestamp
from common.helpers import parse_datetime_to_timestamp
from common.testing_helpers import generate_ecc_key_pair
from core.message_handlers import store_subtask
from core.models import Subtask
from core.utils import calculate_maximum_download_time
from core.utils import calculate_subtask_verification_time
from core.utils import hex_to_bytes_convert


def store_report_computed_task_as_subtask(report_computed_task):
    store_subtask(
        task_id=report_computed_task.task_to_compute.task_id,
        subtask_id=report_computed_task.task_to_compute.subtask_id,
        provider_public_key=hex_to_bytes_convert(report_computed_task.task_to_compute.provider_public_key),
        requestor_public_key=hex_to_bytes_convert(report_computed_task.task_to_compute.requestor_public_key),
        state=Subtask.SubtaskState.FORCING_REPORT,
        next_deadline=get_current_utc_timestamp() + settings.CONCENT_MESSAGING_TIME,
        task_to_compute=report_computed_task.task_to_compute,
        report_computed_task=report_computed_task,
    )


class TestSubtaskWithTimingColumnsManagerQuerySet():
    @pytest.fixture(autouse=True)
    def setUp(self):

        (self.PROVIDER_PRIVATE_KEY, self.PROVIDER_PUBLIC_KEY) = generate_ecc_key_pair()
        (self.REQUESTOR_PRIVATE_KEY, self.REQUESTOR_PUBLIC_KEY) = generate_ecc_key_pair()

        self.report_computed_task = ReportComputedTaskFactory(
            sign__privkey=self.PROVIDER_PRIVATE_KEY,
            task_to_compute=TaskToComputeFactory(
                sign__privkey=self.REQUESTOR_PRIVATE_KEY,
            )
        )
        store_report_computed_task_as_subtask(self.report_computed_task)

    @pytest.mark.django_db
    @pytest.mark.parametrize(
        ('minimum_upload_rate', 'download_leadin_time', 'concent_messaging_time', 'custom_protocol_times'), [
            (48, 3, 2, True),
            (96, 6, 4, True),
            (192, 12, 8, True),
            (384, 24, 16, True),
        ])
    def test_that_subtask_verification_time_query_gives_correct_value(
        self,
        minimum_upload_rate,
        download_leadin_time,
        concent_messaging_time,
        custom_protocol_times
    ):
        with override_settings(
            MINIMUM_UPLOAD_RATE=minimum_upload_rate,
            DOWNLOAD_LEADIN_TIME=download_leadin_time,
            CONCENT_MESSAGING_TIME=concent_messaging_time,
            CUSTOM_PROTOCOL_TIMES=custom_protocol_times,
        ):
            subtask_verification_time = calculate_subtask_verification_time(self.report_computed_task)
            assert_that(
                Subtask.objects_with_timing_columns.
                get(subtask_id=self.report_computed_task.task_to_compute.subtask_id).subtask_verification_time
            ).is_equal_to(
                subtask_verification_time
            )

    @pytest.mark.django_db
    def test_that_subtask_verification_time_query_gives_correct_value_without_custom_protocol_times(self):
        with override_settings(
            CUSTOM_PROTOCOL_TIMES=False,
            CONCENT_MESSAGING_TIME=int(constants.CMT.total_seconds()),
            MINIMUM_UPLOAD_RATE=constants.DEFAULT_UPLOAD_RATE,
            DOWNLOAD_LEADIN_TIME=constants.DOWNLOAD_LEADIN_TIME.total_seconds(),
        ):
            subtask_verification_time = calculate_subtask_verification_time(self.report_computed_task)
            assert_that(
                Subtask.objects_with_timing_columns.
                get(subtask_id=self.report_computed_task.task_to_compute.subtask_id).subtask_verification_time
            ).is_equal_to(
                subtask_verification_time
            )

    @pytest.mark.django_db
    @pytest.mark.parametrize(
        ('minimum_upload_rate', 'download_leadin_time', 'concent_messaging_time', 'custom_protocol_times'), [
            (48, 3, 2, True),
            (96, 6, 4, True),
            (192, 12, 8, True),
            (384, 24, 16, True),
        ])
    def test_that_maximum_download_time_query_gives_correct_value(
        self,
        minimum_upload_rate,
        download_leadin_time,
        concent_messaging_time,
        custom_protocol_times,
    ):
        with override_settings(
            MINIMUM_UPLOAD_RATE=minimum_upload_rate,
            DOWNLOAD_LEADIN_TIME=download_leadin_time,
            CONCENT_MESSAGING_TIME=concent_messaging_time,
            CUSTOM_PROTOCOL_TIMES=custom_protocol_times,
        ):
            maximum_download_deadline = calculate_maximum_download_time(
                size=self.report_computed_task.size,
                rate=settings.MINIMUM_UPLOAD_RATE,
            )
            assert_that(
                Subtask.objects_with_timing_columns.
                get(subtask_id=self.report_computed_task.task_to_compute.subtask_id).maximum_download_time
            ).is_equal_to(
                maximum_download_deadline
            )

    @pytest.mark.django_db
    def test_that_maximum_download_time_query_gives_correct_value_without_custom_protocol_times(self):
        with override_settings(
            CUSTOM_PROTOCOL_TIMES=False,
            DOWNLOAD_LEADIN_TIME=int(constants.DOWNLOAD_LEADIN_TIME.total_seconds()),
        ):
            maximum_download_deadline = calculate_maximum_download_time(
                size=self.report_computed_task.size,
                rate=settings.MINIMUM_UPLOAD_RATE,
            )
            assert_that(
                Subtask.objects_with_timing_columns.
                get(subtask_id=self.report_computed_task.task_to_compute.subtask_id).maximum_download_time
            ).is_equal_to(
                maximum_download_deadline
            )

    @pytest.mark.django_db
    @pytest.mark.parametrize(
        ('minimum_upload_rate', 'download_leadin_time', 'concent_messaging_time', 'custom_protocol_times'), [
            (48, 3, 2, True),
            (96, 6, 4, True),
            (192, 12, 8, True),
            (384, 24, 16, True),
        ])
    def test_that_download_deadline_query_gives_correct_value(
        self,
        minimum_upload_rate,
        download_leadin_time,
        concent_messaging_time,
        custom_protocol_times
    ):
        with override_settings(
            MINIMUM_UPLOAD_RATE=minimum_upload_rate,
            DOWNLOAD_LEADIN_TIME=download_leadin_time,
            CONCENT_MESSAGING_TIME=concent_messaging_time,
            CUSTOM_PROTOCOL_TIMES=custom_protocol_times,
        ):
            assert_that(
                Subtask.objects_with_timing_columns.
                get(subtask_id=self.report_computed_task.task_to_compute.subtask_id).download_deadline
            ).is_equal_to(
                parse_datetime_to_timestamp(
                    Subtask.objects_with_timing_columns.get(
                        subtask_id=self.report_computed_task.task_to_compute.subtask_id
                    ).computation_deadline
                ) + Subtask.objects_with_timing_columns.get(
                    subtask_id=self.report_computed_task.task_to_compute.subtask_id
                ).subtask_verification_time,
            )

    @pytest.mark.django_db
    def test_that_download_deadline_query_gives_correct_value_without_protocol_custom_times(self):
        with override_settings(CUSTOM_PROTOCOL_TIMES=False):
            assert_that(
                Subtask.objects_with_timing_columns.
                get(subtask_id=self.report_computed_task.task_to_compute.subtask_id).download_deadline
            ).is_equal_to(
                parse_datetime_to_timestamp(
                    Subtask.objects_with_timing_columns.get(
                        subtask_id=self.report_computed_task.task_to_compute.subtask_id
                    ).computation_deadline
                ) + Subtask.objects_with_timing_columns.get(
                    subtask_id=self.report_computed_task.task_to_compute.subtask_id
                ).subtask_verification_time,
            )
