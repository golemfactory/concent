from django.test                import override_settings
from django.test                import TestCase
from django.conf import settings

from concent_api.system_check   import check_concents_time_settings
from concent_api.system_check   import create_error_10_if_concent_time_settings_is_not_defined
from concent_api.system_check   import create_error_11_if_concent_time_settings_have_wrong_value


class TestConcentsTimeSettingsCheck(TestCase):
    def setUp(self):
        self.error_CMT_wrong_value = create_error_11_if_concent_time_settings_have_wrong_value('CONCENT_MESSAGING_TIME')
        self.error_CMT_not_defined = create_error_10_if_concent_time_settings_is_not_defined('CONCENT_MESSAGING_TIME')
        self.error_FAT_wrong_value = create_error_11_if_concent_time_settings_have_wrong_value('FORCE_ACCEPTANCE_TIME')
        self.error_FAT_not_defined = create_error_10_if_concent_time_settings_is_not_defined('FORCE_ACCEPTANCE_TIME')
        self.error_PDT_wrong_value = create_error_11_if_concent_time_settings_have_wrong_value('PAYMENT_DUE_TIME')
        self.error_PDT_not_defined = create_error_10_if_concent_time_settings_is_not_defined('PAYMENT_DUE_TIME')

    @override_settings(
    )
    def test_that_function_returns_list_of_3_errors_when_cmt_fat_pdt_are_unset(self):
        del settings.CONCENT_MESSAGING_TIME
        del settings.FORCE_ACCEPTANCE_TIME
        del settings.PAYMENT_DUE_TIME
        errors = check_concents_time_settings()

        self.assertEqual([self.error_CMT_not_defined, self.error_FAT_not_defined, self.error_PDT_not_defined], errors)

    @override_settings(
        FORCE_ACCEPTANCE_TIME = 1,
    )
    def test_that_function_return_list_of_2_errors_when_cmt_pdt_are_unset(self):
        del settings.CONCENT_MESSAGING_TIME
        del settings.PAYMENT_DUE_TIME
        errors = check_concents_time_settings()

        self.assertEqual([self.error_CMT_not_defined, self.error_PDT_not_defined], errors)

    @override_settings(
        CONCENT_MESSAGING_TIME = -1,
        FORCE_ACCEPTANCE_TIME = -1,
        PAYMENT_DUE_TIME = -1,
    )
    def test_that_function_returns_list_of_3_errors_when_cmt_fat_pdt_have_negative_integers(self):
        errors = check_concents_time_settings()

        self.assertEqual([self.error_CMT_wrong_value, self.error_FAT_wrong_value, self.error_PDT_wrong_value], errors)

    @override_settings(
        CONCENT_MESSAGING_TIME = '1',
        FORCE_ACCEPTANCE_TIME = '1',
        PAYMENT_DUE_TIME = '1',
    )
    def test_that_function_returns_list_of_3_errors_when_cmt_fat_pdt_are_strings(self):
        errors = check_concents_time_settings()

        self.assertEqual([self.error_CMT_wrong_value, self.error_FAT_wrong_value, self.error_PDT_wrong_value], errors)

    @override_settings(
        CONCENT_MESSAGING_TIME = '1',
        FORCE_ACCEPTANCE_TIME = 1,
        PAYMENT_DUE_TIME = '1',
    )
    def test_that_function_returns_list_of_2_errors_when_cmt_pdt_have_wrong_values(self):
        errors = check_concents_time_settings()

        self.assertEqual([self.error_CMT_wrong_value, self.error_PDT_wrong_value], errors)

    @override_settings(
        CONCENT_MESSAGING_TIME = 1,
        FORCE_ACCEPTANCE_TIME = '1',
        PAYMENT_DUE_TIME = '1',
    )
    def test_that_function_returns_list_of_2_errors_when_fat_pdt_have_wrong_values(self):
        errors = check_concents_time_settings()

        self.assertEqual([self.error_FAT_wrong_value, self.error_PDT_wrong_value], errors)

    @override_settings(
        CONCENT_MESSAGING_TIME = '1',
        FORCE_ACCEPTANCE_TIME = '1',
        PAYMENT_DUE_TIME = 1,
    )
    def test_that_function_returns_list_of_2_errors_when_cmt_fat_have_wrong_values(self):
        errors = check_concents_time_settings()

        self.assertEqual([self.error_CMT_wrong_value, self.error_FAT_wrong_value], errors)

    @override_settings(
        CONCENT_MESSAGING_TIME = '1',
        FORCE_ACCEPTANCE_TIME = 1,
        PAYMENT_DUE_TIME = -1,
    )
    def test_that_function_returns_list_of_2_errors_when_cmt_is_string_pdt_is_negative_integer(self):
        errors = check_concents_time_settings()

        self.assertEqual([self.error_CMT_wrong_value, self.error_PDT_wrong_value], errors)

    @override_settings(
        CONCENT_MESSAGING_TIME = 1,
        FORCE_ACCEPTANCE_TIME = 1,
        PAYMENT_DUE_TIME = 1,
    )
    def test_that_function_returns_empty_error_list_when_cmt_fat_pdt_have_correct_values(self):
        errors = check_concents_time_settings()

        self.assertEqual([], errors)
