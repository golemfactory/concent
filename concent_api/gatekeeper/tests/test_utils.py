from base64                         import b64encode
import json

from django.http                    import JsonResponse
from django.test                    import TestCase
from golem_messages.message         import FileTransferToken

from gatekeeper.utils               import gatekeeper_access_denied_response
from utils.constants                import ErrorCode
from utils.testing_helpers          import generate_ecc_key_pair


class GatekeeperAccessDeniedResponseTest(TestCase):

    def setUp(self):
        self.message     = "Missing 'Authorization' header."
        self.path        = 'blender/benchmark/test_task/scene-Helicopter-27-cycles.blend'
        self.client_key  = b64encode(generate_ecc_key_pair()[1]).decode("ascii")

    def test_gatekeeper_access_denied_response_should_return_appropriate_body_and_headers(self):
        response = gatekeeper_access_denied_response(
            self.message,
            FileTransferToken.Operation.upload,
            ErrorCode.HEADER_AUTHORIZATION_MISSING,
            self.path,
            None,
            self.client_key
        )
        response_body = json.loads(response.content.decode())

        self.assertIsInstance(response, JsonResponse)
        self.assertEqual(response.status_code, 401)
        self.assertTrue(response.has_header("WWW-Authenticate"))
        self.assertEqual("application/json", response["Content-Type"])
        self.assertEqual(response_body["subtask_id"], None)
        self.assertEqual(response_body["message"], self.message)
        self.assertEqual(response_body["path_to_file"], self.path)
        self.assertEqual(response_body["client_key"], self.client_key)
        self.assertEqual(response_body["error_code"], ErrorCode.HEADER_AUTHORIZATION_MISSING.value)
