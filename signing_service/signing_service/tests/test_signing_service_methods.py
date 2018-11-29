import datetime
from base64 import b64encode
from unittest import TestCase
import os
import sys
import tempfile

from golem_messages.cryptography import ECCx
from golem_messages.cryptography import ecdsa_verify
import assertpy
import mock
import pytest

from middleman_protocol.concent_golem_messages.message import SignedTransaction
from middleman_protocol.concent_golem_messages.message import TransactionRejected

from signing_service.constants import SIGNING_SERVICE_DEFAULT_PORT
from signing_service.constants import SIGNING_SERVICE_DEFAULT_INITIAL_RECONNECT_DELAY
from signing_service.constants import SIGNING_SERVICE_DEFAULT_RECONNECT_ATTEMPTS
from signing_service.constants import SIGNING_SERVICE_MAXIMUM_RECONNECT_TIME
from signing_service.exceptions import Base64DecodeError
from signing_service.exceptions import SigningServiceValidationError
from signing_service.signing_service import _parse_arguments
from signing_service.signing_service import SigningService
from signing_service.utils import ConsoleNotifier
from .utils import SigningServiceIntegrationTestCase


TEST_ETHEREUM_PRIVATE_KEY = '47a286230c8b3a1c3fa0282f6a65d1d57ffe5147dafaef7cd110d24ed51b462e'

concent_ecc_keys = ECCx(None)
(CONCENT_PRIVATE_KEY, CONCENT_PUBLIC_KEY) = concent_ecc_keys.raw_privkey, concent_ecc_keys.raw_pubkey

signing_service_ecc_keys = ECCx(None)
(SIGNING_SERVICE_PRIVATE_KEY, SIGNING_SERVICE_PUBLIC_KEY) = signing_service_ecc_keys.raw_privkey, signing_service_ecc_keys.raw_pubkey


class SigningServiceGetSignedTransactionTestCase(SigningServiceIntegrationTestCase, TestCase):

    def setUp(self):
        self.host = '127.0.0.1'
        self.port = 8000
        self.initial_reconnect_delay = 2

        with mock.patch('signing_service.signing_service.SigningService.run'):
            self.signing_service = SigningService(
                self.host,
                self.port,
                self.initial_reconnect_delay,
                CONCENT_PUBLIC_KEY,
                SIGNING_SERVICE_PRIVATE_KEY,
                TEST_ETHEREUM_PRIVATE_KEY,
                SIGNING_SERVICE_DEFAULT_RECONNECT_ATTEMPTS,
                ConsoleNotifier(),
            )

    def test_that_get_signed_transaction_should_return_transaction_signed_if_transaction_was_signed_correctly(self):
        transaction_signing_request = self._get_deserialized_transaction_signing_request()

        transaction_signed = self.signing_service._get_signed_transaction(transaction_signing_request)

        self.assertIsInstance(transaction_signed, SignedTransaction)
        self.assertEqual(transaction_signed.nonce, transaction_signing_request.nonce)  # pylint: disable=no-member
        self.assertEqual(transaction_signed.gasprice, transaction_signing_request.gasprice)  # pylint: disable=no-member
        self.assertEqual(transaction_signed.startgas, transaction_signing_request.startgas)  # pylint: disable=no-member
        self.assertEqual(transaction_signed.to, transaction_signing_request.to)  # pylint: disable=no-member
        self.assertEqual(transaction_signed.value, transaction_signing_request.value)  # pylint: disable=no-member
        self.assertEqual(transaction_signed.data, transaction_signing_request.data)  # pylint: disable=no-member
        self.assertEqual(transaction_signed.v, 27)  # pylint: disable=no-member
        self.assertEqual(transaction_signed.r, 30388804072119173430692318653717116791007045427887199775992056799290419449340)  # pylint: disable=no-member
        self.assertEqual(transaction_signed.s, 12415095341641447952516229207372622127096123813439844824954905697584046077123)  # pylint: disable=no-member

    def test_that_get_signed_transaction_should_return_transaction_rejected_if_transaction_cannot_be_recreated_from_received_transaction_signing_request(self):
        transaction_signing_request = self._get_deserialized_transaction_signing_request()
        transaction_signing_request.nonce = 'invalid_nonce'

        transaction_rejected = self.signing_service._get_signed_transaction(transaction_signing_request)

        self.assertIsInstance(transaction_rejected, TransactionRejected)
        self.assertEqual(transaction_rejected.reason, TransactionRejected.REASON.InvalidTransaction)  # pylint: disable=no-member

    def test_that_get_signed_transaction_should_return_transaction_rejected_if_transaction_cannot_be_signed(self):
        transaction_signing_request = self._get_deserialized_transaction_signing_request()
        self.signing_service.ethereum_private_key = b'\x00'

        transaction_rejected = self.signing_service._get_signed_transaction(transaction_signing_request)

        self.assertIsInstance(transaction_rejected, TransactionRejected)
        self.assertEqual(transaction_rejected.reason, TransactionRejected.REASON.UnauthorizedAccount)  # pylint: disable=no-member


