from django.conf import settings

from django.test import override_settings
from django.test import TestCase

from concent_api.system_check import create_error_8_if_download_leadin_time_is_not_set
from concent_api.system_check import create_error_9_if_download_leadin_time_has_wrong_value
from concent_api.system_check import check_download_leadin_time


class TestDownloadLeadinTimeCheck(TestCase):

    @override_settings(
        DOWNLOAD_LEADIN_TIME=1
    )
    def test_that_proper_configuration_of__download_leadin_time_setting_value_should_not_produce_any_errors(self):
        errors = check_download_leadin_time()

        self.assertEqual(errors, [])

    @override_settings()
    def test_not_set_download_leadin_time_setting_value_should_produce_error(self):
        del settings.DOWNLOAD_LEADIN_TIME

        errors = check_download_leadin_time()

        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0], create_error_8_if_download_leadin_time_is_not_set())

    @override_settings(
        DOWNLOAD_LEADIN_TIME='1'
    )
    def test_non_int_download_leadin_time_setting_type_should_produce_error(self):
        errors = check_download_leadin_time()

        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0], create_error_9_if_download_leadin_time_has_wrong_value())

    @override_settings(
        DOWNLOAD_LEADIN_TIME=-1
    )
    def test_negative_download_leadin_time_setting_value_should_produce_error(self):
        errors = check_download_leadin_time()

        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0], create_error_9_if_download_leadin_time_has_wrong_value())
