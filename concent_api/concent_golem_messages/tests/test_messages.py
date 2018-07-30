from unittest import TestCase

from golem_messages.shortcuts import dump
from golem_messages.shortcuts import load

from concent_golem_messages import message
from concent_golem_messages.tests import factories


class SerializationMixin:

    def get_instance(self):
        return self.FACTORY()

    def test_serialization(self):
        msg = self.get_instance()
        s_msg = dump(msg, None, None)
        msg2 = load(s_msg, None, None)
        self.assertEqual(msg, msg2)


class TransactionSigningRequestTest(SerializationMixin, TestCase):
    MSG_CLASS = message.TransactionSigningRequest
    FACTORY = factories.TransactionSigningRequestFactory

    def test_factory(self):
        msg = self.FACTORY()
        self.assertIsInstance(msg, self.MSG_CLASS)


class SignedTransactionTest(SerializationMixin, TestCase):
    MSG_CLASS = message.SignedTransaction
    FACTORY = factories.SignedTransactionFactory

    def test_factory(self):
        msg = self.FACTORY()
        self.assertIsInstance(msg, self.MSG_CLASS)


class TransactionRejectedTest(SerializationMixin, TestCase):
    MSG_CLASS = message.TransactionRejected
    FACTORY = factories.TransactionRejectedFactory

    def test_factory(self):
        msg = self.FACTORY()
        self.assertIsInstance(msg, self.MSG_CLASS)
