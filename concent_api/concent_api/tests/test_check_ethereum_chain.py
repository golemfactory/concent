from assertpy import assert_that
import pytest

from django.conf import settings
from django.test import override_settings

from golem_sci import chains

from concent_api.system_check import check_ethereum_chain
from concent_api.system_check import create_error_59_ethereum_chain_is_not_set
from concent_api.system_check import create_error_60_ethereum_chain_is_not_a_string
from concent_api.system_check import create_error_61_ethereum_chain_is_invalid


# pylint: disable=no-self-use
class TestPaymentInterfaceChainCheck():
    settings.GETH_ADDRESS='http://geth_address:71830'

    def test_that_ethereum_chain_check_will_produce_error_when_payment_backend_is_not_set(self):
        del settings.ETHEREUM_CHAIN
        errors = check_ethereum_chain()

        assert_that(errors).is_equal_to([create_error_59_ethereum_chain_is_not_set()])

    @pytest.mark.parametrize('chain', [
        chains.RINKEBY,
        chains.MAINNET,
    ])
    def test_that_ethereum_chain_from_golem_sci_will_not_produce_error(self, chain):
        with override_settings(ETHEREUM_CHAIN=chain):
            errors = check_ethereum_chain()
            assert_that(errors).is_empty()

    @override_settings(ETHEREUM_CHAIN=71830)
    def test_that_ethereum_chain_check_will_produce_error_when_setting_is_not_a_string(self):
        errors = check_ethereum_chain()

        assert_that(errors[0]).is_equal_to(create_error_60_ethereum_chain_is_not_a_string())

    @override_settings(ETHEREUM_CHAIN='71830')
    def test_that_ethereum_chain_check_will_produce_error_when_setting_has_invalid_value(self):
        errors = check_ethereum_chain()

        assert_that(errors[0]).is_equal_to(create_error_61_ethereum_chain_is_invalid())
