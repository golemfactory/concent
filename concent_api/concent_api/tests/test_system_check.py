from django.test import override_settings
from django.test import TestCase
from concent_api.system_check import create_error_4_if_geth_container_address_has_wrong_value
from concent_api.system_check import geth_container_address_check


@override_settings(
    PAYMENT_BACKEND = 'core.payments.backends.sci_backend'
)
class SystemCheckTest(TestCase):
    def setUp(self):
        self.error_wrong_value = create_error_4_if_geth_container_address_has_wrong_value()

    @override_settings(
        GETH_ADDRESS = 'http://localhost:8545'
    )
    def test_geth_container_address_check_correct_value(self):
        errors = geth_container_address_check(None)

        self.assertEqual(errors, [])

    @override_settings(
        GETH_ADDRESS = 'http://localhost8545'
    )
    def test_geth_container_address_check_should_return_error_because_of_missing_colon(self):
        errors = geth_container_address_check(None)
        self.assertEqual(self.error_wrong_value, errors[0])

    @override_settings(
        GETH_ADDRESS = 'localhost:8545'
    )
    def test_geth_container_address_check_should_return_error_if_in_setting_is_missing_http_at_the_beginning(self):
        errors = geth_container_address_check(None)
        self.assertEqual(self.error_wrong_value, errors[0])

    @override_settings(
        GETH_ADDRESS = 'http:/localhost:8545'
    )
    def test_geth_container_address_check_should_return_error_if_slash_is_missing(self):
        errors = geth_container_address_check(None)
        self.assertEqual(self.error_wrong_value, errors[0])

    @override_settings(
        GETH_ADDRESS = 'localhost:8545/http://'
    )
    def test_geth_container_address_check_should_return_error_if_http_is_in_the_end(self):
        errors = geth_container_address_check(None)
        self.assertEqual(self.error_wrong_value, errors[0])
