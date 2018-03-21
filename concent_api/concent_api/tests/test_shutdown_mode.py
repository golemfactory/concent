from base64                     import b64encode

from django.conf                import settings
from django.core                import mail
from django.http.response       import JsonResponse
from django.test                import override_settings
from django.urls                import reverse

from constance                  import config
from constance.test             import override_config
from freezegun                  import freeze_time
from golem_messages             import message
from golem_messages.shortcuts   import dump

from core.message_handlers      import store_subtask
from core.models                import PendingResponse
from core.models                import Subtask
from core.tests.utils           import ConcentIntegrationTestCase
from utils.helpers              import get_current_utc_timestamp
from utils.testing_helpers      import generate_ecc_key_pair


(CONCENT_PRIVATE_KEY, CONCENT_PUBLIC_KEY) = generate_ecc_key_pair()


@override_config(
    SHUTDOWN_MODE = True
)
@override_settings(
    CONCENT_PRIVATE_KEY         = CONCENT_PRIVATE_KEY,
    CONCENT_PUBLIC_KEY          = CONCENT_PUBLIC_KEY,
    PAYMENT_DUE_TIME            = 10,  # seconds
    PAYMENT_GRACE_PERIOD        = 10,  # seconds
    CONCENT_MESSAGING_TIME      = 10,  # seconds
    FORCE_ACCEPTANCE_TIME       = 10,  # seconds
    SUBTASK_VERIFICATION_TIME   = 10,  # seconds
    ADMINS                      = ['admin@localhost']
)
class ShutdownModeTest(ConcentIntegrationTestCase):

    def test_in_shutdown_mode_concent_should_not_accept_messages_that_would_cause_transition_to_active_state(self):
        """
        Tests if in shutdown mode
        Concent will not accept any new messages which create or update subtasks in active state.
        """

        compute_task_def = self._get_deserialized_compute_task_def(
            task_id     = '1',
            subtask_id  = '8',
            deadline    = "2017-12-01 11:00:00"
        )

        task_to_compute = self._get_deserialized_task_to_compute(
            timestamp           = "2017-12-01 10:00:00",
            compute_task_def    = compute_task_def,
        )

        report_computed_task = self._get_deserialized_report_computed_task(
            timestamp = "2017-12-01 10:59:00",
            task_to_compute = task_to_compute,
        )

        serialized_force_report_computed_task = self._get_serialized_force_report_computed_task(
            timestamp = "2017-12-01 10:59:00",
            force_report_computed_task = self._get_deserialized_force_report_computed_task(
                timestamp               = "2017-12-01 10:59:00",
                report_computed_task    = report_computed_task
            ),
            provider_private_key = self.PROVIDER_PRIVATE_KEY
        )

        with freeze_time("2017-12-01 10:59:00"):
            response = self.client.post(
                reverse('core:send'),
                data                                = serialized_force_report_computed_task,
                content_type                        = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY      = self._get_encoded_provider_public_key(),
                HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY = self._get_encoded_requestor_public_key(),
            )

        self.assertIsInstance(response, JsonResponse)
        self.assertEqual(response.status_code, 503)
        self._assert_stored_message_counter_not_increased()

    def test_in_shutdown_mode_concent_should_accept_messages_that_would_cause_transition_to_passive_state(self):
        """
        Tests if in shutdown mode
        Concent will accept new messages which update subtasks in passive state.
        It also checks if email to admins is sent when all subtasks are turned into passive states.
        """

        compute_task_def = self._get_deserialized_compute_task_def(
            task_id     = '1',
            subtask_id  = '8',
            deadline    = "2017-12-01 11:00:00"
        )
        task_to_compute = self._get_deserialized_task_to_compute(
            timestamp           = "2017-12-01 10:00:00",
            compute_task_def    = compute_task_def,
        )
        report_computed_task = self._get_deserialized_report_computed_task(
            timestamp       = "2017-12-01 10:59:00",
            task_to_compute = task_to_compute,
        )

        with freeze_time("2017-12-01 11:00:00"):
            config.SHUTDOWN_MODE = False
            store_subtask(
                task_id                 = '1',
                subtask_id              = '8',
                provider_public_key     = self.PROVIDER_PUBLIC_KEY,
                requestor_public_key    = self.REQUESTOR_PUBLIC_KEY,
                state                   = Subtask.SubtaskState.FORCING_REPORT,
                next_deadline           = get_current_utc_timestamp() + settings.CONCENT_MESSAGING_TIME,
                task_to_compute         = task_to_compute,
                report_computed_task    = report_computed_task,
            )
            config.SHUTDOWN_MODE = True

        self.stored_message_counter = 2

        serialized_ack_report_computed_task = self._get_serialized_ack_report_computed_task(
            timestamp                = "2017-12-01 11:00:05",
            ack_report_computed_task = self._get_deserialized_ack_report_computed_task(
                timestamp       = "2017-12-01 11:00:05",
                subtask_id      = '8',
                task_to_compute = task_to_compute
            ),
            requestor_private_key    = self.REQUESTOR_PRIVATE_KEY
        )

        with freeze_time("2017-12-01 11:00:05"):
            response = self.client.post(
                reverse('core:send'),
                data                           = serialized_ack_report_computed_task,
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = self._get_encoded_requestor_public_key(),
            )

        self.assertEqual(response.status_code,  202)
        self.assertEqual(len(response.content), 0)
        self._assert_stored_message_counter_increased(increased_by = 1)
        self._test_subtask_state(
            task_id                  = '1',
            subtask_id               = '8',
            subtask_state            = Subtask.SubtaskState.REPORTED,
            provider_key             = self._get_encoded_provider_public_key(),
            requestor_key            = self._get_encoded_requestor_public_key(),
            expected_nested_messages = {'task_to_compute', 'report_computed_task', 'ack_report_computed_task'},
        )
        self._test_last_stored_messages(
            expected_messages= [
                message.concents.AckReportComputedTask,
            ],
            task_id         = '1',
            subtask_id      = '8',
            timestamp       = "2017-12-01 11:00:05"
        )
        self._test_undelivered_pending_responses(
            subtask_id                         = '8',
            client_public_key                  = self._get_encoded_provider_public_key(),
            expected_pending_responses_receive = [
                PendingResponse.ResponseType.ForceReportComputedTaskResponse,
            ]
        )
        self.assertEqual(len(mail.outbox), len(settings.ADMINS))

    def test_in_shutdown_mode_concent_should_not_accept_payment_requests(self):
        """
        Tests if in shutdown mode Concent will not accept new payment requests.
        """

        subtask_results_accepted_list = [
            self._get_deserialized_subtask_results_accepted(
                timestamp       = "2018-02-05 10:00:15",
                payment_ts      = "2018-02-05 12:00:16",
                task_to_compute = self._get_deserialized_task_to_compute(
                    timestamp                       = "2018-02-05 10:00:00",
                    deadline                        = "2018-02-05 10:00:10",
                    task_id                         = '2',
                    requestor_public_key            = self._get_encoded_requestor_public_key(),
                    requestor_ethereum_public_key   = self._get_encoded_requestor_ethereum_public_key(),
                )
            )
        ]
        serialized_force_payment = self._get_serialized_force_payment(
            timestamp                     = "2018-02-05 10:00:15",
            subtask_results_accepted_list = subtask_results_accepted_list
        )

        with freeze_time("2018-02-05 10:00:25"):
            response = self.client.post(
                reverse('core:send'),
                data                                = serialized_force_payment,
                content_type                        = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY      = self._get_encoded_provider_public_key(),
                HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY = self._get_encoded_requestor_public_key(),
            )

        self.assertIsInstance(response, JsonResponse)
        self.assertEqual(response.status_code, 503)

    def test_in_shutdown_mode_gatekeeper_should_not_accept_download_tokens_from_clients(self):
        """
        Tests if in shutdown mode Gatekeeper will not accept new download tokens from clients.
        """

        download_token                               = message.FileTransferToken()
        download_token.token_expiration_deadline     = get_current_utc_timestamp() + 3600
        download_token.storage_cluster_address       = 'http://devel.concent.golem.network/'
        download_token.authorized_client_public_key  = self.PROVIDER_PUBLIC_KEY

        download_token.files                 = [message.FileTransferToken.FileInfo()]
        download_token.files[0]['path']      = 'blender/benchmark/test_task/scene-Helicopter-27-cycles.blend'
        download_token.files[0]['checksum']  = 'sha1:95a0f391c7ad86686ab1366bcd519ba5ab3cce89'
        download_token.files[0]['size']      = 1024
        download_token.operation             = 'download'

        golem_download_token = dump(download_token, settings.CONCENT_PRIVATE_KEY, settings.CONCENT_PUBLIC_KEY)
        encoded_token        = b64encode(golem_download_token).decode()

        response = self.client.get(
            '{}{}'.format(
                reverse('gatekeeper:download'),
                'blender/benchmark/test_task/scene-Helicopter-27-cycles.blend'
            ),
            HTTP_AUTHORIZATION              = 'Golem ' + encoded_token,
            content_type                    = 'application/x-www-form-urlencoded',
            HTTP_CONCENT_CLIENT_PUBLIC_KEY  = self._get_encoded_provider_public_key()
        )

        self.assertIsInstance(response, JsonResponse)
        self.assertEqual(response.status_code, 401)

    def test_in_shutdown_mode_gatekeeper_should_not_accept_upload_tokens_from_clients(self):
        """
        Tests if in shutdown mode Gatekeeper will not accept new upload tokens from clients.
        """

        upload_token                               = message.FileTransferToken()
        upload_token.token_expiration_deadline     = get_current_utc_timestamp() + 3600
        upload_token.storage_cluster_address       = 'http://devel.concent.golem.network/'
        upload_token.authorized_client_public_key  = self.PROVIDER_PUBLIC_KEY

        upload_token.files                 = [message.FileTransferToken.FileInfo()]
        upload_token.files[0]['path']      = 'blender/benchmark/test_task/scene-Helicopter-27-cycles.blend'
        upload_token.files[0]['checksum']  = 'sha1:95a0f391c7ad86686ab1366bcd519ba5ab3cce89'
        upload_token.files[0]['size']      = 1024
        upload_token.operation             = 'upload'

        golem_upload_token = dump(upload_token, settings.CONCENT_PRIVATE_KEY, settings.CONCENT_PUBLIC_KEY)
        encoded_token      = b64encode(golem_upload_token).decode()

        response = self.client.post(
            '{}{}'.format(
                reverse('gatekeeper:upload'),
                'blender/benchmark/test_task/scene-Helicopter-27-cycles.blend'
            ),
            HTTP_AUTHORIZATION              = 'Golem ' + encoded_token,
            content_type                    = 'application/x-www-form-urlencoded',
            HTTP_CONCENT_CLIENT_PUBLIC_KEY  = self._get_encoded_provider_public_key()
        )

        self.assertIsInstance(response, JsonResponse)
        self.assertEqual(response.status_code, 401)

    def test_in_shutdown_mode_gatekeeper_should_accept_download_tokens_from_concent(self):
        """
        Tests if in shutdown mode Gatekeeper will accept new download tokens from Concent.
        """

        download_token                               = message.FileTransferToken()
        download_token.token_expiration_deadline     = get_current_utc_timestamp() + 3600
        download_token.storage_cluster_address       = 'http://devel.concent.golem.network/'
        download_token.authorized_client_public_key  = self.PROVIDER_PUBLIC_KEY

        download_token.files                 = [message.FileTransferToken.FileInfo()]
        download_token.files[0]['path']      = 'blender/benchmark/test_task/scene-Helicopter-27-cycles.blend'
        download_token.files[0]['checksum']  = 'sha1:95a0f391c7ad86686ab1366bcd519ba5ab3cce89'
        download_token.files[0]['size']      = 1024
        download_token.operation             = 'download'

        golem_download_token = dump(download_token, settings.CONCENT_PRIVATE_KEY, settings.CONCENT_PUBLIC_KEY)
        encoded_token        = b64encode(golem_download_token).decode()

        response = self.client.get(
            '{}{}'.format(
                reverse('gatekeeper:download'),
                'blender/benchmark/test_task/scene-Helicopter-27-cycles.blend'
            ),
            HTTP_AUTHORIZATION              = 'Golem ' + encoded_token,
            content_type                    = 'application/x-www-form-urlencoded',
            HTTP_CONCENT_CLIENT_PUBLIC_KEY  = self._get_encoded_key(settings.CONCENT_PUBLIC_KEY)
        )

        self.assertIsInstance(response, JsonResponse)
        self.assertEqual(response.status_code, 401)

    def test_in_shutdown_mode_gatekeeper_should_not_accept_upload_tokens_from_concent(self):
        """
        Tests if in shutdown mode Gatekeeper will accept new upload tokens from Concent.
        """

        upload_token                               = message.FileTransferToken()
        upload_token.token_expiration_deadline     = get_current_utc_timestamp() + 3600
        upload_token.storage_cluster_address       = 'http://devel.concent.golem.network/'
        upload_token.authorized_client_public_key  = self.PROVIDER_PUBLIC_KEY

        upload_token.files                 = [message.FileTransferToken.FileInfo()]
        upload_token.files[0]['path']      = 'blender/benchmark/test_task/scene-Helicopter-27-cycles.blend'
        upload_token.files[0]['checksum']  = 'sha1:95a0f391c7ad86686ab1366bcd519ba5ab3cce89'
        upload_token.files[0]['size']      = 1024
        upload_token.operation             = 'upload'

        golem_upload_token  = dump(upload_token, settings.CONCENT_PRIVATE_KEY, settings.CONCENT_PUBLIC_KEY)
        encoded_token       = b64encode(golem_upload_token).decode()

        response = self.client.post(
            '{}{}'.format(
                reverse('gatekeeper:upload'),
                'blender/benchmark/test_task/scene-Helicopter-27-cycles.blend'
            ),
            HTTP_AUTHORIZATION              = 'Golem ' + encoded_token,
            content_type                    = 'application/x-www-form-urlencoded',
            HTTP_CONCENT_CLIENT_PUBLIC_KEY  = self._get_encoded_key(settings.CONCENT_PUBLIC_KEY)
        )

        self.assertIsInstance(response, JsonResponse)
        self.assertEqual(response.status_code, 401)
