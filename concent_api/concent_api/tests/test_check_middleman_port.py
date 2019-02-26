from django.conf import settings
from django.test import override_settings
from django.test import TestCase

import assertpy
import pytest

from concent_api.system_check import check_middleman_port
from concent_api.system_check import create_error_39_middleman_port_is_not_set
from concent_api.system_check import create_error_40_middleman_port_has_wrong_type
from concent_api.system_check import create_error_41_middleman_port_has_wrong_value


class MiddlemanPortCheckTestCase(TestCase):

    @override_settings(
        CONCENT_FEATURES=[
            'concent-worker',
            'concent-api',
        ]
    )
    def test_that_middleman_port_not_set_will_produce_error_when_middleman_is_in_concent_features(self):
        del settings.MIDDLEMAN_PORT

        errors = check_middleman_port()

        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0], create_error_39_middleman_port_is_not_set())

    @override_settings(
        CONCENT_FEATURES=[]
    )
    def test_that_middleman_port_not_set_will_not_produce_error_when_middleman_is_not_in_concent_features(self):
        del settings.MIDDLEMAN_PORT

        errors = check_middleman_port()

        self.assertEqual(errors, [])

    @override_settings(
        CONCENT_FEATURES=[
            'concent-worker',
            'concent-api',
        ],
        MIDDLEMAN_PORT='1'
    )
    def test_that_non_int_middleman_port_rate_setting_type_should_produce_error(self):
        errors = check_middleman_port()

        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0], create_error_40_middleman_port_has_wrong_type(settings.MIDDLEMAN_PORT))


class TestMiddlemanPortCheck:

    @pytest.mark.parametrize('middleman_port_value', [
        1,
        65534,
    ])  # pylint: disable=no-self-use
    def test_that_checking_middleman_port_setting_in_allowed_range_should_not_produce_error(self, middleman_port_value):  # pylint: disable=no-self-use
        with override_settings(
            CONCENT_FEATURES=[
                 'concent-worker',
                 'concent-api',
            ],
            MIDDLEMAN_PORT=middleman_port_value
        ):
            errors = check_middleman_port()

            assertpy.assert_that(errors).is_length(0)

    @pytest.mark.parametrize(('middleman_port_value',), [
        (-1,),
        (0,),
        (65535,),
        (65536,),
    ])  # pylint: disable=no-self-use
    def test_that_checking_middleman_port_setting_not_in_allowed_range_should_produce_error(self, middleman_port_value):  # pylint: disable=no-self-use
        with override_settings(
            CONCENT_FEATURES=[
                'concent-worker',
                'concent-api',
            ],
            MIDDLEMAN_PORT=middleman_port_value
        ):
            errors = check_middleman_port()

            assertpy.assert_that(errors).is_length(1)
            assertpy.assert_that(errors[0]).is_equal_to(
                create_error_41_middleman_port_has_wrong_value(settings.MIDDLEMAN_PORT)
            )
