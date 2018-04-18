from django.test import override_settings
from django.test import TestCase

from concent_api.system_check import create_error_18_atomic_requests_not_set_for_database
from concent_api.system_check import check_atomic_requests


class TestStorageClusterCertificatePathCheck(TestCase):

    @override_settings(
        DATABASES=''
    )
    def test_non_dict_database_setting_value_should_not_produce_any_errors(self):
        errors = check_atomic_requests()

        self.assertEqual(errors, [])

    @override_settings(
        DATABASES={
            'default': {
                'ATOMIC_REQUESTS': True
            },
            'non-default': {}
        }
    )
    def test_missing_atomic_request_setting_should_produce_error(self):
        errors = check_atomic_requests()

        self.assertEqual(errors[0], create_error_18_atomic_requests_not_set_for_database('non-default'))

    @override_settings(
        DATABASES={
            'default': {
                'ATOMIC_REQUESTS': True
            },
            'non-default': {
                'ATOMIC_REQUESTS': False
            }
        }
    )
    def test_atomic_request_setting_set_to_false_should_produce_error(self):
        errors = check_atomic_requests()

        self.assertEqual(errors[0], create_error_18_atomic_requests_not_set_for_database('non-default'))

    @override_settings(
        DATABASES={
            'default': {
                'ATOMIC_REQUESTS': True
            },
            'non-default': {
                'ATOMIC_REQUESTS': True
            }
        }
    )
    def test_atomic_request_setting_set_to_true_should_not_produce_any_errors(self):
        errors = check_atomic_requests()

        self.assertEqual(errors, [])
