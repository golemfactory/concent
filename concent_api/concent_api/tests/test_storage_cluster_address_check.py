from django.test import override_settings
from django.conf import settings
from django.test import TestCase

from concent_api.system_check import check_settings_storage_cluster_address
from concent_api.system_check import create_error_36_storage_cluster_address_does_not_end_with_slash
from concent_api.system_check import create_error_38_storage_cluster_address_is_not_valid_url
from concent_api.system_check import create_error_39_storage_server_internal_address_is_not_set


class TestStorageClusterAddressCheck(TestCase):

    @override_settings(
        CONCENT_FEATURES=[
            'gatekeeper'
        ]
    )
    def test_that_storage_cluster_address_not_set_will_produce_error_when_verifier_is_in_available_concent_features(self):
        del settings.STORAGE_CLUSTER_ADDRESS

        errors = check_settings_storage_cluster_address()

        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0], create_error_39_storage_server_internal_address_is_not_set())

    @override_settings(
        CONCENT_FEATURES=[]
    )
    def test_that_storage_cluster_address_not_set_will_not_produce_error_when_verifier_is_not_in_available_concent_features(self):
        del settings.STORAGE_cluster_ADDRESS

        errors = check_settings_storage_cluster_address()

        self.assertEqual(errors, [])

    @override_settings(
        CONCENT_FEATURES=[
            'gatekeeper'
        ],
        STORAGE_CLUSTER_ADDRESS='test'
    )
    def test_that_storage_cluster_address_as_invalid_url_will_produce_error(self):
        errors = check_settings_storage_cluster_address()

        self.assertEqual(len(errors), 1)
        self.assertEqual(
            errors[0],
            create_error_38_storage_cluster_address_is_not_valid_url(
                "['Enter a valid URL.']"
            )
        )

    @override_settings(
        CONCENT_FEATURES=[
            'gatekeeper'
        ],
        STORAGE_CLUSTER_ADDRESS='http://golem.network'
    )
    def test_that_storage_cluster_address_non_ending_with_slash_will_produce_error(self):
        errors = check_settings_storage_cluster_address()

        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0], create_error_36_storage_cluster_address_does_not_end_with_slash())

    @override_settings(
        CONCENT_FEATURES=[
            'gatekeeper'
        ],
        STORAGE_CLUSTER_ADDRESS='http://golem.network/'
    )
    def test_that_storage_cluster_address_as_valid_url_will_not_produce_error(self):
        errors = check_settings_storage_cluster_address()

        self.assertEqual(errors, [])
