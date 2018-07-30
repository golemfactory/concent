from unittest import TestCase

from golem_messages.exceptions import FieldError
from golem_messages.shortcuts import dump
from golem_messages.shortcuts import load

from middleman_protocol.concent_golem_messages import message
from .factories import SignedTransactionFactory
from .factories import TransactionRejectedFactory
from .factories import TransactionSigningRequestFactory


class SerializationMixin:

    def get_instance(self):
        return self.FACTORY()

    def test_serialization(self):
        message_instance = self.get_instance()
        serialized_message = dump(message_instance, None, None)
        deserialized_message = load(serialized_message, None, None)
        self.assertEqual(message_instance, deserialized_message)


class TransactionSigningRequestTest(SerializationMixin, TestCase):
    MSG_CLASS = message.TransactionSigningRequest
    FACTORY = TransactionSigningRequestFactory

    def test_factory(self):
        msg = self.FACTORY()
        self.assertIsInstance(msg, self.MSG_CLASS)

    def test_validation(self):
        for key in ('nonce', 'gasprice', 'startgas', 'value'):
            invalid_message_instance = self.FACTORY(
                **{key: '1' * 79}
            )
            serialized_message = dump(invalid_message_instance, None, None)
            with self.assertRaises(FieldError):
                load(serialized_message, None, None)


class SignedTransactionTest(SerializationMixin, TestCase):
    MSG_CLASS = message.SignedTransaction
    FACTORY = SignedTransactionFactory

    def test_factory(self):
        msg = self.FACTORY()
        self.assertIsInstance(msg, self.MSG_CLASS)

    def test_validation(self):
        for key in ('nonce', 'gasprice', 'startgas', 'value', 'r', 's'):
            invalid_message_instance = self.FACTORY(
                **{key: '1' * 79}
            )
            serialized_message = dump(invalid_message_instance, None, None)
            with self.assertRaises(FieldError):
                load(serialized_message, None, None)

        invalid_message_instance = self.FACTORY(
            v='1' * 4
        )
        serialized_message = dump(invalid_message_instance, None, None)
        with self.assertRaises(FieldError):
            load(serialized_message, None, None)


class TransactionRejectedTest(SerializationMixin, TestCase):
    MSG_CLASS = message.TransactionRejected
    FACTORY = TransactionRejectedFactory

    def test_factory(self):
        msg = self.FACTORY()
        self.assertIsInstance(msg, self.MSG_CLASS)
