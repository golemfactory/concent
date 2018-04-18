from django.test                import override_settings
from django.test                import TestCase
from concent_api.system_check   import creation_new_chain_segment_time_check
from concent_api.system_check   import create_error_15_if_new_chain_segment_time_not_integer
from concent_api.system_check   import create_error_16_if_new_chain_segment_time_is_not_bigger_than_0
from concent_api.system_check   import create_error_17_if_geth_container_address_has_wrong_value
from concent_api.system_check   import geth_container_address_check


@override_settings(
    PAYMENT_BACKEND = 'core.payments.sci_backend'
)
class SystemCheckTest(TestCase):
    def setUp(self):
        self.error_not_integer = create_error_15_if_new_chain_segment_time_not_integer()
        self.error_wrong_value = create_error_17_if_geth_container_address_has_wrong_value()

    @override_settings(
        CREATION_NEW_CHAIN_SEGMENT_TIME = ''
    )
    def test_creation_new_chain_segment_time_check_return_error_if_setting_is_empty(self):

        errors = creation_new_chain_segment_time_check(None)

        self.assertEqual(self.error_not_integer, errors[0])

    @override_settings(
        CREATION_NEW_CHAIN_SEGMENT_TIME = '5'
    )
    def test_creation_new_chain_segment_time_check_return_error_if_setting_is_a_string(self):

        errors = creation_new_chain_segment_time_check(None)

        self.assertEqual(self.error_not_integer, errors[0])

    @override_settings(
        CREATION_NEW_CHAIN_SEGMENT_TIME = -1
    )
    def test_creation_new_chain_segment_time_check_return_error_if_setting_less_than_0(self):
        error_lesser_than_0 = create_error_16_if_new_chain_segment_time_is_not_bigger_than_0()

        errors = creation_new_chain_segment_time_check(None)

        self.assertEqual(error_lesser_than_0, errors[0])

    @override_settings(
        CREATION_NEW_CHAIN_SEGMENT_TIME = 0
    )
    def test_creation_new_chain_segment_time_check_return_error_if_setting_is_0(self):
        error_setting_is_0 = create_error_16_if_new_chain_segment_time_is_not_bigger_than_0()

        errors = creation_new_chain_segment_time_check(None)

        self.assertEqual(error_setting_is_0, errors[0])

    @override_settings(
        CREATION_NEW_CHAIN_SEGMENT_TIME = 15
    )
    def test_creation_new_chain_segment_time_check_return_none_when_setting_has_correct_value(self):
        errors = creation_new_chain_segment_time_check(None)

        self.assertEqual(errors, [])

    @override_settings(
        GETH_CONTAINER_ADDRESS = 'http://localhost:8545'
    )
    def test_geth_container_address_check_correct_value(self):
        errors = geth_container_address_check(None)

        self.assertEqual(errors, [])

    @override_settings(
        GETH_CONTAINER_ADDRESS = 'http://localhost8545'
    )
    def test_geth_container_address_check_should_return_error_because_of_missing_colon(self):
        errors = geth_container_address_check(None)
        self.assertEqual(self.error_wrong_value, errors[0])

    @override_settings(
        GETH_CONTAINER_ADDRESS = 'localhost:8545'
    )
    def test_geth_container_address_check_should_return_error_if_in_setting_is_missing_http_at_the_beginning(self):
        errors = geth_container_address_check(None)
        self.assertEqual(self.error_wrong_value, errors[0])

    @override_settings(
        GETH_CONTAINER_ADDRESS = 'http:/localhost:8545'
    )
    def test_geth_container_address_check_should_return_error_if_slash_is_missing(self):
        errors = geth_container_address_check(None)
        self.assertEqual(self.error_wrong_value, errors[0])

    @override_settings(
        GETH_CONTAINER_ADDRESS = 'localhost:8545/http://'
    )
    def test_geth_container_address_check_should_return_error_if_http_is_in_the_end(self):
        errors = geth_container_address_check(None)
        self.assertEqual(self.error_wrong_value, errors[0])
