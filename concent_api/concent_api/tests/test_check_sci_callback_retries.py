from django.conf import settings
from django.test import override_settings
from django.test import TestCase
from mock import patch

from concent_api.system_check import create_error_63_sci_callback_retries_is_not_set
from concent_api.system_check import create_error_64_sci_callback_retries_has_wrong_value
from concent_api.system_check import check_sci_callback_retries


class TestSciCallbackRetriesCheck(TestCase):

    @override_settings(
        SCI_CALLBACK_RETRIES_TIME=2
    )
    @patch('concent_api.system_check.SCI_CALLBACK_MAXIMUM_TIMEOUT', 1)
    def test_that_proper_configuration_of_sci_callback_retries_setting_value_should_not_produce_any_errors(self):
        errors = check_sci_callback_retries()

        self.assertEqual(errors, [])

    @override_settings()
    def test_not_set_sci_callback_retries_setting_value_should_produce_error(self):
        del settings.SCI_CALLBACK_RETRIES_TIME

        errors = check_sci_callback_retries()

        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0], create_error_63_sci_callback_retries_is_not_set())

    @override_settings(
        SCI_CALLBACK_RETRIES_TIME=1
    )
    @patch('concent_api.system_check.SCI_CALLBACK_MAXIMUM_TIMEOUT', 1)
    def test_sci_callback_retries_setting_equal_to_sci_callback_timeout_should_produce_error(self):
        errors = check_sci_callback_retries()

        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0], create_error_64_sci_callback_retries_has_wrong_value())

    @override_settings(
        SCI_CALLBACK_RETRIES_TIME='1'
    )
    def test_non_int_sci_callback_retries_setting_type_should_produce_error(self):
        errors = check_sci_callback_retries()

        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0], create_error_64_sci_callback_retries_has_wrong_value())

    @override_settings(
        SCI_CALLBACK_RETRIES_TIME=-1
    )
    def test_negative_sci_callback_retries_value_should_produce_error(self):
        errors = check_sci_callback_retries()

        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0], create_error_64_sci_callback_retries_has_wrong_value())
