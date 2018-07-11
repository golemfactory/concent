from unittest import TestCase

from core.message_handlers import are_items_unique
from core.tests.utils import ConcentIntegrationTestCase


class TestMessageHandlers(TestCase):
    def test_that_function_returns_true_when_ids_are_diffrent(self):
        response = are_items_unique([1, 2, 3, 4, 5])
        self.assertTrue(response)

    def test_that_function_returns_false_when_ids_are_the_same(self):
        response = are_items_unique([1, 2, 3, 2, 5])
        self.assertFalse(response)