class SigningServiceGetAuthenticationChallengeSignatureTestCase(SigningServiceIntegrationTestCase, TestCase):

    def setUp(self):
        self.host = '127.0.0.1'
        self.port = 8000
        self.initial_reconnect_delay = 2

        with mock.patch('signing_service.signing_service.SigningService.run'):
            self.signing_service = SigningService(
                self.host,
                self.port,
                self.initial_reconnect_delay,
                CONCENT_PUBLIC_KEY,
                SIGNING_SERVICE_PRIVATE_KEY,
                TEST_ETHEREUM_PRIVATE_KEY,
                SIGNING_SERVICE_DEFAULT_RECONNECT_ATTEMPTS,
                ConsoleNotifier(),
            )

    def test_that_get_authentication_challenge_signature_should_return_signature_of_passed_bytes(self):
        authentication_challenge = bytes(os.urandom(1000))

        signature = self.signing_service._get_authentication_challenge_signature(authentication_challenge)

        self.assertIsInstance(signature, bytes)
        self.assertTrue(
            ecdsa_verify(
                self.signing_service.signing_service_public_key,
                signature,
                authentication_challenge,
            )
        )


class TestSigningServiceIncreaseDelay:

    @pytest.fixture(autouse=True)
    def setUp(self, unused_tcp_port_factory):
        self.signing_service = SigningService(
            '127.0.0.1',
            unused_tcp_port_factory(),
            2,
            CONCENT_PUBLIC_KEY,
            SIGNING_SERVICE_PRIVATE_KEY,
            TEST_ETHEREUM_PRIVATE_KEY,
            SIGNING_SERVICE_DEFAULT_RECONNECT_ATTEMPTS,
            ConsoleNotifier(),
        )

    def test_that_initial_reconnect_delay_should_be_set_to_passed_value(self):
        assertpy.assert_that(self.signing_service.current_reconnect_delay).is_equal_to(None)
        assertpy.assert_that(self.signing_service.initial_reconnect_delay).is_equal_to(2)

    def test_that_current_reconnect_delay_should_be_set_to_reconnect_delay_after_first_call_to__increase_delay(self):
        self.signing_service._increase_delay()
        assertpy.assert_that(self.signing_service.current_reconnect_delay).is_equal_to(2)

    def test_that_current_reconnect_delay_should_be_doubled_after_next_call_to__increase_delay(self):
        self.signing_service._increase_delay()
        self.signing_service._increase_delay()
        assertpy.assert_that(self.signing_service.current_reconnect_delay).is_equal_to(2 * 2)

    def test_that_current_reconnect_delay_should_be_set_to_allowed_maximum_after_it_extends_it(self):
        self.signing_service.current_reconnect_delay = SIGNING_SERVICE_MAXIMUM_RECONNECT_TIME - 1
        self.signing_service._increase_delay()
        assertpy.assert_that(self.signing_service.current_reconnect_delay).is_equal_to(SIGNING_SERVICE_MAXIMUM_RECONNECT_TIME)


