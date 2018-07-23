from base64         import b64encode

from freezegun      import freeze_time
from django.conf    import settings
from django.http    import JsonResponse
from django.test    import override_settings
from django.urls    import reverse

from golem_messages.shortcuts       import dump
from golem_messages.message         import FileTransferToken
from golem_messages.factories.concents import FileTransferTokenFactory

from core.tests.utils                import ConcentIntegrationTestCase
from common.constants                import ErrorCode
from common.helpers                  import get_current_utc_timestamp
from common.helpers                  import get_storage_result_file_path


@override_settings(
    CONCENT_PRIVATE_KEY = b'l\xcdh\x19\xeb$>\xbcG\xa1\xc7v\xe8\xd7o\x0c\xbf\x0e\x0fM\x89lw\x1e\xd7K\xd6Hnv$\xa2',
    CONCENT_PUBLIC_KEY  = b'\xf3\x97\x19\xcdX\xda\x86tiP\x1c&\xd39M\x9e\xa4\xddb\x89\xb5,]O\xd5cR\x84\xb85\xed\xc9\xa17e,\xb2s\xeb\n1\xcaN.l\xba\xc3\xb7\xc2\xba\xff\xabN\xde\xb3\x0b\xa6l\xbf6o\x81\xe0;',
    STORAGE_CLUSTER_ADDRESS = 'http://devel.concent.golem.network/'
)
class GatekeeperViewUploadTest(ConcentIntegrationTestCase):

    @freeze_time("2018-12-30 11:00:00")
    def setUp(self):
        self.message_timestamp  = get_current_utc_timestamp()
        self.public_key         = '85cZzVjahnRpUBwm0zlNnqTdYom1LF1P1WNShLg17cmhN2UssnPrCjHKTi5susO3wrr/q07eswumbL82b4HgOw=='
        self.upload_token = FileTransferTokenFactory(
            token_expiration_deadline=self.message_timestamp + 3600,
            storage_cluster_address='http://devel.concent.golem.network/',
            authorized_client_public_key=settings.CONCENT_PUBLIC_KEY,
            operation=FileTransferToken.Operation.upload,
        )
        self.upload_token.files[0]['path']      = 'blender/benchmark/test_task/scene-Helicopter-27-cycles.blend'
        self.upload_token.files[0]['checksum']  = 'sha1:95a0f391c7ad86686ab1366bcd519ba5ab3cce89'

        self.header_concent_auth = self._create_client_auth_message_as_header(
            settings.CONCENT_PRIVATE_KEY,
            settings.CONCENT_PUBLIC_KEY,
        )

    @freeze_time("2018-12-30 11:00:00")
    def test_upload_should_accept_valid_message(self):
        golem_upload_token = dump(self.upload_token, settings.CONCENT_PRIVATE_KEY, settings.CONCENT_PUBLIC_KEY)
        encoded_token = b64encode(golem_upload_token).decode()
        response = self.client.post(
            '{}{}'.format(
                reverse('gatekeeper:upload'),
                'blender/benchmark/test_task/scene-Helicopter-27-cycles.blend'
            ),
            content_type='application/octet-stream',
            HTTP_AUTHORIZATION = 'Golem ' + encoded_token,
            HTTP_CONCENT_AUTH=self.header_concent_auth,
        )

        self.assertIsInstance(response, JsonResponse)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.has_header("Concent-File-Size"))
        self.assertTrue(response.has_header("Concent-File-Checksum"))
        self.assertEqual("application/json", response["Content-Type"])

    @freeze_time("2018-12-30 11:00:00")
    def test_upload_should_return_401_if_wrong_request_content_type(self):
        golem_upload_token = dump(self.upload_token, settings.CONCENT_PRIVATE_KEY, settings.CONCENT_PUBLIC_KEY)
        encoded_token = b64encode(golem_upload_token).decode()
        response = self.client.post(
            '{}{}'.format(
                reverse('gatekeeper:upload'),
                'blender/benchmark/test_task/scene-Helicopter-27-cycles.blend'
            ),
            HTTP_AUTHORIZATION = 'Golem ' + encoded_token,
            HTTP_CONCENT_AUTH=self.header_concent_auth,
            content_type = '',
        )

        self.assertIsInstance(response, JsonResponse)
        self.assertEqual(response.status_code, 401)
        self.assertIn('message', response.json().keys())
        self.assertIn('error_code', response.json().keys())
        self.assertEqual(response.json()["error_code"], ErrorCode.HEADER_CONTENT_TYPE_NOT_SUPPORTED.value)

    @freeze_time("2018-12-30 12:00:01")
    def test_upload_should_return_401_if_message_token_deadline_pass(self):
        golem_upload_token = dump(self.upload_token, settings.CONCENT_PRIVATE_KEY, settings.CONCENT_PUBLIC_KEY)
        encoded_token = b64encode(golem_upload_token).decode()
        response = self.client.post(
            '{}{}'.format(
                reverse('gatekeeper:upload'),
                'blender/benchmark/test_task/scene-Helicopter-27-cycles.blend'
            ),
            HTTP_AUTHORIZATION = 'Golem ' + encoded_token,
            HTTP_CONCENT_AUTH=self.header_concent_auth,
            content_type = 'application/x-www-form-urlencoded',
        )

        self.assertIsInstance(response, JsonResponse)
        self.assertEqual(response.status_code, 401)
        self.assertIn('message', response.json().keys())
        self.assertEqual(response.json()["error_code"], ErrorCode.AUTH_CLIENT_AUTH_MESSAGE_INVALID.value)

    @freeze_time("2018-12-30 11:00:00")
    def test_upload_should_return_401_if_file_paths_are_not_unique(self):
        file1 = FileTransferToken.FileInfo(
            path     = 'blender/benchmark/test_task/scene-Helicopter-27-cycles.blend',
            checksum = 'sha1:95a0f391c7ad86686ab1366bcd519ba5ab3cce89',
            size     = 1024,
        )

        file2 = FileTransferToken.FileInfo(
            path     = 'blender/benchmark/test_task/scene-Helicopter-27-cycles.blend',
            checksum = 'sha1:95a0f391c7ad86686ab1366bcd519ba5ab3cce89',
            size     = 1024,
        )

        self.upload_token.files = [file1, file2]
        assert file1 == file2

        golem_upload_token = dump(self.upload_token, settings.CONCENT_PRIVATE_KEY, settings.CONCENT_PUBLIC_KEY)
        encoded_token = b64encode(golem_upload_token).decode()
        response = self.client.post(
            '{}{}'.format(
                reverse('gatekeeper:upload'),
                'blender/benchmark/test_task/scene-Helicopter-27-cycles.blend'
            ),
            HTTP_AUTHORIZATION             = 'Golem ' + encoded_token,
            HTTP_CONCENT_AUTH=self.header_concent_auth,
            content_type                   = 'application/x-www-form-urlencoded',
        )

        self.assertIsInstance(response, JsonResponse)
        self.assertEqual(response.status_code, 401)
        self.assertIn('message', response.json().keys())
        self.assertIn('error_code', response.json().keys())
        self.assertEqual("application/json", response["Content-Type"])
        self.assertEqual(response.json()["error_code"], ErrorCode.MESSAGE_FILES_PATHS_NOT_UNIQUE.value)

    @freeze_time("2018-12-30 11:00:00")
    def test_upload_should_return_401_if_checksum_is_wrong(self):
        invalid_values_with_expected_error_code = {
            b'sha1:95a0f391c7ad86686ab1366bcd519ba5ab3cce89':   ErrorCode.MESSAGE_FILES_CHECKSUM_WRONG_TYPE,
            '':                                                 ErrorCode.MESSAGE_FILES_CHECKSUM_EMPTY,
            '95a0f391c7ad86686ab1366bcd519ba5ab3cce89':         ErrorCode.MESSAGE_FILES_CHECKSUM_WRONG_FORMAT,
            ':95a0f391c7ad86686ab1366bcd519ba5ab3cce89':        ErrorCode.MESSAGE_FILES_CHECKSUM_INVALID_ALGORITHM,
            'sha1:95a0f391c7ad86686ab1366bcd519ba5amONj':       ErrorCode.MESSAGE_FILES_CHECKSUM_INVALID_SHA1_HASH,
            'sha1:':                                            ErrorCode.MESSAGE_FILES_CHECKSUM_INVALID_SHA1_HASH,
        }

        for invalid_value, error_code in invalid_values_with_expected_error_code.items():
            file1 = FileTransferToken.FileInfo(
                path     = 'blender/benchmark/test_task/scene-Helicopter-27-cycles.blend',
                checksum = 'sha1:95a0f391c7ad86686ab1366bcd519ba5ab3cce89',
                size     = 1024,
            )

            file2 = FileTransferToken.FileInfo(
                path     = 'blenderrr/benchmark/test_task/scene-Helicopter-27-cycles.blend',
                checksum = invalid_value,
                size     = 1024,
            )

            self.upload_token.files = [file1, file2]
            self.upload_token.sig   = None

            golem_upload_token = dump(self.upload_token, settings.CONCENT_PRIVATE_KEY, settings.CONCENT_PUBLIC_KEY)
            encoded_token = b64encode(golem_upload_token).decode()
            response = self.client.post(
                '{}{}'.format(
                    reverse('gatekeeper:upload'),
                    'blender/benchmark/test_task/scene-Helicopter-27-cycles.blend'
                ),
                HTTP_AUTHORIZATION             = 'Golem ' + encoded_token,
                HTTP_CONCENT_AUTH=self.header_concent_auth,
                content_type                   = 'application/x-www-form-urlencoded',
            )

            self.assertIsInstance(response, JsonResponse)
            self.assertEqual(response.status_code, 401)
            self.assertIn('message', response.json().keys())
            self.assertIn('error_code', response.json().keys())
            self.assertEqual("application/json", response["Content-Type"])
            self.assertEqual(response.json()["error_code"], error_code.value)

    @freeze_time("2018-12-30 11:00:00")
    def test_upload_should_return_401_if_size_of_file_is_wrong(self):
        invalid_values_with_expected_error_code = {
            None: ErrorCode.MESSAGE_FILES_SIZE_EMPTY,
            'number': ErrorCode.MESSAGE_FILES_SIZE_WRONG_TYPE,
            '-2': ErrorCode.MESSAGE_FILES_SIZE_NEGATIVE,
            '1.0': ErrorCode.MESSAGE_FILES_SIZE_WRONG_TYPE,
        }

        for invalid_value, error_code in invalid_values_with_expected_error_code.items():
            file1 = FileTransferToken.FileInfo(
                path     = 'blender/benchmark/test_task/scene-Helicopter-27-cycles.blend',
                checksum = 'sha1:95a0f391c7ad86686ab1366bcd519ba5ab3cce89',
                size     = 1024,
            )

            file2 = FileTransferToken.FileInfo(
                path     = 'blenderrr/benchmark/test_task/scene-Helicopter-27-cycles.blend',
                checksum = 'sha1:95a0f391c7ad86686ab1366bcd519ba5ab3cce89',
                size     = invalid_value,
            )

            self.upload_token.files = [file1, file2]
            self.upload_token.sig   = None

            golem_upload_token = dump(self.upload_token, settings.CONCENT_PRIVATE_KEY, settings.CONCENT_PUBLIC_KEY)
            encoded_token = b64encode(golem_upload_token).decode()
            response = self.client.post(
                '{}{}'.format(
                    reverse('gatekeeper:upload'),
                    'blender/benchmark/test_task/scene-Helicopter-27-cycles.blend'
                ),
                HTTP_AUTHORIZATION             = 'Golem ' + encoded_token,
                HTTP_CONCENT_AUTH=self.header_concent_auth,
                content_type                   = 'application/x-www-form-urlencoded',
            )

            self.assertIsInstance(response, JsonResponse)
            self.assertEqual(response.status_code, 401)
            self.assertIn('message', response.json().keys())
            self.assertEqual("application/json", response["Content-Type"])
            self.assertEqual(response.json()["error_code"], error_code.value)

    @freeze_time("2018-12-30 11:00:00")
    def test_upload_should_return_401_if_newlines_in_message_checksum(self):
        invalid_values_with_expected_error_code = {
            's\nha1:95a0f391c7ad866\n86ab1366bcd519ba5ab3cce89': ErrorCode.MESSAGE_FILES_CHECKSUM_INVALID_ALGORITHM,
            '\nsha1:95a0f391c7ad86686ab1366bcd519ba5ab3cce89': ErrorCode.MESSAGE_FILES_CHECKSUM_INVALID_ALGORITHM,
            'sha1:95a0f391c7ad86686ab1366bcd519ba5ab3cce89\n': ErrorCode.MESSAGE_FILES_CHECKSUM_INVALID_SHA1_HASH,
        }

        for value, error_code in invalid_values_with_expected_error_code.items():
            file = FileTransferToken.FileInfo(
                path     = 'blender/benchmark/test_task/scene-Helicopter-27-cycles.blend',
                size     = 1024,
            )

            self.upload_token.files = [file]
            self.upload_token.files[0]['checksum'] = value
            self.upload_token.sig = None

            golem_upload_token = dump(self.upload_token, settings.CONCENT_PRIVATE_KEY, settings.CONCENT_PUBLIC_KEY)
            encoded_token = b64encode(golem_upload_token).decode()
            response = self.client.post(
                '{}{}'.format(
                    reverse('gatekeeper:upload'),
                    'blender/benchmark/test_task/scene-Helicopter-27-cycles.blend'
                ),
                HTTP_AUTHORIZATION             = 'Golem ' + encoded_token,
                HTTP_CONCENT_AUTH=self.header_concent_auth,
                content_type                   = 'application/x-www-form-urlencoded',
            )

            self.assertIsInstance(response, JsonResponse)
            self.assertEqual(response.status_code, 401)
            self.assertIn('message', response.json().keys())
            self.assertEqual("application/json", response["Content-Type"])
            self.assertEqual(response.json()["error_code"], error_code.value)

    @freeze_time("2018-12-30 11:00:00")
    def test_upload_should_return_401_if_newlines_in_message_path(self):
        invalid_values_with_expected_error_code = {
            'blen\nder/benchmark/test_task/scene-Helicopter-2\n7-cycles.blend': ErrorCode.MESSAGE_FILES_PATH_NOT_LISTED_IN_FILES,
            '\nblender/benchmark/test_task/scene-Helicopter-27-cycles.blend': ErrorCode.MESSAGE_FILES_PATH_NOT_LISTED_IN_FILES,
            'blender/benchmark/test_task/scene-Helicopter-27-cycles.blend\n': ErrorCode.MESSAGE_FILES_PATH_NOT_LISTED_IN_FILES,
        }

        for value, error_code in invalid_values_with_expected_error_code.items():
            file = FileTransferToken.FileInfo(
                path     = value,
                checksum = 'sha1:95a0f391c7ad86686ab1366bcd519ba5ab3cce89',
                size     = 1024,
            )

            self.upload_token.files = [file]
            self.upload_token.sig   = None

            golem_upload_token = dump(self.upload_token, settings.CONCENT_PRIVATE_KEY, settings.CONCENT_PUBLIC_KEY)
            encoded_token = b64encode(golem_upload_token).decode()
            response = self.client.post(
                '{}{}'.format(
                    reverse('gatekeeper:upload'),
                    'blender/benchmark/test_task/scene-Helicopter-27-cycles.blend'
                ),
                HTTP_AUTHORIZATION             = 'Golem ' + encoded_token,
                HTTP_CONCENT_AUTH=self.header_concent_auth,
                content_type                   = 'application/x-www-form-urlencoded',
            )

            self.assertIsInstance(response, JsonResponse)
            self.assertEqual(response.status_code, 401)
            self.assertIn('message', response.json().keys())
            self.assertIn('error_code', response.json().keys())
            self.assertEqual("application/json", response["Content-Type"])
            self.assertEqual(response.json()["error_code"], error_code.value)

    @freeze_time("2018-02-12 16:19:00")
    def test_upload_should_return_401_if_previously_causing_500_error_authorization_header_is_used(self):

        response = self.client.post(
            '{}{}'.format(
                reverse('gatekeeper:upload'),
                get_storage_result_file_path(
                    task_id=1,
                    subtask_id=2,
                ),
            ),
            HTTP_AUTHORIZATION             = 'Golem D6UAAAAAWoG9YgGsJib/zgj2cAHGXunyxI7t2NYnHKPvrdzVkdT/B58TpQHpdfonuWy8sWq9nrpc9+/1nUTm8O9szLOrFrCPKL7hAQRWLO4JCR6cVGILFbqRKX6abR1AKMLqRUa/ucH5t0YrLe/OPEp6+2swgbRgcnu0dlvfaupn9bwRPZhjVc2hJlDlkz+7aRx+NDEFWQeRHt3q7b8vA0xd/UUvPGudSnzGR6DaM1+Ji4PifQ7AUdYkQHmRNP4yZH+xjCq706J8mftrySj2geoP+TLKZFgpqHhng5I9v0xKpjOnZk9MRTWkzPyxIMwl535ZVLte0J5VRIIaZFEyYFRXgZGVyGinnEIfXZKZdUdRpRELUBK086A/w4aG3shpEPXEzfo42hjdrDEfyx5bZTANyrGwj1hTLKPoVaPMN9wb3MdQ1D1B5Os3+5YdfASnQRZfZmaEJqNAHNlZveLHpA2DcPFNvltcwUy3Jj1gTI43IbbuXNsIXhMKgNaZrNgJKKpQpc+qF9D7CwfugtiD6y/g71UrrUgvVIcZ9UXVTu5OJg2agGiaIvRWrGxfhyzv/HyHR530p7fNTt/dJBCDO55Mx3uhxA/XGYxmz2uk/xIQMR8QU7Cc/tOdvzdHJ+WHhNBo2fe5oLk03AXIhpqOOgJb8nnM',
            HTTP_CONCENT_AUTH=self.header_concent_auth,
            content_type                   = 'application/x-www-form-urlencoded',
        )

        self.assertIsInstance(response, JsonResponse)
        self.assertEqual(response.status_code, 401)
        self.assertIn('message', response.json().keys())
        self.assertEqual("application/json", response["Content-Type"])

    def test_upload_should_return_401_if_specific_file_info_data(self):
        file = FileTransferToken.FileInfo(
            path     = get_storage_result_file_path(
                task_id=1,
                subtask_id=2
            ),
            size     = 1,
            checksum = 'sha1:356a192b7913b04c54574d18c28d46e6395428ab\n',
        )

        self.upload_token.files = [file]

        golem_upload_token = dump(self.upload_token, settings.CONCENT_PRIVATE_KEY, settings.CONCENT_PUBLIC_KEY)
        encoded_token = b64encode(golem_upload_token).decode()
        response = self.client.post(
            '{}{}'.format(
                reverse('gatekeeper:upload'),
                get_storage_result_file_path(
                    task_id=1,
                    subtask_id=2,
                ),
            ),
            HTTP_AUTHORIZATION             = 'Golem ' + encoded_token,
            HTTP_CONCENT_AUTH=self.header_concent_auth,
            content_type                   = 'application/x-www-form-urlencoded',
        )

        self.assertIsInstance(response, JsonResponse)
        self.assertEqual(response.status_code, 401)
        self.assertIn('message', response.json().keys())
        self.assertEqual("application/json", response["Content-Type"])

    @freeze_time("2018-12-30 11:00:00")
    def test_upload_should_return_401_if_file_categories_are_not_unique_across_file_info_list(self):
        file_1 = FileTransferToken.FileInfo(
            path='blender/benchmark/test_task/scene-Helicopter-27-cycles.blend',
            checksum='sha1:95a0f391c7ad86686ab1366bcd519ba5ab3cce89',
            size=1024,
            category=FileTransferToken.FileInfo.Category.results
        )
        file_2 = FileTransferToken.FileInfo(
            path='blender/benchmark/test_task/scene-Helicopter-28-cycles.blend',
            checksum='sha1:95a0f391c7ad86686ab1366bcd519ba5ab3cce89',
            size=1024,
            category=FileTransferToken.FileInfo.Category.results
        )

        self.upload_token.files = [file_1, file_2]

        golem_upload_token = dump(self.upload_token, settings.CONCENT_PRIVATE_KEY, settings.CONCENT_PUBLIC_KEY)
        encoded_token = b64encode(golem_upload_token).decode()
        response = self.client.post(
            '{}{}'.format(
                reverse('gatekeeper:upload'),
                'blender/benchmark/test_task/scene-Helicopter-27-cycles.blend'
            ),
            HTTP_AUTHORIZATION='Golem ' + encoded_token,
            HTTP_CONCENT_AUTH=self.header_concent_auth,
            content_type='application/x-www-form-urlencoded',
        )

        self.assertIsInstance(response, JsonResponse)
        self.assertEqual(response.status_code, 401)
        self.assertIn('message', response.json().keys())
        self.assertIn('error_code', response.json().keys())
        self.assertEqual("application/json", response["Content-Type"])
        self.assertEqual(response.json()["error_code"], ErrorCode.MESSAGE_FILES_CATEGORY_NOT_UNIQUE.value)


