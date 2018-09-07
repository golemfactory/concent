import socket

from django.test import override_settings
from django.test import TestCase
from ethereum.transactions import Transaction
from golem_messages.exceptions import MessageError
from golem_messages.message import Ping

import mock

from middleman_protocol.concent_golem_messages.message import SignedTransaction
from middleman_protocol.concent_golem_messages.message import TransactionRejected
from middleman_protocol.concent_golem_messages.message import TransactionSigningRequest
from middleman_protocol.constants import ErrorCode
from middleman_protocol.exceptions import MiddlemanProtocolError
from middleman_protocol.message import GolemMessageFrame
from middleman_protocol.message import ErrorFrame
from common.testing_helpers import generate_ecc_key_pair
from core.exceptions import SCICallbackFrameError
from core.exceptions import SCICallbackPayloadError
from core.exceptions import SCICallbackPayloadSignatureError
from core.exceptions import SCICallbackRequestIdError
from core.exceptions import SCICallbackTimeoutError
from core.exceptions import SCICallbackTransactionSignatureError
from core.payments.sci_callback import RequestIDGenerator
from core.payments.sci_callback import sci_callback


(CONCENT_PRIVATE_KEY, CONCENT_PUBLIC_KEY) = generate_ecc_key_pair()
(DIFFERENT_CONCENT_PRIVATE_KEY, DIFFERENT_CONCENT_PUBLIC_KEY) = generate_ecc_key_pair()
(SIGNING_SERVICE_PRIVATE_KEY, SIGNING_SERVICE_PUBLIC_KEY) = generate_ecc_key_pair()


