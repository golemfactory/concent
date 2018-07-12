from unittest import TestCase
import sys

import mock

from ..constants import SIGNING_SERVICE_DEFAULT_PORT
from ..signing_service import _parse_arguments
from ..signing_service import main


class SigningServiceMainTestCase(TestCase):

    def test_that_main_should_exit_when_called_with_wrong_host(self):
        with self.assertRaises(SystemExit):
            main('not_really_ip_or_host', 8000)

    def test_that_main_should_work_correctly_when_called_with_correct_parameters(self):  # pylint: disable=no-self-use
        with mock.patch('socket.socket.connect') as mock_socket_connect:
            with mock.patch('socket.socket.send') as mock_socket_send:
                with mock.patch('socket.socket.recv') as mock_socket_recv:
                    with mock.patch('socket.socket.close') as mock_socket_close:
                        main('127.0.0.1', 8000)

        mock_socket_connect.assert_called_once_with(('127.0.0.1', 8000))
        mock_socket_send.assert_called_once()
        mock_socket_recv.assert_called_once()
        mock_socket_close.assert_called_once()


class SigningServiceParseArgumentsTestCase(TestCase):

    def setUp(self):
        super().setUp()
        # ArgumentParser takes values directly from sys.argv, but the test runner has its own arguments,
        # so they have to be replaced.
        sys.argv = sys.argv[:1]

    def test_that_argument_parser_should_parse_correct_input(self):
        sys.argv += ['127.0.0.1', '--concent-cluster-port', '8000']

        args = _parse_arguments()

        self.assertEqual(args.concent_cluster_host, '127.0.0.1')
        self.assertEqual(args.concent_cluster_port, 8000)

    def test_that_argument_parser_should_parse_correct_input_and_use_default_port(self):
        sys.argv += ['127.0.0.1']

        args = _parse_arguments()

        self.assertEqual(args.concent_cluster_host, '127.0.0.1')
        self.assertEqual(args.concent_cluster_port, SIGNING_SERVICE_DEFAULT_PORT)

    def test_that_argument_parser_should_fail_if_port_cannot_be_casted_to_int(self):
        sys.argv += ['127.0.0.1', '--concent-cluster-port', 'abc']

        with self.assertRaises(SystemExit):
            _parse_arguments()

    def test_that_argument_parser_should_fail_if_host_is_missing(self):
        with self.assertRaises(SystemExit):
            _parse_arguments()
