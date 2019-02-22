from django.conf import settings

from django.test import override_settings
from django.test import TestCase

from concent_api.system_check import create_error_6_if_minimum_upload_rate_is_not_set
from concent_api.system_check import create_error_7_if_minimum_upload_rate_has_wrong_value
from concent_api.system_check import check_minimum_upload_rate


class TestMinimumUploadRateCheck(TestCase):

    @override_settings(
        MINIMUM_UPLOAD_RATE=1
    )
    def test_that_correct_minimum_upload_rate_setting_value_should_not_produce_any_errors(self):
        errors = check_minimum_upload_rate()

        self.assertEqual(errors, [])

    @override_settings()
    def test_not_set_minimum_upload_rate_setting_value_should_produce_error(self):
        del settings.MINIMUM_UPLOAD_RATE

        errors = check_minimum_upload_rate()

        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0], create_error_6_if_minimum_upload_rate_is_not_set())

    @override_settings(
        MINIMUM_UPLOAD_RATE='1'
    )
    def test_non_int_minimum_upload_rate_setting_type_should_produce_error(self):
        errors = check_minimum_upload_rate()

        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0], create_error_7_if_minimum_upload_rate_has_wrong_value())

    @override_settings(
        MINIMUM_UPLOAD_RATE=0
    )
    def test_negative_minimum_upload_rate_setting_value_should_produce_error(self):
        errors = check_minimum_upload_rate()

        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0], create_error_7_if_minimum_upload_rate_has_wrong_value())