@override_settings(
    CONCENT_PRIVATE_KEY=CONCENT_PRIVATE_KEY,
    CONCENT_PUBLIC_KEY=CONCENT_PUBLIC_KEY,
    SIGNING_SERVICE_PUBLIC_KEY=SIGNING_SERVICE_PUBLIC_KEY,
    CONCENT_ETHEREUM_PUBLIC_KEY='a7ea7479471be3035e3de19ecc495c13ab77d0f9c0bfcfb2b60356d89d874c6a0e016b1610719cd16581025bb65431f2c45f2ce4be2609ee88a63c9ef05e9e8c',
)
class SCICallbackTest(TestCase):

    multi_db = True

    def setUp(self):
        super().setUp()

        self.v = 28
        self.r = 43021479287739768723523510158222935518435169120980980279247970098168969365906
        self.s = 27167722793113753385347871828548141783025585937756999455305671053201800240244

        self.request_id = RequestIDGenerator.generate_request_id() + 1
        self.transaction = self._create_unsigned_transaction()
        self.signed_transaction_golem_message = self._create_signed_transaction()
        self.signed_transaction_golem_message.sign_message(SIGNING_SERVICE_PRIVATE_KEY)
        self.frame = GolemMessageFrame(
            payload=self.signed_transaction_golem_message,
            request_id=self.request_id,
        ).serialize(private_key=CONCENT_PRIVATE_KEY)

        def iterator(connection):  # pylint: disable=unused-argument
            yield self.frame

        self.frame_iterator = iterator

    def _create_transaction_signing_request(self):  # pylint: disable=no-self-use
        transaction_siging_request = TransactionSigningRequest(
            nonce=99,
            gasprice=10 ** 6,
            startgas=80000,
            value=10,
            to='7917bc33eea648809c28',
            data=b'3078666333323333396130303030303030303030303030303030303030303030303032393662363963383738613734393865663463343531363436353231336564663834666334623330303030303030303030303030303030303030303030303030333431336437363161356332633362656130373531373064333239363566636161386261303533633030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303237313030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303562343336643666',
        )
        setattr(transaction_siging_request, 'from', '7917bc33eea648809c29')
        return transaction_siging_request

    def _create_signed_transaction(self):
        return SignedTransaction(
            nonce=99,
            gasprice=10 ** 6,
            startgas=80000,
            value=10,
            to=b'7917bc33eea648809c28',
            v=self.v,
            r=self.r,
            s=self.s,
            data=b'3078666333323333396130303030303030303030303030303030303030303030303032393662363963383738613734393865663463343531363436353231336564663834666334623330303030303030303030303030303030303030303030303030333431336437363161356332633362656130373531373064333239363566636161386261303533633030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303237313030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303562343336643666',
        )

    def _create_unsigned_transaction(self):  # pylint: disable=no-self-use
        return Transaction(
            nonce=99,
            gasprice=10 ** 6,
            startgas=80000,
            value=10,
            to=b'7917bc33eea648809c28',
            data=b'3078666333323333396130303030303030303030303030303030303030303030303032393662363963383738613734393865663463343531363436353231336564663834666334623330303030303030303030303030303030303030303030303030333431336437363161356332633362656130373531373064333239363566636161386261303533633030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303237313030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303562343336643666',
        )

    def test_that_sci_callback_should_sign_transaction(self):
        with mock.patch('core.payments.sci_callback.socket.socket.connect'):
            with mock.patch('core.payments.sci_callback.send_over_stream'):
                with mock.patch('core.payments.sci_callback.unescape_stream', side_effect=self.frame_iterator):
                    signed_transaction = sci_callback(self.transaction)

        self.assertEqual(signed_transaction.v, self.v)
        self.assertEqual(signed_transaction.r, self.r)
        self.assertEqual(signed_transaction.s, self.s)

    def test_that_sci_callback_should_raise_exception_on_timeout(self):
        with mock.patch('core.payments.sci_callback.socket.socket.connect'):
            with mock.patch('core.payments.sci_callback.send_over_stream', side_effect=socket.timeout):
                with self.assertRaises(SCICallbackTimeoutError):
                    sci_callback(self.transaction)

    def test_that_sci_callback_should_raise_exception_on_receiving_invalid_middleman_protocol_message(self):
        with mock.patch('core.payments.sci_callback.socket.socket.connect'):
            with mock.patch('core.payments.sci_callback.send_over_stream'):
                with mock.patch('core.payments.sci_callback.unescape_stream', side_effect=self.frame_iterator):
                    with mock.patch('middleman_protocol.message.AbstractFrame.deserialize', side_effect=MiddlemanProtocolError):
                        with self.assertRaises(SCICallbackFrameError):
                            sci_callback(self.transaction)

    def test_that_sci_callback_should_raise_exception_on_receiving_invalid_golem_message(self):
        with mock.patch('core.payments.sci_callback.socket.socket.connect'):
            with mock.patch('core.payments.sci_callback.send_over_stream'):
                with mock.patch('core.payments.sci_callback.unescape_stream', side_effect=self.frame_iterator):
                    with mock.patch('middleman_protocol.message.AbstractFrame.deserialize', side_effect=MessageError):
                        with self.assertRaises(SCICallbackPayloadError):
                            sci_callback(self.transaction)

    def test_that_sci_callback_should_raise_exception_when_golem_message_is_not_signed_by_signing_service(self):
        wrong_signed_golem_message = self._create_signed_transaction()
        wrong_signed_golem_message.sign_message(DIFFERENT_CONCENT_PRIVATE_KEY)

        with mock.patch('core.payments.sci_callback.socket.socket.connect'):
            with mock.patch('core.payments.sci_callback.send_over_stream'):
                with mock.patch('core.payments.sci_callback.unescape_stream', side_effect=self.frame_iterator):
                    with mock.patch(
                        'middleman_protocol.message.AbstractFrame.deserialize',
                        return_value=GolemMessageFrame(payload=wrong_signed_golem_message, request_id=self.request_id),
                    ):
                        with self.assertRaises(SCICallbackPayloadSignatureError):
                            sci_callback(self.transaction)

    def test_that_sci_callback_should_raise_exception_when_messages_request_ids_do_not_match(self):
        with mock.patch('core.payments.sci_callback.socket.socket.connect'):
            with mock.patch('core.payments.sci_callback.send_over_stream'):
                with mock.patch('core.payments.sci_callback.unescape_stream', side_effect=self.frame_iterator):
                    with mock.patch(
                        'middleman_protocol.message.AbstractFrame.deserialize',
                        return_value=GolemMessageFrame(payload=self._create_signed_transaction(), request_id=self.request_id + 1),
                    ):
                        with self.assertRaises(SCICallbackRequestIdError):
                            sci_callback(self.transaction)

    def test_that_sci_callback_should_raise_exception_when_response_is_error_frame(self):
        with mock.patch('core.payments.sci_callback.socket.socket.connect'):
            with mock.patch('core.payments.sci_callback.send_over_stream'):
                with mock.patch('core.payments.sci_callback.unescape_stream', side_effect=self.frame_iterator):
                    with mock.patch(
                        'middleman_protocol.message.AbstractFrame.deserialize',
                        return_value=ErrorFrame(payload=(ErrorCode.UnexpectedMessage, 'error'), request_id=self.request_id),
                    ):
                        with self.assertRaises(SCICallbackPayloadError):
                            sci_callback(self.transaction)

    def test_that_sci_callback_should_raise_exception_when_response_is_transaction_rejected(self):
        with mock.patch('core.payments.sci_callback.socket.socket.connect'):
            with mock.patch('core.payments.sci_callback.send_over_stream'):
                with mock.patch('core.payments.sci_callback.unescape_stream', side_effect=self.frame_iterator):
                    with mock.patch(
                        'middleman_protocol.message.AbstractFrame.deserialize',
                        return_value=GolemMessageFrame(
                            payload=TransactionRejected(REASON=TransactionRejected.REASON.InvalidTransaction),
                            request_id=self.request_id
                        ),
                    ):
                        with self.assertRaises(SCICallbackPayloadError):
                            sci_callback(self.transaction)

    def test_that_sci_callback_should_raise_exception_when_response_is_not_signed_transaction_golem_message(self):
        with mock.patch('core.payments.sci_callback.socket.socket.connect'):
            with mock.patch('core.payments.sci_callback.send_over_stream'):
                with mock.patch('core.payments.sci_callback.unescape_stream', side_effect=self.frame_iterator):
                    with mock.patch(
                        'middleman_protocol.message.AbstractFrame.deserialize',
                        return_value=GolemMessageFrame(payload=Ping(), request_id=self.request_id),
                    ):
                        with self.assertRaises(SCICallbackPayloadError):
                            sci_callback(self.transaction)

    def test_that_sci_callback_should_raise_exception_when_response_signature_is_not_correct(self):
        wrong_signed_transaction = self._create_signed_transaction()
        wrong_signed_transaction.v = self.v - 10
        wrong_signed_transaction.sign_message(SIGNING_SERVICE_PRIVATE_KEY)

        with mock.patch('core.payments.sci_callback.socket.socket.connect'):
            with mock.patch('core.payments.sci_callback.send_over_stream'):
                with mock.patch('core.payments.sci_callback.unescape_stream', side_effect=self.frame_iterator):
                    with mock.patch(
                        'middleman_protocol.message.AbstractFrame.deserialize',
                        return_value=GolemMessageFrame(payload=wrong_signed_transaction, request_id=self.request_id),
                    ):
                        with self.assertRaises(SCICallbackTransactionSignatureError):
                            sci_callback(self.transaction)
