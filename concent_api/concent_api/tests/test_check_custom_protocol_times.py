import mock

from django.conf import settings
from django.test import override_settings
from django.test import TestCase

from golem_messages import constants

from concent_api.system_check import check_custom_protocol_times
from concent_api.system_check import create_error_31_custom_protocol_times_is_not_set
from concent_api.system_check import create_error_32_custom_protocol_times_has_wrong_value
from concent_api.system_check import create_error_33_custom_protocol_times_is_false_and_settings_does_not_match_golem_messages_constants


class TestConcentsTimeSettingsCheck(TestCase):

    def test_that_check_custom_protocol_times_should_not_return_error_if_settings_match_golem_messages_constants(self):
        errors = check_custom_protocol_times()

        self.assertEqual(errors, [])

    @override_settings()
    def test_that_check_custom_protocol_times_should_return_error_if_custom_protocol_times_setting_is_missing(self):
        del settings.CUSTOM_PROTOCOL_TIMES
        errors = check_custom_protocol_times()

        self.assertEqual([create_error_31_custom_protocol_times_is_not_set()], errors)

    def test_that_check_custom_protocol_times_should_return_error_if_custom_protocol_times_setting_is_not_bool_value(self):
        for wrong_value in [
            None,
            'a',
            1,
        ]:
            settings.CUSTOM_PROTOCOL_TIMES = wrong_value

            errors = check_custom_protocol_times()

            self.assertEqual([create_error_32_custom_protocol_times_has_wrong_value()], errors)

    @override_settings(
        CONCENT_MESSAGING_TIME=1,
        FORCE_ACCEPTANCE_TIME=1,
        DOWNLOAD_LEADIN_TIME=int(constants.DOWNLOAD_LEADIN_TIME.total_seconds()),  # This is set back to original
        MINIMUM_UPLOAD_RATE=constants.DEFAULT_UPLOAD_RATE,  # This is set back to original
        CUSTOM_PROTOCOL_TIMES=False,
    )  # pylint: disable=no-self-use
    def test_that_check_custom_protocol_times_should_return_error_if_custom_protocol_times_setting_does_not_match_golem_messages_constant(self):
        class CMT:
            def total_seconds(self):
                return 2

        class FAT:
            def total_seconds(self):
                return 2

        with mock.patch('concent_api.system_check.constants.CMT', new_callable=CMT):
            with mock.patch('concent_api.system_check.constants.FAT', new_callable=FAT):
                errors = check_custom_protocol_times()

        self.assertEqual(
            [
                create_error_33_custom_protocol_times_is_false_and_settings_does_not_match_golem_messages_constants(
                    'CONCENT_MESSAGING_TIME'
                ),
                create_error_33_custom_protocol_times_is_false_and_settings_does_not_match_golem_messages_constants(
                    'FORCE_ACCEPTANCE_TIME'
                )
            ],
            errors
        )
