import mock

from django.test                import override_settings
from django.conf                import settings
from django.test                import TestCase

from concent_api.system_check   import create_error_28_verifier_storage_path_is_not_set
from concent_api.system_check   import create_error_29_verifier_storage_path_is_does_not_exists
from concent_api.system_check   import create_error_30_verifier_storage_path_is_not_accessible
from concent_api.system_check   import check_settings_verifier_storage_path


class TestVerifierStoragePathCheck(TestCase):

    @override_settings(
        CONCENT_FEATURES=[
            'verifier'
        ]
    )
    def test_that_verifier_storage_path_not_set_will_produce_error_when_verifier_is_in_available_concent_features(self):
        del settings.VERIFIER_STORAGE_PATH

        errors = check_settings_verifier_storage_path()

        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0], create_error_28_verifier_storage_path_is_not_set())

    @override_settings(
        CONCENT_FEATURES=[]
    )
    def test_that_verifier_storage_path_not_set_will_not_produce_error_when_verifier_is_not_in_available_concent_features(self):
        del settings.VERIFIER_STORAGE_PATH

        errors = check_settings_verifier_storage_path()

        self.assertEqual(errors, [])

    @override_settings(
        CONCENT_FEATURES=[
            'verifier'
        ],
        VERIFIER_STORAGE_PATH='test'
    )
    def test_that_verifier_storage_path_as_non_existing_path_will_produce_error(self):
        with mock.patch('concent_api.system_check.os.path.exists', return_value=False):
            errors = check_settings_verifier_storage_path()

        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0], create_error_29_verifier_storage_path_is_does_not_exists())

    @override_settings(
        CONCENT_FEATURES=[
            'verifier'
        ],
        VERIFIER_STORAGE_PATH='test'
    )
    def test_that_verifier_storage_path_as_existing_non_accessible_path_will_produce_error(self):
        with mock.patch('concent_api.system_check.os.path.exists', return_value=True):
            with mock.patch('concent_api.system_check.os.access', return_value=False):
                errors = check_settings_verifier_storage_path()

        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0], create_error_30_verifier_storage_path_is_not_accessible())

    @override_settings(
        CONCENT_FEATURES=[
            'verifier'
        ],
        VERIFIER_STORAGE_PATH='test'
    )
    def test_that_verifier_storage_path_as_existing_accessible_path_will_not_produce_error(self):
        with mock.patch('concent_api.system_check.os.path.exists', return_value=True):
            with mock.patch('concent_api.system_check.os.access', return_value=True):
                errors = check_settings_verifier_storage_path()

        self.assertEqual(errors, [])
