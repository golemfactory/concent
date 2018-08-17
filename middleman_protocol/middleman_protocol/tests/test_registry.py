from unittest import TestCase

import mock

from middleman_protocol.constants import PayloadType
from middleman_protocol.registry import register


class TestRegistryMiddlemanProtocol(TestCase):

    def test_that_decorating_class_should_add_it_to_registry(self):

        with mock.patch('middleman_protocol.registry.PAYLOAD_TYPE_TO_MIDDLEMAN_MESSAGE_CLASS', {}):
            @register
            class ToTest:
                payload_type = PayloadType.GOLEM_MESSAGE

            from middleman_protocol.registry import PAYLOAD_TYPE_TO_MIDDLEMAN_MESSAGE_CLASS

            self.assertIn(ToTest.payload_type, PAYLOAD_TYPE_TO_MIDDLEMAN_MESSAGE_CLASS)
            self.assertEqual(PAYLOAD_TYPE_TO_MIDDLEMAN_MESSAGE_CLASS[ToTest.payload_type], ToTest)

    def test_that_decorating_class_without_payload_type_should_raise_exception(self):
        with self.assertRaises(AssertionError):
            @register
            class ToTest:  # pylint: disable=unused-variable
                pass

    def test_that_decorating_class_with_unknown_payload_type_should_raise_exception(self):
        with self.assertRaises(AssertionError):
            @register
            class ToTest:  # pylint: disable=unused-variable
                payload_type = 'unknown'

    def test_that_decorating_classes_same_payload_type_should_raise_exception(self):
        with mock.patch('middleman_protocol.registry.PAYLOAD_TYPE_TO_MIDDLEMAN_MESSAGE_CLASS', {}):
            @register
            class ToTest:  # pylint: disable=unused-variable
                payload_type = PayloadType.GOLEM_MESSAGE

            with self.assertRaises(AssertionError):
                @register
                class ToTest2:  # pylint: disable=unused-variable
                    payload_type = PayloadType.GOLEM_MESSAGE
