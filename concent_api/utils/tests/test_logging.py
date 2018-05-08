from unittest import TestCase
from unittest.mock import patch  # For python 2.x use from mock import patch

import mock

from utils.logging import log_empty_queue, replace_key_to_unavailable_instead_of_none, Message
from utils.testing_helpers import generate_ecc_key_pair

(PRIVATE_KEY, PUBLIC_KEY) = generate_ecc_key_pair()


class ApiViewTestCase(TestCase):

    @patch('utils.logging.logger')
    def test_check_log_empty_queue_schould_log_given_data(self, mock_logger):
        endpoint = 'endpoint_name'
        log_empty_queue(endpoint, PRIVATE_KEY)

        mock_logger.info.assert_called_with('A message queue is empty in `{}()` -- CLIENT PUBLIC KEY: {}'.format(
            endpoint,
            PRIVATE_KEY,
        ))


class ReplaceKeyToUnavailableInsteadOfNoneTestCase(TestCase):

    def test_foo(self):
        m = mock.Mock()
        decorated = replace_key_to_unavailable_instead_of_none(m)

        decorated(1, None, a=2, b=None)

        m.assert_called_once_with(1, 'UNAVAILABLE', a=2, b='UNAVAILABLE')

    def test_foo1(self):
        m = mock.Mock()
        decorated = replace_key_to_unavailable_instead_of_none(m)
        decorated(1, None, a=2, b=3)
        m.assert_called_once_with(1, 'UNAVAILABLE', a=2, b=3)

    def test_that_single_element_should_be_returned(self):
        m = mock.Mock()
        decorated = replace_key_to_unavailable_instead_of_none(m)
        decorated(1)
        m.assert_called_once_with(1)

        m = mock.Mock()
        decorated = replace_key_to_unavailable_instead_of_none(m)
        decorated('any string')
        m.assert_called_once_with('any string')

        m = mock.Mock()
        decorated = replace_key_to_unavailable_instead_of_none(m)
        decorated(PRIVATE_KEY)
        m.assert_called_once_with(PRIVATE_KEY)

        message = mock.create_autospec(spec=Message)
        m = mock.Mock()
        decorated = replace_key_to_unavailable_instead_of_none(m)
        decorated(message)
        m.assert_called_once_with(message)

        m = mock.Mock()
        decorated = replace_key_to_unavailable_instead_of_none(m)
        decorated(a=1)
        m.assert_called_once_with(a=1)

        m = mock.Mock()
        decorated = replace_key_to_unavailable_instead_of_none(m)
        decorated(a='any string')
        m.assert_called_once_with(a='any string')

        m = mock.Mock()
        decorated = replace_key_to_unavailable_instead_of_none(m)
        decorated(a=PRIVATE_KEY)
        m.assert_called_once_with(a=PRIVATE_KEY)

        m = mock.Mock()
        decorated = replace_key_to_unavailable_instead_of_none(m)
        decorated(a=message)
        m.assert_called_once_with(a=message)

    def test_that_single_none_should_be_changed_to_unavailable(self):
        m = mock.Mock()
        decorated = replace_key_to_unavailable_instead_of_none(m)
        decorated(None)
        m.assert_called_once_with('UNAVAILABLE')

        m = mock.Mock()
        decorated = replace_key_to_unavailable_instead_of_none(m)
        decorated(a=None)
        m.assert_called_once_with(a='UNAVAILABLE')

    def test_that_all_none_should_be_changed_to_unavailable(self):
        m = mock.Mock()
        decorated = replace_key_to_unavailable_instead_of_none(m)
        decorated(None, None, None)
        m.assert_called_once_with('UNAVAILABLE', 'UNAVAILABLE', 'UNAVAILABLE')

    def test_that_custom_args_should_be_changed_correctly(self):
        message = mock.create_autospec(spec=Message)
        m = mock.Mock()
        decorated = replace_key_to_unavailable_instead_of_none(m)
        decorated(None, 1, 'any string', message, None, None, PRIVATE_KEY)
        m.assert_called_once_with('UNAVAILABLE', 1, 'any string', message, 'UNAVAILABLE', 'UNAVAILABLE', PRIVATE_KEY)

    def test_that_custom_kwargs_should_be_changed_correctly(self):
        message = mock.create_autospec(spec=Message)
        m = mock.Mock()
        decorated = replace_key_to_unavailable_instead_of_none(m)
        decorated(a=None, b=1, c='any string', d=message, e=None, f=None, g=PRIVATE_KEY)
        m.assert_called_once_with(a='UNAVAILABLE', b=1, c='any string', d=message, e='UNAVAILABLE', f='UNAVAILABLE', g=PRIVATE_KEY)

    def test_that_custom_args_and_kwargs_should_be_changed_correctly(self):
        message = mock.create_autospec(spec=Message)
        m = mock.Mock()
        decorated = replace_key_to_unavailable_instead_of_none(m)
        decorated(None, 1, 'any string', message, e=None, f=None, g=PRIVATE_KEY)
        m.assert_called_once_with('UNAVAILABLE', 1, 'any string', message, e='UNAVAILABLE', f='UNAVAILABLE', g=PRIVATE_KEY)
