from logging import getLogger
from unittest import TestCase

import mock

from utils.logging import Message
from utils.logging import replace_element_to_unavailable_instead_of_none
from utils.testing_helpers import generate_ecc_key_pair

(PRIVATE_KEY, PUBLIC_KEY) = generate_ecc_key_pair()

logger = getLogger(__name__)


# pylint: disable=R0201
class ReplaceElementToUnavailableInsteadOfNoneTestCase(TestCase):

    def test_that_all_none_should_be_changed_to_unavailable_when_only_args_given(self):
        message = mock.create_autospec(spec=Message)
        m = mock.Mock()
        decorated = replace_element_to_unavailable_instead_of_none(m)
        decorated(None, 1, 'any string', message, None, None, PRIVATE_KEY)
        m.assert_called_once_with('-not available-', 1, 'any string', message, '-not available-', '-not available-', PRIVATE_KEY)

    def test_that_all_none_should_be_changed_to_unavailable_when_only_kwargs_given(self):
        message = mock.create_autospec(spec=Message)
        m = mock.Mock()
        decorated = replace_element_to_unavailable_instead_of_none(m)
        decorated(a=None, b=1, c='any string', d=message, e=None, f=None, g=PRIVATE_KEY)
        m.assert_called_once_with(a='-not available-', b=1, c='any string', d=message, e='-not available-', f='-not available-',
                                  g=PRIVATE_KEY)

    def test_that_all_none_should_be_changed_to_unavailable_when_args_and_kwargs_given(self):
        message = mock.create_autospec(spec=Message)
        m = mock.Mock()
        decorated = replace_element_to_unavailable_instead_of_none(m)
        decorated(None, 1, 'any string', message, e=None, f=None, g=PRIVATE_KEY)
        m.assert_called_once_with('-not available-', 1, 'any string', message, e='-not available-', f='-not available-',
                                  g=PRIVATE_KEY)
