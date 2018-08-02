from assertpy import assert_that
from django.test import override_settings

from common.testing_helpers import generate_ecc_key_pair
from concent_api.system_check import check_signing_service_key_availability_for_middleman
from concent_api.system_check import create_error_43_signing_service_public_key_is_missing
from concent_api.system_check import create_error_44_signing_service_public_key_is_invalid


(_, SIGNING_SERVICE_PUBLIC_KEY) = generate_ecc_key_pair()


class TestCheckSigningServiceKeyAvailabilityForMiddleMan:  # pylint: disable=no-self-use
    def test_that_if_middleman_is_disabled_signing_service_public_key_does_not_have_to_be_defined_in_settings(self):
        with override_settings(CONCENT_FEATURES=[]):
            errors = check_signing_service_key_availability_for_middleman()
            assert_that(errors).is_empty()

    def test_that_if_middleman_is_enabled_and_key_signing_service_public_key_is_not_defined_error_is_returned(self):
        errors = check_signing_service_key_availability_for_middleman()
        assert_that(errors).is_length(1)
        assert_that(errors[0]).is_equal_to(create_error_43_signing_service_public_key_is_missing())

    def test_that_if_middleman_is_enabled_and_valid_signing_service_public_key_is_defined_no_errors_are_returned(self):
        with override_settings(
            SIGNING_SERVICE_PUBLIC_KEY=SIGNING_SERVICE_PUBLIC_KEY,
        ):
            errors = check_signing_service_key_availability_for_middleman()
            assert_that(errors).is_empty()

    def test_that_if_middleman_is_enabled_and_invalid_signing_service_public_key_is_invalid_error_is_returned(self):
        with override_settings(
            SIGNING_SERVICE_PUBLIC_KEY="not a public key",
        ):
            errors = check_signing_service_key_availability_for_middleman()
            assert_that(errors).is_length(1)
            assert_that(errors[0]).is_equal_to(create_error_44_signing_service_public_key_is_invalid())
