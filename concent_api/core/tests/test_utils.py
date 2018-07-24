import datetime
import mock

from django.conf import settings
from django.test import override_settings
from django.test import TestCase

from golem_messages import constants
from golem_messages import helpers

from core.tests.utils import ConcentIntegrationTestCase
from core.utils import calculate_maximum_download_time
from core.utils import calculate_subtask_verification_time
from common.helpers import get_current_utc_timestamp
from common.helpers import parse_timestamp_to_utc_datetime
from common.testing_helpers import generate_ecc_key_pair

(CONCENT_PRIVATE_KEY, CONCENT_PUBLIC_KEY) = generate_ecc_key_pair()


class CalculateMaximumDownloadTimeTestCase(TestCase):

    @override_settings(
        CUSTOM_PROTOCOL_TIMES=False
    )  # pylint: disable=no-self-use
    def test_that_calculate_maximum_download_time_will_call_maximum_download_time_when_custom_protocol_times_is_off(self):
        with mock.patch('core.utils.maximum_download_time', return_value=datetime.timedelta()) as mock_maximum_download_time:
            calculate_maximum_download_time(
                size=1,
                rate=settings.MINIMUM_UPLOAD_RATE,
            )

        mock_maximum_download_time.assert_called_once_with(
            1,
            settings.MINIMUM_UPLOAD_RATE,
        )

    @override_settings(
        CUSTOM_PROTOCOL_TIMES=True
    )  # pylint: disable=no-self-use
    def test_that_calculate_maximum_download_time_will_not_call_maximum_download_time_when_custom_protocol_times_is_on(self):
        with mock.patch('core.utils.maximum_download_time', return_value=datetime.timedelta()) as mock_maximum_download_time:
            calculate_maximum_download_time(
                size=1,
                rate=settings.MINIMUM_UPLOAD_RATE,
            )

        mock_maximum_download_time.assert_not_called()

    @override_settings(
        DOWNLOAD_LEADIN_TIME=int(constants.DOWNLOAD_LEADIN_TIME.total_seconds()),
        MINIMUM_UPLOAD_RATE=constants.DEFAULT_UPLOAD_RATE,
    )
    def test_that_both_maximum_download_time_implementation_should_return_same_result_when_golem_messages_constants_match_concent_settings(self):
        for size, rate in [
            (7, 19),
            (10, 10),
            (19, 7),
            (100, 100),
            (331, 331),
            (1000, 1000),
            (9999, 9999),
        ]:
            self.assertEqual(
                calculate_maximum_download_time(size, rate),
                int(helpers.maximum_download_time(size, rate).total_seconds())
            )
            self.assertEqual(
                calculate_maximum_download_time(size, settings.MINIMUM_UPLOAD_RATE),
                calculate_maximum_download_time(size, constants.DEFAULT_UPLOAD_RATE),
            )


class CalculateSubtaskVerificationTimeTestCase(ConcentIntegrationTestCase):

    def setUp(self):
        super().setUp()
        self.report_computed_task = self._get_deserialized_report_computed_task()

    @override_settings(
        CUSTOM_PROTOCOL_TIMES=False
    )
    def test_that_calculate_subtask_verification_time_will_call_subtask_verification_time_when_custom_protocol_times_is_off(self):
        with mock.patch('core.utils.subtask_verification_time', return_value=datetime.timedelta()) as mock_subtask_verification_time:
            calculate_subtask_verification_time(self.report_computed_task)

        mock_subtask_verification_time.assert_called_once_with(self.report_computed_task)

    @override_settings(
        CUSTOM_PROTOCOL_TIMES=True
    )
    def test_that_calculate_subtask_verification_time_will_not_call_subtask_verification_time_when_custom_protocol_times_is_on(self):
        with mock.patch('core.utils.subtask_verification_time', return_value=datetime.timedelta()) as mock_subtask_verification_time:
            calculate_subtask_verification_time(self.report_computed_task)

        mock_subtask_verification_time.assert_not_called()

    @override_settings(
        CONCENT_MESSAGING_TIME=int(constants.CMT.total_seconds()),
        MINIMUM_UPLOAD_RATE=constants.DEFAULT_UPLOAD_RATE,
        DOWNLOAD_LEADIN_TIME=constants.DOWNLOAD_LEADIN_TIME.total_seconds(),
        CUSTOM_PROTOCOL_TIMES=True  # overridden to ensure this setting is always True, otherwise this test has no sense
    )
    def test_that_both_subtask_verification_time_implementation_should_return_same_result_when_golem_messages_constants_match_concent_settings(self):
        current_time = get_current_utc_timestamp()

        for size, timestamp, deadline in [
            (7,     current_time + 7,        current_time + 7),
            (10,    current_time,            current_time + 10),
            (19,    current_time + 19,       current_time + 19),
            (100,   current_time + 100,      current_time + 100),
            (331,   current_time + 331,      current_time + 331),
            (999,   current_time + 999,      current_time + 999),
        ]:
            report_computed_task = self._get_deserialized_report_computed_task(
                size=size,
                task_to_compute=self._get_deserialized_task_to_compute(
                    timestamp=parse_timestamp_to_utc_datetime(timestamp),
                    deadline=deadline,
                )
            )
            self.assertEqual(
                calculate_subtask_verification_time(report_computed_task),
                int(helpers.subtask_verification_time(report_computed_task).total_seconds())
            )
