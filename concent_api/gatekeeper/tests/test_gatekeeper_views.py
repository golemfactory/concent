import datetime
from base64         import b64encode

from freezegun      import freeze_time
from django.conf    import settings
from django.http    import JsonResponse
from django.test    import override_settings
from django.test    import TestCase
from django.urls    import reverse

from golem_messages.shortcuts       import dump
from golem_messages.message         import FileTransferToken


@override_settings(
    CONCENT_PRIVATE_KEY = b'l\xcdh\x19\xeb$>\xbcG\xa1\xc7v\xe8\xd7o\x0c\xbf\x0e\x0fM\x89lw\x1e\xd7K\xd6Hnv$\xa2',
    CONCENT_PUBLIC_KEY  = b'\xf3\x97\x19\xcdX\xda\x86tiP\x1c&\xd39M\x9e\xa4\xddb\x89\xb5,]O\xd5cR\x84\xb85\xed\xc9\xa17e,\xb2s\xeb\n1\xcaN.l\xba\xc3\xb7\xc2\xba\xff\xabN\xde\xb3\x0b\xa6l\xbf6o\x81\xe0;',
    STORAGE_CLUSTER_ADDRESS = 'http://devel.concent.golem.network/'
)
class GatekeeperViewUploadTest(TestCase):

    @freeze_time("2018-12-30 11:00:00")
    def setUp(self):
        self.message_timestamp  = int(datetime.datetime.now().timestamp())
        self.public_key         = '85cZzVjahnRpUBwm0zlNnqTdYom1LF1P1WNShLg17cmhN2UssnPrCjHKTi5susO3wrr/q07eswumbL82b4HgOw=='
        self.upload_token                                 = FileTransferToken()
        self.upload_token.token_expiration_deadline       = self.message_timestamp + 3600
        self.upload_token.storage_cluster_address         = 'http://devel.concent.golem.network/'
        self.upload_token.authorized_client_public_key    = b'\xf3\x97\x19\xcdX\xda\x86tiP\x1c&\xd39M\x9e\xa4\xddb\x89\xb5,]O\xd5cR\x84\xb85\xed\xc9\xa17e,\xb2s\xeb\n1\xcaN.l\xba\xc3\xb7\xc2\xba\xff\xabN\xde\xb3\x0b\xa6l\xbf6o\x81\xe0;'

        self.upload_token.files                 = [FileTransferToken.FileInfo()]
        self.upload_token.files[0]['path']      = 'blender/benchmark/test_task/scene-Helicopter-27-cycles.blend'
        self.upload_token.files[0]['checksum']  = 'sha1:098f6bcd4621d373cade4e832627b4f6'
        self.upload_token.files[0]['size']      = 1024
        self.upload_token.operation             = 'upload'

    @freeze_time("2018-12-30 11:00:00")
    def test_upload_should_accept_valid_message(self):
        golem_upload_token = dump(self.upload_token, settings.CONCENT_PRIVATE_KEY, settings.CONCENT_PUBLIC_KEY)
        encrypted_token = b64encode(golem_upload_token).decode()
        response = self.client.post(
            '{}{}'.format(
                reverse('gatekeeper:upload'),
                'blender/benchmark/test_task/scene-Helicopter-27-cycles.blend'
            ),
            HTTP_AUTHORIZATION = 'Golem ' + encrypted_token,
            content_type = 'application/x-www-form-urlencoded',
            HTTP_CONCENT_CLIENT_PUBLIC_KEY = self.public_key
        )

        self.assertIsInstance(response, JsonResponse)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.has_header("Concent-File-Size"))
        self.assertTrue(response.has_header("Concent-File-Checksum"))
        self.assertEqual("application/json", response["Content-Type"])

    @freeze_time("2018-12-30 11:00:00")
    def test_upload_should_return_401_if_wrong_request_content_type(self):
        golem_upload_token = dump(self.upload_token, settings.CONCENT_PRIVATE_KEY, settings.CONCENT_PUBLIC_KEY)
        encrypted_token = b64encode(golem_upload_token).decode()
        response = self.client.post(
            '{}{}'.format(
                reverse('gatekeeper:upload'),
                'blender/benchmark/test_task/scene-Helicopter-27-cycles.blend'
            ),
            HTTP_AUTHORIZATION = 'Golem ' + encrypted_token,
            content_type = '',
            HTTP_CONCENT_CLIENT_PUBLIC_KEY = self.public_key
        )

        self.assertIsInstance(response, JsonResponse)
        self.assertEqual(response.status_code, 401)
        self.assertIn('message', response.json().keys())

    @freeze_time("2018-12-30 12:00:01")
    def test_upload_should_return_401_if_message_token_deadline_pass(self):
        golem_upload_token = dump(self.upload_token, settings.CONCENT_PRIVATE_KEY, settings.CONCENT_PUBLIC_KEY)
        encrypted_token = b64encode(golem_upload_token).decode()
        response = self.client.post(
            '{}{}'.format(
                reverse('gatekeeper:upload'),
                'blender/benchmark/test_task/scene-Helicopter-27-cycles.blend'
            ),
            HTTP_AUTHORIZATION = 'Golem ' + encrypted_token,
            content_type = 'application/x-www-form-urlencoded',
            HTTP_CONCENT_CLIENT_PUBLIC_KEY = self.public_key
        )

        self.assertIsInstance(response, JsonResponse)
        self.assertEqual(response.status_code, 401)
        self.assertIn('message', response.json().keys())