class SigningServiceParseArgumentsTestCase(TestCase):

    def setUp(self):
        # ArgumentParser takes values directly from sys.argv, but the test runner has its own arguments,
        # so they have to be replaced.
        sys.argv = sys.argv[:1]
        self.concent_public_key_encoded = b64encode(CONCENT_PUBLIC_KEY).decode()
        self.signing_service_private_key_encoded = b64encode(SIGNING_SERVICE_PRIVATE_KEY).decode()
        self.ethereum_private_key_encoded = b64encode(TEST_ETHEREUM_PRIVATE_KEY.encode('ascii')).decode()
        self.sentry_dsn = 'http://test.sentry@dsn.com'
        self.maximum_reconnection_attempts = 3

    def test_that_argument_parser_should_parse_correct_input(self):
        sys.argv += [
            '--concent-cluster-host', '127.0.0.1',
            '--concent-public-key', self.concent_public_key_encoded,
            '--initial_reconnect_delay', '2',
            '--concent-cluster-port', '8000',
            '--sentry-dsn', self.sentry_dsn,
            '--ethereum-private-key', self.ethereum_private_key_encoded,
            '--signing-service-private-key', self.signing_service_private_key_encoded,
            f'--max-reconnect-attempts={self.maximum_reconnection_attempts}',
        ]

        args = _parse_arguments()

        self.assertEqual(args.concent_cluster_host, '127.0.0.1')
        self.assertEqual(args.concent_cluster_port, 8000)
        self.assertEqual(args.initial_reconnect_delay, 2)
        self.assertEqual(args.concent_public_key, CONCENT_PUBLIC_KEY)
        self.assertEqual(args.sentry_dsn, self.sentry_dsn)
        self.assertEqual(args.ethereum_private_key, TEST_ETHEREUM_PRIVATE_KEY)
        self.assertEqual(args.signing_service_private_key, SIGNING_SERVICE_PRIVATE_KEY)

    def test_that_argument_parser_should_parse_correct_input_and_use_default_values(self):
        sys.argv += [
            '--concent-public-key', self.concent_public_key_encoded,
            '--ethereum-private-key', self.ethereum_private_key_encoded,
            '--signing-service-private-key', self.signing_service_private_key_encoded,
        ]

        args = _parse_arguments()

        self.assertEqual(args.concent_cluster_port, SIGNING_SERVICE_DEFAULT_PORT)
        self.assertEqual(args.initial_reconnect_delay, SIGNING_SERVICE_DEFAULT_INITIAL_RECONNECT_DELAY)
        self.assertEqual(args.max_reconnect_attempts, SIGNING_SERVICE_DEFAULT_RECONNECT_ATTEMPTS)

    def test_that_argument_parser_should_fail_if_port_cannot_be_casted_to_int(self):
        sys.argv += [
            '--concent_cluster_host', '127.0.0.1',
            '--concent-public-key', self.concent_public_key_encoded,
            '--concent-cluster-port', 'abc',
            '--ethereum-private-key', self.ethereum_private_key_encoded,
            '--signing-service-private-key', self.signing_service_private_key_encoded,
        ]

        with self.assertRaises(SystemExit):
            _parse_arguments()

    def test_that_argument_parser_should_parse_correct_secrets_from_env_variables(self):
        sys.argv += [
            '--concent-cluster-host', '127.0.0.1',
            '--concent-public-key', self.concent_public_key_encoded,
            '--sentry-dsn-from-env',
            '--ethereum-private-key-from-env',
            '--signing-service-private-key-from-env',
        ]

        with mock.patch.dict(os.environ, {
            'SENTRY_DSN': self.sentry_dsn,
            'ETHEREUM_PRIVATE_KEY': self.ethereum_private_key_encoded,
            'SIGNING_SERVICE_PRIVATE_KEY': self.signing_service_private_key_encoded,
        }):
            args = _parse_arguments()

        self.assertEqual(args.sentry_dsn, self.sentry_dsn)
        self.assertEqual(args.ethereum_private_key, TEST_ETHEREUM_PRIVATE_KEY)
        self.assertEqual(args.signing_service_private_key, SIGNING_SERVICE_PRIVATE_KEY)

    def test_that_argument_parses_should_fail_if_file_with_secrets_is_missing(self):
        sys.argv += [
            '--concent-cluster-host', '127.0.0.1',
            '--concent-public-key', self.concent_public_key_encoded,
            '--sentry-dsn-path', '/not_existing_path/file.txt'
        ]
        with self.assertRaises(FileNotFoundError):
            _parse_arguments()

    def test_that_argument_parser_should_parse_parameters_if_passed_files_exist(self):
        sentry_tmp_file = os.path.join(tempfile.gettempdir(), "sentry_tmp_file.txt")
        ethereum_private_key_tmp_file = os.path.join(tempfile.gettempdir(), "ethereum_private_key_tmp_file.txt")
        signing_service_private_key_tmp_file = os.path.join(tempfile.gettempdir(), "signing_service_private_key_tmp_file.txt")

        sys.argv += [
            '--concent-cluster-host', '127.0.0.1',
            '--concent-public-key', self.concent_public_key_encoded,
            '--ethereum-private-key-path', ethereum_private_key_tmp_file,
            '--sentry-dsn-path', sentry_tmp_file,
            '--signing-service-private-key-path', signing_service_private_key_tmp_file,
        ]

        with open(sentry_tmp_file, "w") as file:
            file.write(self.sentry_dsn)

        with open(ethereum_private_key_tmp_file, "w") as file:
            file.write(self.ethereum_private_key_encoded)

        with open(signing_service_private_key_tmp_file, "w") as file:
            file.write(self.signing_service_private_key_encoded)

        args =_parse_arguments()

        self.assertEqual(args.sentry_dsn, self.sentry_dsn)
        self.assertEqual(args.ethereum_private_key, TEST_ETHEREUM_PRIVATE_KEY)
        self.assertEqual(args.signing_service_private_key, SIGNING_SERVICE_PRIVATE_KEY)
        os.remove(sentry_tmp_file)
        os.remove(ethereum_private_key_tmp_file)
        os.remove(signing_service_private_key_tmp_file)

    def test_that_argument_parses_should_fail_gracefully_when_unable_to_decode_base64_value(self):
        sys.argv += [
            '--concent-cluster-host', '127.0.0.1',
            '--concent-public-key', self.concent_public_key_encoded[:-1],
        ]
        with self.assertRaises(Base64DecodeError) as error:
            _parse_arguments()

        self.assertIn(
            f'Unable to decode "{self.concent_public_key_encoded[:-1]}"',
            str(error.exception)
        )


