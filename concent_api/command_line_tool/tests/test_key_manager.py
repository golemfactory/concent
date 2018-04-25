from unittest import TestCase

import key_manager


PUBLIC_KEY_LENGTH = 64
PRIVATE_KEY_LENGTH = 32

PREDEFINED_REQUESOTR_PRIVATE_KEY = b's\xba\xe2O6$\x04z\x87?\xec\xa1;\xe8\xaa\xae\xc2\x97^(\xe6ps8\xe71P-\xd2\x12\x93s'
PREDEFINED_REQUESTOR_PUBLIC_KEY = b'E\xee\x8b\xa1\xa2NcE\x87\xd5=\x0c)2\xef\x99\xfdYO\xd4\xc6UbJ\xa5\xb6\xe8\xdf\xc4SW\xc6X\xe2\xa9R\xe2-\xac\xe2h\x8cf\xadt9\x05\x1eF\x99\x0b\xbb{\xf7\x0f\x0eW[m"}\xdcBL'
PREDEFINED_PROVIDER_PRIVATE_KEY = b'\xff`\xe9\xf2\x10DA\xa7g\x02\x00K}\x83\x1d\xff\t\x81\xd1.C\x1bQQ\x80\xdc\xe6\x7f6\xec\x18D'
PREDEFINED_PROVIDER_PUBLIC_KEY = b"\xd4\x8b\xf9\x91\x88 PDS{\x1fr\xbfb\xa6z\xc4\xfd'\xb2wb\xb1\x1d\x90\xfa\xa8Y\xdb\x9a\xea#\xc3 \x1fO\xfbNRt=\xea4%XZ>P\xc9\x05!\xa7\xf6\x1c\x15\xd9\x7f\x17G\x1f[\xf0&\x83"


class TestKeyManager(TestCase):
    def setUp(self):
        key_manager.REQUESTOR_PRIVATE_KEY = None
        key_manager.REQUESTOR_PUBLIC_KEY = None
        key_manager.PROVIDER_PRIVATE_KEY = None
        key_manager.PROVIDER_PUBLIC_KEY = None

    def test_that_new_instance_generates_new_keys_for_requestor_when_globals_not_set(self):
        requestor_public_key, requestor_private_key = key_manager.KeyManager().get_requestor_keys()
        new_requestor_public_key, new_requestor_private_key = key_manager.KeyManager().get_requestor_keys()

        self._assert_keys_are_not_equal(requestor_public_key, new_requestor_public_key, "public")
        self._assert_keys_are_not_equal(requestor_private_key, new_requestor_private_key, "private")

    def test_that_new_instance_generates_new_keys_for_provider_when_globals_not_set(self):
        provider_public_key, provider_private_key = key_manager.KeyManager().get_provider_keys()
        new_provider_public_key, new_provider_private_key = key_manager.KeyManager().get_provider_keys()

        self._assert_keys_are_not_equal(new_provider_public_key, provider_public_key, "public")
        self._assert_keys_are_not_equal(provider_private_key, new_provider_private_key, "private")

    def test_that_key_pairs_are_distinct_for_provider_and_requestor(self):
        manager = key_manager.KeyManager()
        provider_public_key, provider_private_key = manager.get_provider_keys()
        requestor_public_key, requestor_private_key = manager.get_requestor_keys()

        self._assert_keys_are_not_equal(provider_public_key, requestor_public_key, "public")
        self._assert_keys_are_not_equal(provider_private_key, requestor_private_key, "private")

    def test_that_requestor_predefined_keys_are_returned_when_set(self):
        key_manager.REQUESTOR_PUBLIC_KEY = PREDEFINED_REQUESTOR_PUBLIC_KEY
        key_manager.REQUESTOR_PRIVATE_KEY = PREDEFINED_REQUESOTR_PRIVATE_KEY
        requestor_public_key, requestor_private_key = key_manager.KeyManager().get_requestor_keys()

        self.assertEqual(requestor_public_key, PREDEFINED_REQUESTOR_PUBLIC_KEY)
        self.assertEqual(requestor_private_key, PREDEFINED_REQUESOTR_PRIVATE_KEY)

    def test_that_provider_predefined_keys_are_returned_when_set(self):
        key_manager.PROVIDER_PUBLIC_KEY = PREDEFINED_PROVIDER_PUBLIC_KEY
        key_manager.PROVIDER_PRIVATE_KEY = PREDEFINED_PROVIDER_PRIVATE_KEY
        provider_public_key, provider_private_key = key_manager.KeyManager().get_provider_keys()

        self.assertEqual(provider_public_key, PREDEFINED_PROVIDER_PUBLIC_KEY)
        self.assertEqual(provider_private_key, PREDEFINED_PROVIDER_PRIVATE_KEY)

    def _assert_keys_are_not_equal(self, first_key, second_key, key_type):
        getattr(self, f"_assert_is_valid_{key_type}_key")(first_key)
        getattr(self, f"_assert_is_valid_{key_type}_key")(second_key)
        self.assertNotEqual(first_key, second_key)

    def _assert_is_valid_public_key(self, key_to_check):
        self.assertEqual(type(key_to_check), bytes)
        self.assertEqual(len(key_to_check), PUBLIC_KEY_LENGTH)

    def _assert_is_valid_private_key(self, key_to_check):
        self.assertEqual(type(key_to_check), bytes)
        self.assertEqual(len(key_to_check), PRIVATE_KEY_LENGTH)
