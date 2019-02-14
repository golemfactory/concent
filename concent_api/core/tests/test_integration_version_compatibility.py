from django.test import override_settings
from golem_messages import message

from common.testing_helpers import generate_ecc_key_pair
from core.models import PendingResponse
from core.tests.utils import ConcentIntegrationTestCase


(CONCENT_PRIVATE_KEY, CONCENT_PUBLIC_KEY) = generate_ecc_key_pair()


def _get_pending_messages_query(subtask_id, client_public_key, golem_message_version):
    return PendingResponse.objects.filter(
        subtask__subtask_id=subtask_id,
        client__public_key=client_public_key,
        delivered=False,
        queue=PendingResponse.Queue.Receive.name,  # pylint: disable=no-member
        subtask__protocol_version=golem_message_version
    )


@override_settings(
    CONCENT_PRIVATE_KEY=CONCENT_PRIVATE_KEY,
    CONCENT_PUBLIC_KEY=CONCENT_PUBLIC_KEY,
)
class VersionCompatibilityIntegrationTest(ConcentIntegrationTestCase):

    def setUp(self):
        super().setUp()
        self.GM_2_15_0 = '2.15.0'
        self.GM_2_15 = '2.15'
        self.GM_2_16_0 = '2.16.0'
        self.GM_2_16 = '2.16'

    def test_that_client_with_undelivered_messages_from_older_golem_messages_version_will_receive_messages_from_version_which_is_supported(self):

        # Expected test behaviour:
        # Provider  -> Concent:     ForceReportComputedTask (GM 2.15.0)
        # Concent   -> Requestor:   ForceReportComputedTask (GM 2.15.0)
        # Requestor -> Concent:     AckReportComputedTask   (GM 2.15.0)
        # AckReportComputedTask as a PendingReponse for Provider
        # GolemMessage update 2.15.0 -> 2.16.0 in Concent and GolemClient
        # Provider  -> Concent:     ForceReportComputedTask (GM 2.16.0; new subtask)
        # Concent   -> Requestor:   ForceReportComputedTask (GM 2.16.0)
        # Requestor -> Concent:     AckReportComputedTask   (GM 2.16.0)
        # Concent   -> Provider:    AckReportComputedTask   (GM 2.16.0)

        report_computed_task = self._get_deserialized_report_computed_task()

        serialized_force_report_computed_task = self._get_serialized_force_report_computed_task(
            force_report_computed_task=self._get_deserialized_force_report_computed_task(
                report_computed_task=report_computed_task
            ),
            provider_private_key=self.PROVIDER_PRIVATE_KEY
        )
        with override_settings(
            GOLEM_MESSAGES_VERSION=self.GM_2_15_0,
            MAJOR_MINOR_GOLEM_MESSAGES_VERSION=self.GM_2_15,
        ):
            response_1 = self.send_request(
                url='core:send',
                data=serialized_force_report_computed_task,
                golem_messages_version=self.GM_2_15_0
            )

        self.assertEqual(response_1.status_code, 202)
        self.assertEqual(len(response_1.content), 0)
        self._assert_stored_message_counter_increased(increased_by=3)

        with override_settings(
            GOLEM_MESSAGES_VERSION=self.GM_2_15_0,
            MAJOR_MINOR_GOLEM_MESSAGES_VERSION=self.GM_2_15,
        ):
            response_2 = self.send_request(
                url='core:receive',
                data=self._create_requestor_auth_message(),
                golem_messages_version=self.GM_2_15_0
            )

        self._test_response(
            response_2,
            status=200,
            key=self.REQUESTOR_PRIVATE_KEY,
            message_type=message.concents.ForceReportComputedTask,
        )
        self._assert_stored_message_counter_not_increased()

        serialized_ack_report_computed_task = self._get_serialized_ack_report_computed_task(
            ack_report_computed_task=self._get_deserialized_ack_report_computed_task(
                report_computed_task=report_computed_task,
            ),
            requestor_private_key=self.REQUESTOR_PRIVATE_KEY
        )
        with override_settings(
            GOLEM_MESSAGES_VERSION=self.GM_2_15_0,
            MAJOR_MINOR_GOLEM_MESSAGES_VERSION=self.GM_2_15,
        ):
            response_3 = self.send_request(
                url='core:send',
                data=serialized_ack_report_computed_task,
                golem_messages_version=self.GM_2_15_0
            )

        self.assertEqual(len(response_3.content), 0)
        self._assert_stored_message_counter_increased(increased_by=1)
        pending_response = _get_pending_messages_query(
            subtask_id=report_computed_task.task_to_compute.subtask_id,
            client_public_key=self._get_encoded_provider_public_key(),
            golem_message_version=self.GM_2_15,
        )

        self.assertEqual(len(pending_response), 1)
        self.assertEqual(pending_response[0].response_type_enum, PendingResponse.ResponseType.ForceReportComputedTaskResponse)

        new_report_computed_task = self._get_deserialized_report_computed_task()

        new_serialized_force_report_computed_task = self._get_serialized_force_report_computed_task(
            force_report_computed_task=self._get_deserialized_force_report_computed_task(
                report_computed_task=new_report_computed_task
            ),
            provider_private_key=self.PROVIDER_PRIVATE_KEY
        )

        # Concent and Golem already updated to GolemMessages version 2.16.0
        with override_settings(
            GOLEM_MESSAGES_VERSION=self.GM_2_16_0,
            MAJOR_MINOR_GOLEM_MESSAGES_VERSION=self.GM_2_16,
        ):
            response_4 = self.send_request(
                url='core:send',
                data=new_serialized_force_report_computed_task,
                golem_messages_version=self.GM_2_16_0
            )

        self.assertEqual(response_4.status_code, 202)
        self.assertEqual(len(response_4.content), 0)
        self._assert_stored_message_counter_increased(increased_by=3)

        with override_settings(
            GOLEM_MESSAGES_VERSION=self.GM_2_16_0,
            MAJOR_MINOR_GOLEM_MESSAGES_VERSION=self.GM_2_16,
        ):
            response_5 = self.send_request(
                url='core:receive',
                data=self._create_requestor_auth_message(),
                golem_messages_version=self.GM_2_16_0
            )

        self._test_response(
            response_5,
            status=200,
            key=self.REQUESTOR_PRIVATE_KEY,
            message_type=message.concents.ForceReportComputedTask,
        )
        self._assert_stored_message_counter_not_increased()

        new_serialized_ack_report_computed_task = self._get_serialized_ack_report_computed_task(
            ack_report_computed_task=self._get_deserialized_ack_report_computed_task(
                report_computed_task=new_report_computed_task,
            ),
            requestor_private_key=self.REQUESTOR_PRIVATE_KEY
        )
        with override_settings(
                GOLEM_MESSAGES_VERSION=self.GM_2_16_0,
                MAJOR_MINOR_GOLEM_MESSAGES_VERSION=self.GM_2_16,
        ):
            response_6 = self.send_request(
                url='core:send',
                data=new_serialized_ack_report_computed_task,
                golem_messages_version=self.GM_2_16_0
            )

        self.assertEqual(len(response_6.content), 0)
        self._assert_stored_message_counter_increased(increased_by=1)

        pending_response = _get_pending_messages_query(
            subtask_id=new_report_computed_task.task_to_compute.subtask_id,
            client_public_key=self._get_encoded_provider_public_key(),
            golem_message_version=self.GM_2_16,
        )
        self.assertEqual(len(pending_response), 1)
        self.assertEqual(pending_response[0].response_type_enum, PendingResponse.ResponseType.ForceReportComputedTaskResponse)

        with override_settings(
                GOLEM_MESSAGES_VERSION=self.GM_2_16_0,
                MAJOR_MINOR_GOLEM_MESSAGES_VERSION=self.GM_2_16,
        ):
            response_7 = self.send_request(
                url='core:receive',
                data=self._create_provider_auth_message(),
                golem_messages_version=self.GM_2_16_0
            )

        self._test_response(
            response_7,
            status=200,
            key=self.PROVIDER_PRIVATE_KEY,
            message_type=message.concents.ForceReportComputedTaskResponse,
        )
        self._assert_stored_message_counter_not_increased()

        # Check to be sure, that message with Golem Messages version 2.15.0 is still undelivered
        pending_response = _get_pending_messages_query(
            subtask_id=report_computed_task.task_to_compute.subtask_id,
            client_public_key=self._get_encoded_provider_public_key(),
            golem_message_version=self.GM_2_15,
        )
        self.assertEqual(len(pending_response), 1)
        self.assertEqual(pending_response[0].response_type_enum, PendingResponse.ResponseType.ForceReportComputedTaskResponse)

        # Check to be sure, that message with Golem Messages version 2.16.0 is already delivered and queue is empty
        pending_response = _get_pending_messages_query(
            subtask_id=new_report_computed_task.task_to_compute.subtask_id,
            client_public_key=self._get_encoded_provider_public_key(),
            golem_message_version=self.GM_2_16,
        )
        self.assertEqual(len(pending_response), 0)
