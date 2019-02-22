from django.conf import settings
from django.test import override_settings
from django.test import TestCase

from concent_api.system_check import create_error_23_additional_verification_time_multiplier_is_not_defined
from concent_api.system_check import create_error_24_additional_verification_time_multiplier_has_wrong_type
from concent_api.system_check import check_additional_verification_time_multiplier


class TestAdditionalVerificationTimeMultiplierCheck(TestCase):

    @override_settings(
        ADDITIONAL_VERIFICATION_TIME_MULTIPLIER=1.0,
    )
    def test_that_check_additional_verification_time_multiplier_not_produce_error_when_additional_verification_time_multiplier_is_set_to_float(self):
        errors = check_additional_verification_time_multiplier()

        self.assertEqual(errors, [])

    @override_settings()
    def test_that_additional_verification_time_multiplier_not_set_will_produce_error(self):
        del settings.ADDITIONAL_VERIFICATION_TIME_MULTIPLIER

        errors = check_additional_verification_time_multiplier()

        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0], create_error_23_additional_verification_time_multiplier_is_not_defined())

    @override_settings()
    def test_that_additional_verification_time_multiplier_set_to_non_float_will_produce_error(self):
        for setting in [
            None,
            1,
            'test',
            [],
            {},
        ]:
            settings.ADDITIONAL_VERIFICATION_TIME_MULTIPLIER = setting

            errors = check_additional_verification_time_multiplier()

            self.assertEqual(len(errors), 1)
            self.assertEqual(
                errors[0],
                create_error_24_additional_verification_time_multiplier_has_wrong_type(type(setting))
            )
