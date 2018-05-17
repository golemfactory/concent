from unittest import TestCase
from unittest.mock import patch

import mock

from utils.logging import log_empty_queue, replace_element_to_unavailable_instead_of_none, Message
from utils.testing_helpers import generate_ecc_key_pair

(PRIVATE_KEY, PUBLIC_KEY) = generate_ecc_key_pair()


# pylint: disable=R0201
class ApiViewTestCase(TestCase):

    @patch('utils.logging.logger')
    def test_check_log_empty_queue_schould_log_given_data(self, mock_logger):
        endpoint = 'endpoint_name'
        log_empty_queue(endpoint, PRIVATE_KEY)

        mock_logger.info.assert_called_with('A message queue is empty in `{}()` -- CLIENT PUBLIC KEY: {}'.format(
            endpoint,
            PRIVATE_KEY,
        ))


# pylint: disable=R0201
class ReplaceElementToUnavailableInsteadOfNoneTestCase(TestCase):

    def test_that_all_none_should_be_changed_to_unavailable_when_only_args_given(self):
        message = mock.create_autospec(spec=Message)
        m = mock.Mock()
        decorated = replace_element_to_unavailable_instead_of_none(m)
        decorated(None, 1, 'any string', message, None, None, PRIVATE_KEY)
        m.assert_called_once_with('UNAVAILABLE', 1, 'any string', message, 'UNAVAILABLE', 'UNAVAILABLE', PRIVATE_KEY)

    def test_that_all_none_should_be_changed_to_unavailable_when_only_kwargs_given(self):
        message = mock.create_autospec(spec=Message)
        m = mock.Mock()
        decorated = replace_element_to_unavailable_instead_of_none(m)
        decorated(a=None, b=1, c='any string', d=message, e=None, f=None, g=PRIVATE_KEY)
        m.assert_called_once_with(a='UNAVAILABLE', b=1, c='any string', d=message, e='UNAVAILABLE', f='UNAVAILABLE',
                                  g=PRIVATE_KEY)

    def test_that_all_none_should_be_changed_to_unavailable_when_args_and_kwargs_given(self):
        message = mock.create_autospec(spec=Message)
        m = mock.Mock()
        decorated = replace_element_to_unavailable_instead_of_none(m)
        decorated(None, 1, 'any string', message, e=None, f=None, g=PRIVATE_KEY)
        m.assert_called_once_with('UNAVAILABLE', 1, 'any string', message, e='UNAVAILABLE', f='UNAVAILABLE',
                                  g=PRIVATE_KEY)