class SigningServiceValidateArgumentsTestCase(TestCase):

    def setUp(self):
        super().setUp()
        self.host = '127.0.0.1'
        self.port = 8000
        self.initial_reconnect_delay = 2

        self.signing_service = SigningService(
            self.host,
            self.port,
            self.initial_reconnect_delay,
            CONCENT_PUBLIC_KEY,
            SIGNING_SERVICE_PRIVATE_KEY,
            TEST_ETHEREUM_PRIVATE_KEY,
            SIGNING_SERVICE_DEFAULT_RECONNECT_ATTEMPTS,
            ConsoleNotifier(),
        )

    def test_that_signing_service__validate_arguments_should_raise_exception_on_port_number_below_or_above_range(self):
        for wrong_port in [0, 65535 + 1]:
            self.signing_service.port = wrong_port

            with self.assertRaises(SigningServiceValidationError):
                self.signing_service._validate_arguments()

    def test_that_signing_service__validate_arguments_should_raise_exception_on_initial_reconnect_delay_lower_than_zero(self):
        self.signing_service.initial_reconnect_delay = -1

        with self.assertRaises(SigningServiceValidationError):
            self.signing_service._validate_arguments()

    def test_that_signing_service__validate_arguments_should_raise_exception_on_wrong_length_of_concent_public_key(self):
        self.signing_service.concent_public_key = CONCENT_PUBLIC_KEY[:-1]

        with self.assertRaises(SigningServiceValidationError):
            self.signing_service._validate_arguments()

    def test_that_signing_service__validate_arguments_should_raise_exception_on_wrong_length_of_ethereum_private_key(self):
        self.signing_service.ethereum_private_key = TEST_ETHEREUM_PRIVATE_KEY[:-1]

        with self.assertRaises(SigningServiceValidationError):
            self.signing_service._validate_arguments()

    def test_that_signing_service__validate_arguments_should_raise_exception_on_wrong_characters_in_ethereum_private_key(self):
        self.signing_service.ethereum_private_key = self.signing_service.ethereum_private_key[:-1] + 'g'

        with self.assertRaises(SigningServiceValidationError):
            self.signing_service._validate_arguments()


