from django.test import override_settings
from django.conf import settings
from django.test import TestCase

from concent_api.system_check import check_settings_storage_server_internal_address
from concent_api.system_check import create_error_13_storage_server_internal_address_is_not_set
from concent_api.system_check import create_error_14_storage_server_internal_address_is_not_valid_url
from concent_api.system_check import create_error_26_storage_server_internal_address_does_not_end_with_slash


class TestStorageServerInternalAddressCheck(TestCase):

    @override_settings(
        CONCENT_FEATURES=[
            'verifier'
        ]
    )
    def test_that_storage_server_internal_address_not_set_will_produce_error_when_verifier_is_in_available_concent_features(self):
        del settings.STORAGE_SERVER_INTERNAL_ADDRESS

        errors = check_settings_storage_server_internal_address()

        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0], create_error_13_storage_server_internal_address_is_not_set())

    @override_settings(
        CONCENT_FEATURES=[]
    )
    def test_that_storage_server_internal_address_not_set_will_not_produce_error_when_verifier_is_not_in_available_concent_features(self):
        del settings.STORAGE_SERVER_INTERNAL_ADDRESS

        errors = check_settings_storage_server_internal_address()

        self.assertEqual(errors, [])

    @override_settings(
        CONCENT_FEATURES=[
            'verifier'
        ],
        STORAGE_SERVER_INTERNAL_ADDRESS='test'
    )
    def test_that_storage_server_internal_address_as_invalid_url_will_produce_error(self):
        errors = check_settings_storage_server_internal_address()

        self.assertEqual(len(errors), 1)
        self.assertEqual(
            errors[0],
            create_error_14_storage_server_internal_address_is_not_valid_url(
                "['Enter a valid URL.']"
            )
        )

    @override_settings(
        CONCENT_FEATURES=[
            'verifier'
        ],
        STORAGE_SERVER_INTERNAL_ADDRESS='http://golem.network'
    )
    def test_that_storage_server_internal_address_non_ending_with_slash_will_produce_error(self):
        errors = check_settings_storage_server_internal_address()

        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0], create_error_26_storage_server_internal_address_does_not_end_with_slash())

    @override_settings(
        CONCENT_FEATURES=[
            'verifier'
        ],
        STORAGE_SERVER_INTERNAL_ADDRESS='http://golem.network/'
    )
    def test_that_storage_server_internal_address_as_valid_url_will_not_produce_error(self):
        errors = check_settings_storage_server_internal_address()

        self.assertEqual(errors, [])
