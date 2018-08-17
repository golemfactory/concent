from django.conf import settings

from django.test import override_settings
from django.test import TestCase

from concent_api.system_check import check_concent_ethereum_public_key
from concent_api.system_check import create_error_45_concent_ethereum_public_key_is_not_set
from concent_api.system_check import create_error_46_concent_ethereum_public_key_has_wrong_type
from concent_api.system_check import create_error_47_concent_ethereum_public_key_has_wrong_length
from core.constants import ETHEREUM_PUBLIC_KEY_LENGTH


class CheckConcentEthereumPublicKeyTestCase(TestCase):

    @override_settings(
        CONCENT_FEATURES=[],
    )
    def test_that_missing_concent_ethereum_public_key_should_not_produce_error_when_core_is_not_in_available_concent_features(self):
        errors = check_concent_ethereum_public_key()

        self.assertEqual(errors, [])

    @override_settings(
        CONCENT_FEATURES=[
            'core'
        ]
    )
    def test_that_missing_concent_ethereum_public_key_should_produce_error_when_core_is_not_in_available_concent_features(self):
        errors = check_concent_ethereum_public_key()

        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0], create_error_45_concent_ethereum_public_key_is_not_set())

    @override_settings(
        CONCENT_FEATURES=[
            'core'
        ],
        CONCENT_ETHEREUM_PUBLIC_KEY=1
    )
    def test_that_wrong_type_of_concent_ethereum_public_key_should_produce_error(self):
        errors = check_concent_ethereum_public_key()

        self.assertEqual(len(errors), 1)
        self.assertEqual(
            errors[0],
            create_error_46_concent_ethereum_public_key_has_wrong_type(settings.CONCENT_ETHEREUM_PUBLIC_KEY)
        )

    @override_settings(
        CONCENT_FEATURES=[
            'core'
        ],
        CONCENT_ETHEREUM_PUBLIC_KEY='1' * (ETHEREUM_PUBLIC_KEY_LENGTH - 1)
    )
    def test_that_wrong_length_of_concent_ethereum_public_key_should_produce_error(self):
        errors = check_concent_ethereum_public_key()

        self.assertEqual(len(errors), 1)
        self.assertEqual(
            errors[0],
            create_error_47_concent_ethereum_public_key_has_wrong_length(settings.CONCENT_ETHEREUM_PUBLIC_KEY)
        )

    @override_settings(
        CONCENT_FEATURES=[
            'core'
        ],
        CONCENT_ETHEREUM_PUBLIC_KEY='1' * ETHEREUM_PUBLIC_KEY_LENGTH
    )
    def test_that_corrent_concent_ethereum_public_key_should_not_produce_error(self):
        errors = check_concent_ethereum_public_key()

        self.assertEqual(errors, [])