class SigningServiceDailyThresholdTestCase(TestCase):

    def setUp(self):
        self.host = '127.0.0.1'
        self.port = 8000
        self.initial_reconnect_delay = 2

        with mock.patch('signing_service.signing_service.SigningService.run'):
            self.signing_service = SigningService(
                self.host,
                self.port,
                self.initial_reconnect_delay,
                CONCENT_PUBLIC_KEY,
                SIGNING_SERVICE_PRIVATE_KEY,
                TEST_ETHEREUM_PRIVATE_KEY,
                SIGNING_SERVICE_DEFAULT_RECONNECT_ATTEMPTS,
                ConsoleNotifier(),
            )

    def test_that_signing_service_get_daily_transaction_threshold_file_directory_should_return_existing_file(self):
        threshold_file = self.signing_service._get_daily_transaction_threshold_file_path()
        self.assertTrue(threshold_file.exists())  # pylint: disable=no-member
        self.assertTrue(threshold_file.is_file())  # pylint: disable=no-member
        threshold_file.unlink()  # pylint: disable=no-member

    def test_that_add_payload_value_to_daily_transactions_sum_write_int_and_get_signing_service_daily_transaction_sum_so_far_returns_correct_value(self):
        threshold_file = self.signing_service._get_daily_transaction_threshold_file_path()
        self.signing_service._add_payload_value_to_daily_transactions_sum(1337)
        transaction_sum = self.signing_service._get_signing_service_daily_transaction_sum_so_far()
        self.assertEqual(transaction_sum, 1337)
        threshold_file.unlink()  # pylint: disable=no-member

    def test_that_signing_service_get_signing_service_daily_transaction_sum_so_far_returns_zero_in_case_of_value_error(self):
        threshold_file = self.signing_service._get_daily_transaction_threshold_file_path()
        threshold_file.write_text('GolemConcent')  # pylint: disable=no-member
        transaction_sum = self.signing_service._get_signing_service_daily_transaction_sum_so_far()
        self.assertEqual(transaction_sum, 0)
        threshold_file.unlink()  # pylint: disable=no-member

    def test_that_signing_service_update_daily_transactions_limit_file_name_overwrite_old_value(self):
        self.signing_service.daily_transactions_limit_file_name = '1970-01-01'
        self.signing_service.signing_service_daily_transaction_sum_so_far = 10000
        self.signing_service._update_daily_transactions_limit_file_name()
        self.assertEqual(self.signing_service.daily_transactions_limit_file_name, datetime.datetime.now().strftime('%Y-%m-%d'))
        self.assertEqual(self.signing_service.signing_service_daily_transaction_sum_so_far, 0)