@override_settings(
    CONCENT_PRIVATE_KEY = b'l\xcdh\x19\xeb$>\xbcG\xa1\xc7v\xe8\xd7o\x0c\xbf\x0e\x0fM\x89lw\x1e\xd7K\xd6Hnv$\xa2',
    CONCENT_PUBLIC_KEY  = b'\xf3\x97\x19\xcdX\xda\x86tiP\x1c&\xd39M\x9e\xa4\xddb\x89\xb5,]O\xd5cR\x84\xb85\xed\xc9\xa17e,\xb2s\xeb\n1\xcaN.l\xba\xc3\xb7\xc2\xba\xff\xabN\xde\xb3\x0b\xa6l\xbf6o\x81\xe0;',
    STORAGE_CLUSTER_ADDRESS = 'http://devel.concent.golem.network/'
)
class GatekeeperViewDownloadTest(ConcentIntegrationTestCase):

    @freeze_time("2018-12-30 11:00:00")
    def setUp(self):
        self.message_timestamp  = get_current_utc_timestamp()
        self.public_key         = '85cZzVjahnRpUBwm0zlNnqTdYom1LF1P1WNShLg17cmhN2UssnPrCjHKTi5susO3wrr/q07eswumbL82b4HgOw=='
        self.download_token = FileTransferTokenFactory(
            token_expiration_deadline=self.message_timestamp + 3600,
            storage_cluster_address='http://devel.concent.golem.network/',
            authorized_client_public_key=settings.CONCENT_PUBLIC_KEY,
            operation=FileTransferToken.Operation.download,
        )
        self.download_token.files[0]['path']      = 'blender/benchmark/test_task/scene-Helicopter-27-cycles.blend'
        self.download_token.files[0]['checksum']  = 'sha1:95a0f391c7ad86686ab1366bcd519ba5ab3cce89'

        self.header_concent_auth = self._create_client_auth_message_as_header(
            settings.CONCENT_PRIVATE_KEY,
            settings.CONCENT_PUBLIC_KEY,
        )

    @freeze_time("2018-12-30 11:00:00")
    def test_download_should_accept_valid_message(self):
        golem_download_token = dump(self.download_token, settings.CONCENT_PRIVATE_KEY, settings.CONCENT_PUBLIC_KEY)
        encoded_token = b64encode(golem_download_token).decode()
        response = self.client.get(
            '{}{}'.format(
                reverse('gatekeeper:download'),
                'blender/benchmark/test_task/scene-Helicopter-27-cycles.blend'
            ),
            HTTP_AUTHORIZATION = 'Golem ' + encoded_token,
            HTTP_CONCENT_AUTH=self.header_concent_auth,
        )

        self.assertIsInstance(response, JsonResponse)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.has_header("Concent-File-Size"))
        self.assertFalse(response.has_header("Concent-File-Checksum"))
        self.assertEqual("application/json", response["Content-Type"])

    @freeze_time("2018-12-30 11:00:00")
    def test_download_should_return_401_if_wrong_authorization_header(self):
        golem_download_token = dump(self.download_token, settings.CONCENT_PRIVATE_KEY, settings.CONCENT_PUBLIC_KEY)
        encoded_token = b64encode(golem_download_token).decode()
        wrong_test_headers_with_expected_error_code = {
            'GolemGolem '+ encoded_token: ErrorCode.HEADER_AUTHORIZATION_UNRECOGNIZED_SCHEME.value,
            '':                             ErrorCode.HEADER_AUTHORIZATION_MISSING_TOKEN.value,
            'Golem encoded_token ':       ErrorCode.HEADER_AUTHORIZATION_NOT_BASE64_ENCODED_VALUE.value,
            'Golem a' + encoded_token:    ErrorCode.HEADER_AUTHORIZATION_TOKEN_INVALID_MESSAGE.value,
        }
        for authorization_header_value, error_code in wrong_test_headers_with_expected_error_code.items():
            response = self.client.get(
                '{}{}'.format(
                    reverse('gatekeeper:download'),
                    'blender/benchmark/test_task/scene-Helicopter-27-cycles.blend'
                ),
                HTTP_CONCENT_AUTH=self.header_concent_auth,
                HTTP_AUTHORIZATION=authorization_header_value,
            )
            self.assertIsInstance(response, JsonResponse)
            self.assertEqual(response.status_code, 401)
            self.assertIn('message', response.json().keys())
            self.assertIn('error_code', response.json().keys())
            self.assertEqual(response.json()["error_code"], error_code)

        response = self.client.get(
            '{}{}'.format(
                reverse('gatekeeper:download'),
                'blender/benchmark/test_task/scene-Helicopter-27-cycles.blend'
            ),
            HTTP_CONCENT_AUTH=self.header_concent_auth,
            HTTP_AUTHORIZATION_ABC='Golem ' + encoded_token,
        )
        self.assertIsInstance(response, JsonResponse)
        self.assertEqual(response.status_code, 401)
        self.assertIn('message', response.json().keys())
        self.assertIn('error_code', response.json().keys())
        self.assertEqual(response.json()["error_code"], ErrorCode.HEADER_AUTHORIZATION_MISSING.value)

    @freeze_time("2018-12-30 11:00:00")
    def test_download_should_return_401_if_wrong_token_cluster_address(self):
        upload_token = self.download_token
        upload_token.storage_cluster_address = 'www://storage.concent.golem.network/'
        golem_upload_token = dump(upload_token, settings.CONCENT_PRIVATE_KEY, settings.CONCENT_PUBLIC_KEY)
        encoded_token = b64encode(golem_upload_token).decode()
        response = self.client.get(
            '{}{}'.format(
                reverse('gatekeeper:download'),
                'blender/benchmark/test_task/scene-Helicopter-27-cycles.blend'
            ),
            HTTP_AUTHORIZATION = 'Golem ' + encoded_token,
            HTTP_CONCENT_AUTH=self.header_concent_auth,
        )

        self.assertIsInstance(response, JsonResponse)
        self.assertEqual(response.status_code, 401)
        self.assertIn('message', response.json().keys())
        self.assertIn('error_code', response.json().keys())
        self.assertEqual(response.json()["error_code"], ErrorCode.MESSAGE_STORAGE_CLUSTER_INVALID_URL.value)

    @freeze_time("2018-12-30 11:00:00")
    def test_download_should_return_401_if_file_paths_are_not_unique(self):
        file1 = FileTransferToken.FileInfo(
            path     = 'blender/benchmark/test_task/scene-Helicopter-27-cycles.blend',
            checksum = 'sha1:95a0f391c7ad86686ab1366bcd519ba5ab3cce89',
            size     = 1024,
        )

        file2 = FileTransferToken.FileInfo(
            path     = 'blender/benchmark/test_task/scene-Helicopter-27-cycles.blend',
            checksum = 'sha1:95a0f391c7ad86686ab1366bcd519ba5ab3cce89',
            size     = 1024,
        )

        self.download_token.files = [file1, file2]
        assert file1 == file2

        golem_download_token = dump(self.download_token, settings.CONCENT_PRIVATE_KEY, settings.CONCENT_PUBLIC_KEY)
        encoded_token = b64encode(golem_download_token).decode()
        response = self.client.get(
            '{}{}'.format(
                reverse('gatekeeper:download'),
                'blender/benchmark/test_task/scene-Helicopter-27-cycles.blend'
            ),
            HTTP_AUTHORIZATION             = 'Golem ' + encoded_token,
            HTTP_CONCENT_AUTH=self.header_concent_auth,
        )

        self.assertIsInstance(response, JsonResponse)
        self.assertEqual(response.status_code, 401)
        self.assertIn('message', response.json().keys())
        self.assertIn('error_code', response.json().keys())
        self.assertEqual("application/json", response["Content-Type"])
        self.assertEqual(response.json()["error_code"], ErrorCode.MESSAGE_FILES_PATHS_NOT_UNIQUE.value)

    @freeze_time("2018-12-30 11:00:00")
    def test_download_should_return_401_if_checksum_is_wrong(self):
        invalid_values_with_expected_error_code = {
            b'sha1:95a0f391c7ad86686ab1366bcd519ba5ab3cce89':   ErrorCode.MESSAGE_FILES_CHECKSUM_WRONG_TYPE,
            '':                                                 ErrorCode.MESSAGE_FILES_CHECKSUM_EMPTY,
            '95a0f391c7ad86686ab1366bcd519ba5ab3cce89':         ErrorCode.MESSAGE_FILES_CHECKSUM_WRONG_FORMAT,
            ':95a0f391c7ad86686ab1366bcd519ba5ab3cce89':        ErrorCode.MESSAGE_FILES_CHECKSUM_INVALID_ALGORITHM,
            'sha1:95a0f391c7ad86686ab1366bcd519ba5amONj':       ErrorCode.MESSAGE_FILES_CHECKSUM_INVALID_SHA1_HASH,
            'sha1:':                                            ErrorCode.MESSAGE_FILES_CHECKSUM_INVALID_SHA1_HASH,
        }

        for invalid_value, error_code in invalid_values_with_expected_error_code.items():
            file1 = FileTransferToken.FileInfo(
                path     = 'blender/benchmark/test_task/scene-Helicopter-27-cycles.blend',
                checksum = 'sha1:95a0f391c7ad86686ab1366bcd519ba5ab3cce89',
                size     = 1024,
            )

            file2 = FileTransferToken.FileInfo(
                path     = 'blenderrr/benchmark/test_task/scene-Helicopter-27-cycles.blend',
                checksum = invalid_value,
                size     = 1024,
            )

            self.download_token.files = [file1, file2]
            self.download_token.sig   = None

            golem_download_token = dump(self.download_token, settings.CONCENT_PRIVATE_KEY, settings.CONCENT_PUBLIC_KEY)
            encoded_token = b64encode(golem_download_token).decode()
            response = self.client.get(
                '{}{}'.format(
                    reverse('gatekeeper:download'),
                    'blender/benchmark/test_task/scene-Helicopter-27-cycles.blend'
                ),
                HTTP_AUTHORIZATION             = 'Golem ' + encoded_token,
                HTTP_CONCENT_AUTH=self.header_concent_auth,
            )

            self.assertIsInstance(response, JsonResponse)
            self.assertEqual(response.status_code, 401)
            self.assertIn('message', response.json().keys())
            self.assertIn('error_code', response.json().keys())
            self.assertEqual("application/json", response["Content-Type"])
            self.assertEqual(response.json()["error_code"], error_code.value)

    @freeze_time("2018-12-30 11:00:00")
    def test_download_should_return_401_if_size_of_file_is_wrong(self):
        invalid_values_with_expected_error_code = {
            None: ErrorCode.MESSAGE_FILES_SIZE_EMPTY,
            'number': ErrorCode.MESSAGE_FILES_SIZE_WRONG_TYPE,
            '-2': ErrorCode.MESSAGE_FILES_SIZE_NEGATIVE,
            '1.0': ErrorCode.MESSAGE_FILES_SIZE_WRONG_TYPE,
        }

        for invalid_value, error_code in invalid_values_with_expected_error_code.items():
            file1 = FileTransferToken.FileInfo(
                path     = 'blender/benchmark/test_task/scene-Helicopter-27-cycles.blend',
                checksum = 'sha1:95a0f391c7ad86686ab1366bcd519ba5ab3cce89',
                size     = 1024,
            )

            file2 = FileTransferToken.FileInfo(
                path     = 'blenderrr/benchmark/test_task/scene-Helicopter-27-cycles.blend',
                checksum = 'sha1:95a0f391c7ad86686ab1366bcd519ba5ab3cce89',
                size     = invalid_value,
            )

            self.download_token.files = [file1, file2]
            self.download_token.sig   = None

            golem_download_token = dump(self.download_token, settings.CONCENT_PRIVATE_KEY, settings.CONCENT_PUBLIC_KEY)
            encoded_token = b64encode(golem_download_token).decode()
            response = self.client.get(
                '{}{}'.format(
                    reverse('gatekeeper:download'),
                    'blender/benchmark/test_task/scene-Helicopter-27-cycles.blend'
                ),
                HTTP_AUTHORIZATION             = 'Golem ' + encoded_token,
                HTTP_CONCENT_AUTH=self.header_concent_auth,
            )

            self.assertIsInstance(response, JsonResponse)
            self.assertEqual(response.status_code, 401)
            self.assertIn('message', response.json().keys())
            self.assertEqual("application/json", response["Content-Type"])
            self.assertEqual(response.json()["error_code"], error_code.value)

    @freeze_time("2018-12-30 11:00:00")
    def test_download_should_return_400_if_newlines_in_message_checksum(self):
        invalid_values_with_expected_error_code = {
            's\nha1:95a0f391c7ad866\n86ab1366bcd519ba5ab3cce89': ErrorCode.MESSAGE_FILES_CHECKSUM_INVALID_ALGORITHM,
            '\nsha1:95a0f391c7ad86686ab1366bcd519ba5ab3cce89': ErrorCode.MESSAGE_FILES_CHECKSUM_INVALID_ALGORITHM,
            'sha1:95a0f391c7ad86686ab1366bcd519ba5ab3cce89\n': ErrorCode.MESSAGE_FILES_CHECKSUM_INVALID_SHA1_HASH,
        }

        for value, error_code in invalid_values_with_expected_error_code.items():
            file = FileTransferToken.FileInfo(
                path     = 'blender/benchmark/test_task/scene-Helicopter-27-cycles.blend',
                checksum = value,
                size     = 1024,
            )

            self.download_token.files = [file]
            self.download_token.sig   = None

            golem_download_token = dump(self.download_token, settings.CONCENT_PRIVATE_KEY, settings.CONCENT_PUBLIC_KEY)
            encoded_token = b64encode(golem_download_token).decode()
            response = self.client.get(
                '{}{}'.format(
                    reverse('gatekeeper:download'),
                    'blender/benchmark/test_task/scene-Helicopter-27-cycles.blend'
                ),
                HTTP_AUTHORIZATION             = 'Golem ' + encoded_token,
                HTTP_CONCENT_AUTH=self.header_concent_auth,
            )

            self.assertIsInstance(response, JsonResponse)
            self.assertEqual(response.status_code, 401)
            self.assertIn('message', response.json().keys())
            self.assertEqual("application/json", response["Content-Type"])
            self.assertEqual(response.json()["error_code"], error_code.value)

    @freeze_time("2018-12-30 11:00:00")
    def test_download_should_return_400_if_newlines_in_message_path(self):
        invalid_values_with_expected_error_code = {
            'blen\nder/benchmark/test_task/scene-Helicopter-2\n7-cycles.blend': ErrorCode.MESSAGE_FILES_PATH_NOT_LISTED_IN_FILES,
            '\nblender/benchmark/test_task/scene-Helicopter-27-cycles.blend': ErrorCode.MESSAGE_FILES_PATH_NOT_LISTED_IN_FILES,
            'blender/benchmark/test_task/scene-Helicopter-27-cycles.blend\n': ErrorCode.MESSAGE_FILES_PATH_NOT_LISTED_IN_FILES,
        }

        for value, error_code in invalid_values_with_expected_error_code.items():
            file = FileTransferToken.FileInfo(
                path     = value,
                checksum = 'sha1:95a0f391c7ad86686ab1366bcd519ba5ab3cce89',
                size     = 1024,
            )

            self.download_token.files = [file]
            self.download_token.sig   = None

            golem_download_token = dump(self.download_token, settings.CONCENT_PRIVATE_KEY, settings.CONCENT_PUBLIC_KEY)
            encoded_token = b64encode(golem_download_token).decode()
            response = self.client.get(
                '{}{}'.format(
                    reverse('gatekeeper:download'),
                    'blender/benchmark/test_task/scene-Helicopter-27-cycles.blend'
                ),
                HTTP_AUTHORIZATION             = 'Golem ' + encoded_token,
                HTTP_CONCENT_AUTH=self.header_concent_auth,
            )

            self.assertIsInstance(response, JsonResponse)
            self.assertEqual(response.status_code, 401)
            self.assertIn('message', response.json().keys())
            self.assertIn('error_code', response.json().keys())
            self.assertEqual("application/json", response["Content-Type"])
            self.assertEqual(response.json()["error_code"], error_code.value)

    @freeze_time("2018-12-30 11:00:00")
    def test_download_should_return_401_concent_auth_header_is_missing(self):
        golem_download_token = dump(self.download_token, settings.CONCENT_PRIVATE_KEY, settings.CONCENT_PUBLIC_KEY)
        encoded_token = b64encode(golem_download_token).decode()
        response = self.client.get(
            '{}{}'.format(
                reverse('gatekeeper:download'),
                'blender/benchmark/test_task/scene-Helicopter-27-cycles.blend'
            ),
            HTTP_AUTHORIZATION = 'Golem ' + encoded_token,
        )

        self.assertIsInstance(response, JsonResponse)
        self.assertEqual(response.status_code, 401)
        self.assertIn('message', response.json().keys())

    @freeze_time("2018-12-30 11:00:00")
    def test_download_should_return_401_concent_auth_header_is_not_loadable(self):
        golem_download_token = dump(self.download_token, settings.CONCENT_PRIVATE_KEY, settings.CONCENT_PUBLIC_KEY)
        encoded_token = b64encode(golem_download_token).decode()
        response = self.client.get(
            '{}{}'.format(
                reverse('gatekeeper:download'),
                'blender/benchmark/test_task/scene-Helicopter-27-cycles.blend'
            ),
            HTTP_AUTHORIZATION = 'Golem ' + encoded_token,
            HTTP_CONCENT_AUTH='test',
        )

        self.assertIsInstance(response, JsonResponse)
        self.assertEqual(response.status_code, 401)
        self.assertIn('message', response.json().keys())

    @freeze_time("2018-12-30 11:00:00")
    def test_download_should_return_401_if_file_categories_are_not_unique_across_file_info_list(self):
        file_1 = FileTransferToken.FileInfo(
            path='blender/benchmark/test_task/scene-Helicopter-27-cycles.blend',
            checksum='sha1:95a0f391c7ad86686ab1366bcd519ba5ab3cce89',
            size=1024,
            category=FileTransferToken.FileInfo.Category.results
        )
        file_2 = FileTransferToken.FileInfo(
            path='blender/benchmark/test_task/scene-Helicopter-28-cycles.blend',
            checksum='sha1:95a0f391c7ad86686ab1366bcd519ba5ab3cce89',
            size=1024,
            category=FileTransferToken.FileInfo.Category.results
        )

        self.download_token.files = [file_1, file_2]

        golem_download_token = dump(self.download_token, settings.CONCENT_PRIVATE_KEY, settings.CONCENT_PUBLIC_KEY)
        encoded_token = b64encode(golem_download_token).decode()
        response = self.client.get(
            '{}{}'.format(
                reverse('gatekeeper:download'),
                'blender/benchmark/test_task/scene-Helicopter-27-cycles.blend'
            ),
            HTTP_AUTHORIZATION='Golem ' + encoded_token,
            HTTP_CONCENT_AUTH=self.header_concent_auth,
            content_type='application/x-www-form-urlencoded',
        )

        self.assertIsInstance(response, JsonResponse)
        self.assertEqual(response.status_code, 401)
        self.assertIn('message', response.json().keys())
        self.assertIn('error_code', response.json().keys())
        self.assertEqual("application/json", response["Content-Type"])
        self.assertEqual(response.json()["error_code"], ErrorCode.MESSAGE_FILES_CATEGORY_NOT_UNIQUE.value)
