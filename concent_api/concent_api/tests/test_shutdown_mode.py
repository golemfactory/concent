from django.conf                import settings
from django.core                import mail
from django.http.response       import JsonResponse
from django.test                import override_settings
from django.urls                import reverse

from constance                  import config
from constance.test             import override_config
from freezegun                  import freeze_time
from golem_messages             import message

from core.message_handlers      import store_subtask
from core.models                import PendingResponse
from core.models                import Subtask
from core.tests.utils import ConcentIntegrationTestCase
from common.helpers              import get_current_utc_timestamp
from common.testing_helpers      import generate_ecc_key_pair


(CONCENT_PRIVATE_KEY, CONCENT_PUBLIC_KEY) = generate_ecc_key_pair()


@override_config(
    SOFT_SHUTDOWN_MODE = True
)
@override_settings(
    CONCENT_PRIVATE_KEY         = CONCENT_PRIVATE_KEY,
    CONCENT_PUBLIC_KEY          = CONCENT_PUBLIC_KEY,
    PAYMENT_DUE_TIME            = 10,  # seconds
    PAYMENT_GRACE_PERIOD        = 10,  # seconds
    CONCENT_MESSAGING_TIME      = 10,  # seconds
    FORCE_ACCEPTANCE_TIME       = 10,  # seconds
    ADMINS                      = ['admin@localhost']
)
class SoftShutdownModeTest(ConcentIntegrationTestCase):

    def test_in_soft_shutdown_mode_concent_should_not_accept_messages_that_would_cause_transition_to_active_state(self):
        """
        Tests if in soft shutdown mode
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
            )

        self.assertIsInstance(response, JsonResponse)
        self.assertEqual(response.status_code, 503)
        self._assert_stored_message_counter_not_increased()

    def test_in_soft_shutdown_mode_concent_should_accept_messages_that_would_cause_transition_to_passive_state(self):
        """
        Tests if in soft shutdown mode
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
            config.SOFT_SHUTDOWN_MODE = False
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
            config.SOFT_SHUTDOWN_MODE = True

        self.stored_message_counter = 2

        serialized_ack_report_computed_task = self._get_serialized_ack_report_computed_task(
            timestamp="2017-12-01 11:00:05",
            ack_report_computed_task=self._get_deserialized_ack_report_computed_task(
                timestamp="2017-12-01 11:00:05",
                subtask_id='8',
                report_computed_task=report_computed_task
            ),
            requestor_private_key=self.REQUESTOR_PRIVATE_KEY
        )

        with freeze_time("2017-12-01 11:00:05"):
            response = self.client.post(
                reverse('core:send'),
                data                           = serialized_ack_report_computed_task,
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = self._get_encoded_requestor_public_key(),
            )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(len(response.content), 0)
        self._assert_stored_message_counter_increased(increased_by=1)
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
                message.AckReportComputedTask,
            ],
            task_id         = '1',
            subtask_id      = '8',
        )
        self._test_undelivered_pending_responses(
            subtask_id                         = '8',
            client_public_key                  = self._get_encoded_provider_public_key(),
            expected_pending_responses_receive = [
                PendingResponse.ResponseType.ForceReportComputedTaskResponse,
            ]
        )
        self.assertEqual(len(mail.outbox), len(settings.ADMINS))

    def test_in_soft_shutdown_mode_concent_should_not_accept_payment_requests(self):
        """
        Tests if in soft shutdown mode Concent will not accept new payment requests.
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
                    requestor_ethereum_public_key   = self._get_requestor_ethereum_hex_public_key(),
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
            )

        self.assertIsInstance(response, JsonResponse)
        self.assertEqual(response.status_code, 503)