@override_settings(
    CONCENT_PRIVATE_KEY = b'l\xcdh\x19\xeb$>\xbcG\xa1\xc7v\xe8\xd7o\x0c\xbf\x0e\x0fM\x89lw\x1e\xd7K\xd6Hnv$\xa2',
    CONCENT_PUBLIC_KEY  = b'\xf3\x97\x19\xcdX\xda\x86tiP\x1c&\xd39M\x9e\xa4\xddb\x89\xb5,]O\xd5cR\x84\xb85\xed\xc9\xa17e,\xb2s\xeb\n1\xcaN.l\xba\xc3\xb7\xc2\xba\xff\xabN\xde\xb3\x0b\xa6l\xbf6o\x81\xe0;',
    STORAGE_CLUSTER_ADDRESS = 'http://devel.concent.golem.network/'
)
class GatekeeperViewDownloadTest(TestCase):

    @freeze_time("2018-12-30 11:00:00")
    def setUp(self):
        self.message_timestamp  = int(datetime.datetime.now().timestamp())
        self.public_key         = '85cZzVjahnRpUBwm0zlNnqTdYom1LF1P1WNShLg17cmhN2UssnPrCjHKTi5susO3wrr/q07eswumbL82b4HgOw=='
        self.upload_token                                 = FileTransferToken()
        self.upload_token.token_expiration_deadline       = self.message_timestamp + 3600
        self.upload_token.storage_cluster_address         = 'http://devel.concent.golem.network/'
        self.upload_token.authorized_client_public_key    = b'\xf3\x97\x19\xcdX\xda\x86tiP\x1c&\xd39M\x9e\xa4\xddb\x89\xb5,]O\xd5cR\x84\xb85\xed\xc9\xa17e,\xb2s\xeb\n1\xcaN.l\xba\xc3\xb7\xc2\xba\xff\xabN\xde\xb3\x0b\xa6l\xbf6o\x81\xe0;'

        self.upload_token.files                 = [FileTransferToken.FileInfo()]
        self.upload_token.files[0]['path']      = 'blender/benchmark/test_task/scene-Helicopter-27-cycles.blend'
        self.upload_token.files[0]['checksum']  = '098f6bcd4621d373cade4e832627b4f6'
        self.upload_token.files[0]['size']      = 1024
        self.upload_token.operation             = 'download'

    @freeze_time("2018-12-30 11:00:00")
    def test_download_should_accept_valid_message(self):
        golem_upload_token = dump(self.upload_token, settings.CONCENT_PRIVATE_KEY, settings.CONCENT_PUBLIC_KEY)
        encrypted_token = b64encode(golem_upload_token).decode()
        response = self.client.get(
            '{}{}'.format(
                reverse('gatekeeper:download'),
                'blender/benchmark/test_task/scene-Helicopter-27-cycles.blend'
            ),
            HTTP_AUTHORIZATION = 'Golem ' + encrypted_token,
            HTTP_CONCENT_CLIENT_PUBLIC_KEY = self.public_key
        )

        self.assertIsInstance(response, JsonResponse)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.has_header("Concent-File-Size"))
        self.assertFalse(response.has_header("Concent-File-Checksum"))
        self.assertEqual("application/json", response["Content-Type"])

    @freeze_time("2018-12-30 11:00:00")
    def test_download_should_return_401_if_wrong_authorization_header(self):
        golem_upload_token = dump(self.upload_token, settings.CONCENT_PRIVATE_KEY, settings.CONCENT_PUBLIC_KEY)
        encrypted_token = b64encode(golem_upload_token).decode()
        wrong_test_headers = [
            {'HTTP_AUTHORIZATION':      'GolemGolem '+ encrypted_token},
            {'HTTP_AUTHORIZATION_ABC':  'GolemGolem '+ encrypted_token},
            {'HTTP_AUTHORIZATION':      ''},
            {'HTTP_AUTHORIZATION':      'Golem encrypted_token '},
            {'HTTP_AUTHORIZATION':      'Golem a' + encrypted_token}
        ]
        for headers in wrong_test_headers:
            response = self.client.get(
                '{}{}'.format(
                    reverse('gatekeeper:download'),
                    'blender/benchmark/test_task/scene-Helicopter-27-cycles.blend'
                ),
                **headers,
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = self.public_key
            )
            self.assertIsInstance(response, JsonResponse)
            self.assertEqual(response.status_code, 401)
            self.assertIn('message', response.json().keys())

    @freeze_time("2018-12-30 11:00:00")
    def test_download_should_return_401_if_wrong_token_cluster_address(self):
        upload_token = self.upload_token
        upload_token.storage_cluster_address = 'www://storage.concent.golem.network/'
        golem_upload_token = dump(upload_token, settings.CONCENT_PRIVATE_KEY, settings.CONCENT_PUBLIC_KEY)
        encrypted_token = b64encode(golem_upload_token).decode()
        response = self.client.get(
            '{}{}'.format(
                reverse('gatekeeper:download'),
                'blender/benchmark/test_task/scene-Helicopter-27-cycles.blend'
            ),
            HTTP_AUTHORIZATION = 'Golem ' + encrypted_token,
            HTTP_CONCENT_CLIENT_PUBLIC_KEY = self.public_key
        )

        self.assertIsInstance(response, JsonResponse)
        self.assertEqual(response.status_code, 401)
        self.assertIn('message', response.json().keys())
