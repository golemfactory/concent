from django.test import override_settings
from django.conf import settings
from django.test import TestCase

from concent_api.system_check import check_middleman_address
from concent_api.system_check import create_error_48_middleman_address_has_wrong_type
from concent_api.system_check import create_error_49_middleman_address_is_not_set


class TestMiddlemanAddressCheck(TestCase):

    @override_settings(
        CONCENT_FEATURES=[
            'middleman'
        ]
    )
    def test_that_middleman_address_not_set_will_produce_error_when_middleman_is_in_concent_features(self):
        del settings.MIDDLEMAN_ADDRESS

        errors = check_middleman_address()

        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0], create_error_49_middleman_address_is_not_set())

    @override_settings(
        CONCENT_FEATURES=[]
    )
    def test_that_middleman_address_not_set_will_not_produce_error_when_middleman_is_not_in_concent_features(self):
        del settings.MIDDLEMAN_ADDRESS

        errors = check_middleman_address()

        self.assertEqual(errors, [])

    @override_settings(
        CONCENT_FEATURES=[
            'middleman'
        ],
        MIDDLEMAN_ADDRESS=1
    )
    def test_that_non_str_middleman_address_setting_type_should_produce_error(self):
        errors = check_middleman_address()

        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0], create_error_48_middleman_address_has_wrong_type(settings.MIDDLEMAN_ADDRESS))

    @override_settings(
        CONCENT_FEATURES=[
            'middleman'
        ],
        MIDDLEMAN_ADDRESS='127.0.0.1'
    )
    def test_that_middleman_address_as_string_will_not_produce_error(self):
        errors = check_middleman_address()

        self.assertEqual(errors, [])
