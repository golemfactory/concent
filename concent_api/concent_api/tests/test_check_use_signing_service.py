from django.conf import settings

from django.test import override_settings
from django.test import TestCase

from concent_api.system_check import check_use_signing_service
from concent_api.system_check import create_error_53_use_signing_service_not_set
from concent_api.system_check import create_error_54_use_signing_service_has_wrong_type
from concent_api.system_check import create_error_55_use_signing_service_is_true_but_middleman_is_missing


class CheckUseSigningServiceTestCase(TestCase):

    @override_settings(
        PAYMENT_BACKEND='mock',
    )
    def test_that_missing_use_signing_service_should_not_produce_error_when_payments_backend_is_not_sci_backend(self):
        errors = check_use_signing_service()

        self.assertEqual(errors, [])

    @override_settings(
        PAYMENT_BACKEND='core.payments.backends.sci_backend',
    )
    def test_that_missing_use_signing_service_should_produce_error_when_payments_backend_is_sci_backend(self):
        del settings.USE_SIGNING_SERVICE
        errors = check_use_signing_service()

        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0], create_error_53_use_signing_service_not_set())

    @override_settings(
        PAYMENT_BACKEND='core.payments.backends.sci_backend',
        USE_SIGNING_SERVICE=1,
    )
    def test_that_wrong_type_of_use_signing_service_should_produce_error(self):
        errors = check_use_signing_service()

        self.assertEqual(len(errors), 1)
        self.assertEqual(
            errors[0],
            create_error_54_use_signing_service_has_wrong_type(settings.USE_SIGNING_SERVICE)
        )

    @override_settings(
        CONCENT_FEATURES=[],
        PAYMENT_BACKEND='core.payments.backends.sci_backend',
        USE_SIGNING_SERVICE=True,
    )
    def test_that_use_signing_service_set_to_true_should_produce_error_when_middleman_is_not_available(self):
        errors = check_use_signing_service()

        self.assertEqual(len(errors), 1)
        self.assertEqual(
            errors[0],
            create_error_55_use_signing_service_is_true_but_middleman_is_missing()
        )

    @override_settings(
        CONCENT_FEATURES=[],
        PAYMENT_BACKEND='core.payments.backends.sci_backend',
        USE_SIGNING_SERVICE=False,
    )
    def test_that_use_signing_service_set_to_false_should_not_produce_error_when_middleman_is_not_available(self):
        errors = check_use_signing_service()

        self.assertEqual(errors, [])

    @override_settings(
        CONCENT_FEATURES=[
            'middleman',
        ],
        PAYMENT_BACKEND='core.payments.backends.sci_backend',
        USE_SIGNING_SERVICE=True,
    )
    def test_that_use_signing_service_set_to_true_should_not_produce_error_when_middleman_is_available(self):
        errors = check_use_signing_service()

        self.assertEqual(errors, [])
