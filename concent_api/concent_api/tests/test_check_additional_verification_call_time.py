from django.conf import settings
from django.test import override_settings
from django.test import TestCase

from concent_api.system_check import create_error_61_additional_verification_call_time_is_not_set
from concent_api.system_check import create_error_62_additional_verification_call_time_has_wrong_value
from concent_api.system_check import check_additional_verification_call_time


class TestAdditionalVerificationCallTimeCheck(TestCase):

    @override_settings(
        ADDITIONAL_VERIFICATION_CALL_TIME=1
    )
    def test_that_proper_configuration_of_additional_verification_call_time_setting_value_should_not_produce_any_errors(self):
        errors = check_additional_verification_call_time()

        self.assertEqual(errors, [])

    @override_settings()
    def test_not_set_additional_verification_call_time_setting_value_should_produce_error(self):
        del settings.ADDITIONAL_VERIFICATION_CALL_TIME

        errors = check_additional_verification_call_time()

        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0], create_error_61_additional_verification_call_time_is_not_set())

    @override_settings(
        ADDITIONAL_VERIFICATION_CALL_TIME='1'
    )
    def test_non_int_additional_verification_call_time_setting_type_should_produce_error(self):
        errors = check_additional_verification_call_time()

        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0], create_error_62_additional_verification_call_time_has_wrong_value())

    @override_settings(
        ADDITIONAL_VERIFICATION_CALL_TIME=-1
    )
    def test_negative_additional_verification_call_time_setting_value_should_produce_error(self):
        errors = check_additional_verification_call_time()

        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0], create_error_62_additional_verification_call_time_has_wrong_value())
