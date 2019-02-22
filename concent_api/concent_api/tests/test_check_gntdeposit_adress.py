from django.conf import settings
from django.test import override_settings
from django.test import TestCase

from concent_api.system_check import check_gntdeposit_adress
from concent_api.system_check import create_error_45_gntdeposit_not_set
from concent_api.system_check import create_error_46_gntdeposit_has_wrong_type
from concent_api.system_check import create_error_47_gntdeposit_wrong_value


class TestGNTDepositCheck(TestCase):

    @override_settings(
        PAYMENT_BACKEND=None,
        GNT_DEPOSIT_CONTRACT_ADDRESS=None,
    )
    def test_that_gntdeposit_check_will_not_produce_error_when_payment_backend_is_not_set(self):
        errors = check_gntdeposit_adress()

        self.assertEqual(errors, [])

    @override_settings(PAYMENT_BACKEND='core.payments.backends.sci_backend')
    def test_that_no_gntdeposit_will_produce_error(self):
        del settings.GNT_DEPOSIT_CONTRACT_ADDRESS
        errors = check_gntdeposit_adress()

        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0], create_error_45_gntdeposit_not_set())

    @override_settings(
        PAYMENT_BACKEND='core.payments.backends.sci_backend',
        GNT_DEPOSIT_CONTRACT_ADDRESS=1000000000000,
    )
    def test_that_gntdeposit_set_to_wrong_type_will_produce_error(self):
        errors = check_gntdeposit_adress()

        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0], create_error_46_gntdeposit_has_wrong_type(settings.GNT_DEPOSIT_CONTRACT_ADDRESS))

    @override_settings(
        PAYMENT_BACKEND='core.payments.backends.sci_backend',
        GNT_DEPOSIT_CONTRACT_ADDRESS='1xA172A4B929Ae9589E3228F723CB99508b8c0709a',
    )
    def test_that_gntdeposit_set_to_wrong_value_will_produce_error(self):
        errors = check_gntdeposit_adress()

        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0], create_error_47_gntdeposit_wrong_value(settings.GNT_DEPOSIT_CONTRACT_ADDRESS))
