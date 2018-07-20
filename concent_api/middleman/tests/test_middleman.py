import asyncio
import os
import signal
import socket
import threading
import time

from assertpy import assert_that
import mock
import pytest

from middleman.constants import DEFAULT_INTERNAL_PORT
from middleman.constants import ERROR_ADDRESS_ALREADY_IN_USE
from middleman.constants import LOCALHOST_IP
from middleman.middleman_server import MiddleMan


class Connections():
    def __init__(self):
        self.counter = 0


def assert_connection(port, delay, connection_counter):
    message = "hello\n"
    fake_client = socket.socket()
    send_data(fake_client, message, port, delay)
    data = fake_client.recv(1024)
    fake_client.close()
    assert_that(data.decode()).is_equal_to(message)
    connection_counter.counter += 1


def send_data(fake_client, message, port, delay):
    time.sleep(delay)
    fake_client.settimeout(1)
    fake_client.connect((LOCALHOST_IP, port))
    fake_client.send(message.encode())


def trigger_signal(pid, delay):
    time.sleep(delay)
    os.kill(pid, signal.SIGINT)


def schedule_sigterm(delay):
    pid = os.getpid()
    thread = threading.Thread(target=trigger_signal, args=(pid, delay,))
    thread.start()


def get_client_thread(fun, *args):
    client_thread = threading.Thread(target=fun, args=args)
    return client_thread


class TestMiddleManInitialization:
    def test_that_middleman_is_created_with_given_params(self, unused_tcp_port, event_loop):  # pylint: disable=no-self-use
        ip = "127.1.0.1"
        middleman = MiddleMan(bind_address=ip, internal_port=(unused_tcp_port), loop=event_loop)

        assert_that(middleman._bind_address).is_equal_to(ip)
        assert_that(middleman._internal_port).is_equal_to(unused_tcp_port)
        assert_that(middleman._loop).is_equal_to(event_loop)

    def test_that_middleman_is_created_with_default_params(self):  # pylint: disable=no-self-use
        middleman = MiddleMan()

        assert_that(middleman._bind_address).is_equal_to(LOCALHOST_IP)
        assert_that(middleman._internal_port).is_equal_to(DEFAULT_INTERNAL_PORT)
        assert_that(middleman._loop).is_equal_to(asyncio.get_event_loop())


class TestMiddleManServer:
    patcher = None
    crash_logger_mock = None

    def setup_method(self):
        self.patcher = mock.patch("middleman.middleman_server.crash_logger")
        self.crash_logger_mock = self.patcher.start()

    def teardown_method(self):
        self.patcher.stop()

    def test_that_if_keyboard_interrupt_is_raised_application_will_exit_without_errors(self, unused_tcp_port, event_loop):
        with pytest.raises(SystemExit) as exception_wrapper:
            middleman = MiddleMan(internal_port=unused_tcp_port, loop=event_loop)
            with mock.patch.object(middleman, "_run_forever", side_effect=KeyboardInterrupt):
                middleman.run()
        assert_that(exception_wrapper.value.code).is_equal_to(None)
        self.crash_logger_mock.assert_not_called()

    @mock.patch("middleman.middleman_server.asyncio.start_server", side_effect=OSError)
    def test_that_if_chosen_port_is_already_used_application_will_exit_with_error_status(self,  _start_server_mock, unused_tcp_port, event_loop):
        with pytest.raises(SystemExit) as exception_wrapper:
            MiddleMan(internal_port=unused_tcp_port, loop=event_loop).run()
        assert_that(exception_wrapper.value.code).is_equal_to(ERROR_ADDRESS_ALREADY_IN_USE)
        self.crash_logger_mock.assert_not_called()

    def test_that_if_sigterm_is_sent_application_will_exit_without_errors(self, unused_tcp_port, event_loop):
        schedule_sigterm(delay=1)
        with pytest.raises(SystemExit) as exception_wrapper:
            MiddleMan(internal_port=unused_tcp_port, loop=event_loop).run()
        assert_that(exception_wrapper.value.code).is_equal_to(None)
        self.crash_logger_mock.assert_not_called()

    def test_that_crash_of_the_server_is_reported_to_sentry(self, unused_tcp_port, event_loop):
        middleman = MiddleMan(internal_port=unused_tcp_port, loop=event_loop)
        error_message = "Unrecoverable error"
        with mock.patch.object(middleman, "_run_forever", side_effect=Exception(error_message)):
            middleman.run()
        self.crash_logger_mock.error.assert_called_once()
        assert_that(self.crash_logger_mock.error.mock_calls[0][1][0]).contains(error_message)

    def test_that_server_accepts_connections_and_sends_data_back(self, event_loop, unused_tcp_port):
        timeout = 2
        short_delay = 0.5
        schedule_sigterm(delay=timeout)
        connections = Connections()
        client_thread = get_client_thread(assert_connection, unused_tcp_port, short_delay, connections)
        client_thread.start()

        with pytest.raises(SystemExit) as exception_wrapper:
            MiddleMan(internal_port=unused_tcp_port, loop=event_loop).run()

        client_thread.join(timeout)
        assert_that(exception_wrapper.value.code).is_equal_to(None)
        self.crash_logger_mock.assert_not_called()
        assert_that(connections.counter).is_equal_to(1)

    def test_that_broken_connection_is_reported_to_sentry(self, event_loop, unused_tcp_port):
        timeout = 2
        short_delay = 0.5
        schedule_sigterm(delay=timeout)
        fake_client = socket.socket()
        client_thread = get_client_thread(send_data, fake_client, "Oi!\n", unused_tcp_port, short_delay)
        client_thread.start()

        middleman = MiddleMan(internal_port=unused_tcp_port, loop=event_loop)
        error_message = "Connection_error"

        with mock.patch.object(middleman, "_respond_to_user", side_effect=Exception(error_message)):
            with pytest.raises(SystemExit):
                middleman.run()
        client_thread.join(timeout)
        fake_client.close()
        self.crash_logger_mock.error.assert_called_once()
        assert_that(self.crash_logger_mock.error.mock_calls[0][1][0]).contains(error_message)
