from django.conf import settings
from django.test import override_settings

import assertpy
import pytest

from concent_api.system_check import create_error_48_additional_verification_cost_is_not_defined
from concent_api.system_check import create_error_49_additional_verification_cost_is_not_non_negative_integer
from concent_api.system_check import check_additional_verification_cost


# pylint: disable=no-self-use
class TestAdditionalVerificationCostCheck:

    @override_settings(
        ADDITIONAL_VERIFICATION_COST=1,
    )
    def test_that_check_additional_verification_cost_not_produce_error_when_additional_verification_cost_is_set_to_int(self):
        errors = check_additional_verification_cost()

        assertpy.assert_that(errors).is_empty()

    @override_settings()
    def test_that_additional_verification_cost_not_set_will_produce_error(self):  # pylint: disable=no-self-use
        del settings.ADDITIONAL_VERIFICATION_COST

        errors = check_additional_verification_cost()

        assertpy.assert_that(errors).is_length(1)
        assertpy.assert_that(errors[0]).is_equal_to(create_error_48_additional_verification_cost_is_not_defined())

    @pytest.mark.parametrize('additional_verification_cost', [
        -1,
        None,
        1.1,
        'test',
        [],
        {},
    ])
    @override_settings()
    def test_that_additional_verification_cost_set_to_non_int_will_produce_error(self, additional_verification_cost):
        settings.ADDITIONAL_VERIFICATION_COST = additional_verification_cost

        errors = check_additional_verification_cost()

        assertpy.assert_that(errors).is_length(1)
        assertpy.assert_that(errors[0]).is_equal_to(
            create_error_49_additional_verification_cost_is_not_non_negative_integer()
        )
