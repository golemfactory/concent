from django.test                import override_settings
from django.conf                import settings
from django.test                import TestCase

from concent_api.system_check   import create_error_31_verifier_min_ssim_is_not_set
from concent_api.system_check   import create_error_32_verifier_min_ssim_is_set
from concent_api.system_check   import create_error_33_verifier_min_ssim_has_wrong_type
from concent_api.system_check   import create_error_34_verifier_min_ssim_has_wrong_value
from concent_api.system_check   import check_verifier_min_ssim


class TestStorageServerInternalAddressCheck(TestCase):

    @override_settings(
        CONCENT_FEATURES=[
            'verifier'
        ]
    )
    def test_that_verifier_min_ssim_not_set_will_produce_error_when_verifier_is_in_available_concent_features(self):
        del settings.VERIFIER_MIN_SSIM

        errors = check_verifier_min_ssim()

        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0], create_error_31_verifier_min_ssim_is_not_set())

    @override_settings(
        CONCENT_FEATURES=[]
    )
    def test_that_verifier_min_ssim_not_set_will_not_produce_error_when_verifier_is_not_in_available_concent_features(self):
        del settings.VERIFIER_MIN_SSIM

        errors = check_verifier_min_ssim()

        self.assertEqual(errors, [])

    @override_settings(
        CONCENT_FEATURES=[],
        VERIFIER_MIN_SSIM=0,
    )
    def test_that_verifier_min_ssim_set_will_produce_error_when_verifier_is_not_in_available_concent_features(self):
        errors = check_verifier_min_ssim()

        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0], create_error_32_verifier_min_ssim_is_set())

    @override_settings(
        CONCENT_FEATURES=[],
        VERIFIER_MIN_SSIM=None,
    )
    def test_that_verifier_min_ssim_set_will_not_produce_error_when_verifier_is_none_in_available_concent_features(self):
        errors = check_verifier_min_ssim()

        self.assertEqual(errors, [])

    @override_settings(
        CONCENT_FEATURES=[
            'verifier'
        ],
        VERIFIER_MIN_SSIM='test'
    )
    def test_that_verifier_min_ssim_set_to_non_float_will_produce_error(self):
        errors = check_verifier_min_ssim()

        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0], create_error_33_verifier_min_ssim_has_wrong_type())

    @override_settings(
        CONCENT_FEATURES=[
            'verifier'
        ],
        VERIFIER_MIN_SSIM=-1.01
    )
    def test_that_verifier_min_ssim_set_to_wrong_value_will_produce_error(self):
        errors = check_verifier_min_ssim()

        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0], create_error_34_verifier_min_ssim_has_wrong_value(settings.VERIFIER_MIN_SSIM))
