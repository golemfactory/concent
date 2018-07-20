from datetime import timedelta

import mock
from django.test import override_settings
from django.urls import reverse
from freezegun import freeze_time

from golem_messages import load
from golem_messages import message

from conductor.models import BlenderSubtaskDefinition
from core.message_handlers import store_or_update_subtask
from core.models import PendingResponse
from core.models import Subtask
from core.tests.utils import add_time_offset_to_date
from core.tests.utils import ConcentIntegrationTestCase
from core.tests.utils import parse_iso_date_to_timestamp
from core.transfer_operations import create_file_transfer_token_for_golem_client
from common.constants import ErrorCode
from common.helpers import get_current_utc_timestamp
from common.helpers import get_storage_result_file_path
from common.helpers import get_storage_source_file_path
from common.helpers import parse_timestamp_to_utc_datetime
from common.testing_helpers import generate_ecc_key_pair


(CONCENT_PRIVATE_KEY, CONCENT_PUBLIC_KEY) = generate_ecc_key_pair()


@override_settings(
    CONCENT_PRIVATE_KEY=CONCENT_PRIVATE_KEY,
    CONCENT_PUBLIC_KEY=CONCENT_PUBLIC_KEY,
    MINIMUM_UPLOAD_RATE=1,  # bits per second
    DOWNLOAD_LEADIN_TIME=10,  # seconds
    ADDITIONAL_VERIFICATION_TIME_MULTIPLIER=1,
    BLENDER_THREADS=1,
)
class SubtaskResultsVerifyIntegrationTest(ConcentIntegrationTestCase):
    def setUp(self):
        super().setUp()
        self.task_id = "task1"
        self.subtask_id = "subtask1"
        self.subtask_result_rejected_time_str = "2018-04-01 10:30:00"
        self.source_package_path = get_storage_source_file_path(
            subtask_id=self.subtask_id,
            task_id=self.task_id,
        )
        self.result_package_path = get_storage_result_file_path(
            subtask_id=self.subtask_id,
            task_id=self.task_id,
        )
        self.report_computed_task = self._create_report_computed_task()

    def test_that_concent_responds_with_service_refused_when_verification_for_this_subtask_is_duplicated(self):
        """
        Provider -> Concent: SubtaskResultsVerify
        Concent -> Provider: ServiceRefused (DuplicateRequest)
        """
        # given
        (serialized_subtask_results_verify,
         subtask_results_verify_time_str) = self._create_serialized_subtask_results_verify()

        store_or_update_subtask(
            task_id=self.task_id,
            subtask_id=self.subtask_id,
            provider_public_key=self.PROVIDER_PUBLIC_KEY,
            requestor_public_key=self.REQUESTOR_PUBLIC_KEY,
            state=Subtask.SubtaskState.ADDITIONAL_VERIFICATION,
            next_deadline=parse_iso_date_to_timestamp(subtask_results_verify_time_str) + (self.compute_task_def['deadline'] - self.task_to_compute.timestamp),
            task_to_compute=self.report_computed_task.task_to_compute,
            report_computed_task=self.report_computed_task,
        )
        self._assert_stored_message_counter_increased(2)

        # when
        with freeze_time(subtask_results_verify_time_str):
            response = self.client.post(
                reverse('core:send'),
                data=serialized_subtask_results_verify,
                content_type='application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY=self._get_encoded_provider_public_key(),
                HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY=self._get_encoded_requestor_public_key(),
            )

        # then
        self._test_response(
            response,
            status=200,
            key=self.PROVIDER_PRIVATE_KEY,
            message_type=message.concents.ServiceRefused,
            fields={
                'reason': message.concents.ServiceRefused.REASON.DuplicateRequest,
            }
        )
        self._assert_stored_message_counter_not_increased()

    def test_that_concent_responds_with_http_400_when_verification_received_in_accepted_state(self):
        """
        Provider -> Concent: SubtaskResultsVerify
        Concent -> Provider: HTTP400
        """
        # given
        (serialized_subtask_results_verify,
         subtask_results_verify_time_str) = self._create_serialized_subtask_results_verify()

        store_or_update_subtask(
            task_id=self.task_id,
            subtask_id=self.subtask_id,
            provider_public_key=self.PROVIDER_PUBLIC_KEY,
            requestor_public_key=self.REQUESTOR_PUBLIC_KEY,
            state=Subtask.SubtaskState.ACCEPTED,
            task_to_compute=self.report_computed_task.task_to_compute,  # pylint: disable=no-member
            report_computed_task=self.report_computed_task,
        )
        self._assert_stored_message_counter_increased(increased_by=2)

        # when
        with freeze_time(subtask_results_verify_time_str):
            response = self.client.post(
                reverse('core:send'),
                data=serialized_subtask_results_verify,
                content_type='application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY=self._get_encoded_provider_public_key(),
                HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY=self._get_encoded_requestor_public_key(),
            )

        # then
        self._test_400_response(
            response,
            error_code=ErrorCode.QUEUE_SUBTASK_STATE_TRANSITION_NOT_ALLOWED
        )
        self._assert_stored_message_counter_not_increased()

    def test_that_concent_responds_with_http_400_when_verification_received_in_failed_state(self):
        """
        Provider -> Concent: SubtaskResultsVerify
        Concent -> Provider: HTTP400
        """
        # given
        (serialized_subtask_results_verify,
         subtask_results_verify_time_str) = self._create_serialized_subtask_results_verify()

        store_or_update_subtask(
            task_id=self.task_id,
            subtask_id=self.subtask_id,
            provider_public_key=self.PROVIDER_PUBLIC_KEY,
            requestor_public_key=self.REQUESTOR_PUBLIC_KEY,
            state=Subtask.SubtaskState.FAILED,
            task_to_compute=self.report_computed_task.task_to_compute,  # pylint: disable=no-member
            report_computed_task=self.report_computed_task,
        )
        self._assert_stored_message_counter_increased(increased_by=2)

        # when
        with freeze_time(subtask_results_verify_time_str):
            response = self.client.post(
                reverse('core:send'),
                data=serialized_subtask_results_verify,
                content_type='application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY=self._get_encoded_provider_public_key(),
                HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY=self._get_encoded_requestor_public_key(),
            )

        # then
        self._test_400_response(
            response,
            error_code=ErrorCode.QUEUE_SUBTASK_STATE_TRANSITION_NOT_ALLOWED
        )
        self._assert_stored_message_counter_not_increased()

    def test_that_concent_responds_with_service_refused_when_request_arrives_too_late(self):
        """
        Provider -> Concent: SubtaskResultsVerify
        Concent -> Provider: ServiceRefused (InvalidRequest)
        """
        # given
        (serialized_subtask_results_verify,
         subtask_results_verify_time_str) = self._create_serialized_subtask_results_verify(
            time_offset=(self.compute_task_def['deadline'] - self.task_to_compute.timestamp) + 1)

        # when
        with freeze_time(subtask_results_verify_time_str):
            response = self.client.post(
                reverse('core:send'),
                data=serialized_subtask_results_verify,
                content_type='application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY=self._get_encoded_provider_public_key(),
                HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY=self._get_encoded_requestor_public_key(),
            )

        # then
        self._test_response(
            response,
            status=200,
            key=self.PROVIDER_PRIVATE_KEY,
            message_type=message.concents.ServiceRefused,
            fields={
                'reason': message.concents.ServiceRefused.REASON.InvalidRequest,
            }
        )
        self._assert_stored_message_counter_not_increased()

    def test_that_concent_reponds_with_too_small_requestor_deposit_when_requestor_doesnt_have_funds(self):
        """
        Provider -> Concent: SubtaskResultsVerify
        Concent -> Provider: ServiceRefused (TooSmallRequestorDeposit)
        """
        # given
        (serialized_subtask_results_verify,
         subtask_results_verify_time_str) = self._create_serialized_subtask_results_verify()

        # when
        with mock.patch(
            "core.message_handlers.payments_service.is_account_status_positive",
            return_value=False
        ) as is_account_status_positive_mock:
            with freeze_time(subtask_results_verify_time_str):
                response = self.client.post(
                    reverse('core:send'),
                    data=serialized_subtask_results_verify,
                    content_type='application/octet-stream',
                    HTTP_CONCENT_CLIENT_PUBLIC_KEY=self._get_encoded_provider_public_key(),
                    HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY=self._get_encoded_requestor_public_key(),
                )

        is_account_status_positive_mock.assert_called_with(
            client_eth_address=self.report_computed_task.task_to_compute.requestor_ethereum_address,
            pending_value=0,
        )

        # then
        self._test_response(
            response,
            status=200,
            key=self.PROVIDER_PRIVATE_KEY,
            message_type=message.concents.ServiceRefused,
            fields={
                'reason': message.concents.ServiceRefused.REASON.TooSmallRequestorDeposit,
            }
        )
        self._assert_stored_message_counter_not_increased()

    def test_that_concent_responds_with_service_refused_when_requestor_does_not_complain_about_verification(self):
        """
        Provider -> Concent: SubtaskResultsVerify
        Concent -> Provider: ServiceRefused (InvalidRequest)
        """
        # given
        (serialized_subtask_results_verify,
         subtask_results_verify_time_str) = self._create_serialized_subtask_results_verify(
            reason_of_rejection=message.tasks.SubtaskResultsRejected.REASON.ResourcesFailure)

        # when
        with freeze_time(subtask_results_verify_time_str):
            response = self.client.post(
                reverse('core:send'),
                data=serialized_subtask_results_verify,
                content_type='application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY=self._get_encoded_provider_public_key(),
                HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY=self._get_encoded_requestor_public_key(),
            )

        # then
        self._test_response(
            response,
            status=200,
            key=self.PROVIDER_PRIVATE_KEY,
            message_type=message.concents.ServiceRefused,
            fields={
                'reason': message.concents.ServiceRefused.REASON.InvalidRequest,
            }
        )
        self._assert_stored_message_counter_not_increased()

    def test_that_concent_responds_with_service_refused_when_subtask_results_rejected_not_issued_by_requestor(self):
        """
        Provider -> Concent: SubtaskResultsVerify
        Concent -> Provider: ServiceRefused (InvalidRequest)
        """
        # given
        (serialized_subtask_results_verify,
         subtask_results_verify_time_str) = self._create_serialized_subtask_results_verify(
            key=self.DIFFERENT_REQUESTOR_PRIVATE_KEY,
        )

        # when
        with freeze_time(subtask_results_verify_time_str):
            response = self.client.post(
                reverse('core:send'),
                data=serialized_subtask_results_verify,
                content_type='application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY=self._get_encoded_provider_public_key(),
                HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY=self._get_encoded_requestor_public_key(),
            )

        # then
        self._test_response(
            response,
            status=200,
            key=self.PROVIDER_PRIVATE_KEY,
            message_type=message.concents.ServiceRefused,
            fields={
                'reason': message.concents.ServiceRefused.REASON.InvalidRequest,
            }
        )
        self._assert_stored_message_counter_not_increased()

    def test_that_concent_accepts_valid_request_and_sends_verification_order_to_work_queue(self):
        """
        Provider -> Concent: SubtaskResultsVerify
        Concent -> Provider: AckSubtaskResultsVerify
        """
        # given
        (serialized_subtask_results_verify,
         subtask_results_verify_time_str) = self._create_serialized_subtask_results_verify()

        # when
        with mock.patch("core.message_handlers.payments_service.is_account_status_positive", return_value=True) as is_account_status_positive_mock:
            with mock.patch("core.queue_operations.blender_verification_request.delay") as send_verification_request_mock:
                with freeze_time(subtask_results_verify_time_str):
                    response = self.client.post(
                        reverse('core:send'),
                        data=serialized_subtask_results_verify,
                        content_type='application/octet-stream',
                        HTTP_CONCENT_CLIENT_PUBLIC_KEY=self._get_encoded_provider_public_key(),
                        HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY=self._get_encoded_requestor_public_key(),
                    )

        is_account_status_positive_mock.assert_called_with(
            client_eth_address=self.report_computed_task.task_to_compute.requestor_ethereum_address,
            pending_value=0,
        )
        send_verification_request_mock.assert_called_once_with(
            frames=[1],
            subtask_id=self.subtask_id,
            source_package_path=self.source_package_path,
            result_package_path=self.result_package_path,
            output_format=self.report_computed_task.task_to_compute.compute_task_def['extra_data']['output_format'],
            scene_file=self.report_computed_task.task_to_compute.compute_task_def['extra_data']['scene_file'],
            verification_deadline=self._get_verification_deadline_as_timestamp(
                parse_iso_date_to_timestamp(self.subtask_result_rejected_time_str),
                self.task_to_compute,
            ),
            blender_crop_script=self.report_computed_task.task_to_compute.compute_task_def['extra_data']['script_src'],
        )

        # then
        self._test_response(
            response,
            status=200,
            key=self.PROVIDER_PRIVATE_KEY,
            message_type=message.concents.AckSubtaskResultsVerify,
            fields={
                'subtask_results_verify': self._prepare_subtask_results_verify(serialized_subtask_results_verify),
                'file_transfer_token': self._prepare_file_transfer_token(subtask_results_verify_time_str),
                'file_transfer_token.files': [
                    message.FileTransferToken.FileInfo(
                        path='blender/result/task1/task1.subtask1.zip',
                        checksum='sha1:4452d71687b6bc2c9389c3349fdc17fbd73b833b',
                        size=1,
                        category=message.FileTransferToken.FileInfo.Category.results,
                    ),
                    message.FileTransferToken.FileInfo(
                        path='blender/source/task1/task1.subtask1.zip',
                        checksum='sha1:230fb0cad8c7ed29810a2183f0ec1d39c9df3f4a',
                        size=1,
                        category=message.FileTransferToken.FileInfo.Category.resources,
                    )
                ]
            }
        )
        self._assert_stored_message_counter_increased(increased_by=3)

    def test_that_concent_should_change_subtask_state_if_verification_is_after_deadline(self):
        """
        Tests that Concent should change subtask state if verification is after deadline.
        To achieve changing state by working queue mechanism, a duplicated SubtaskResultsVerify is being sent.

        Provider -> Concent: SubtaskResultsVerify
        Concent  -> Provider: SubtaskResultsSettled
        Concent  -> Requestor: SubtaskResultsSettled
        """

        with freeze_time("2018-04-01 10:30:00"):
            subtask = store_or_update_subtask(
                task_id=self.task_id,
                subtask_id=self.subtask_id,
                provider_public_key=self.PROVIDER_PUBLIC_KEY,
                requestor_public_key=self.REQUESTOR_PUBLIC_KEY,
                state=Subtask.SubtaskState.ADDITIONAL_VERIFICATION,
                next_deadline=get_current_utc_timestamp() + (self.compute_task_def['deadline'] - self.task_to_compute.timestamp),
                task_to_compute=self.report_computed_task.task_to_compute,
                report_computed_task=self.report_computed_task,
            )
            self._assert_stored_message_counter_increased(2)

            subtask_results_rejected = self._get_deserialized_subtask_results_rejected(
                reason=message.tasks.SubtaskResultsRejected.REASON.VerificationNegative,
                report_computed_task=self.report_computed_task,
            )

        with freeze_time(parse_timestamp_to_utc_datetime(subtask.next_deadline.timestamp() + 1)):
            serialized_subtask_results_verify = self._get_serialized_subtask_results_verify(
                subtask_results_verify=self._get_deserialized_subtask_results_verify(
                    subtask_results_rejected=subtask_results_rejected
                )
            )
            response = self.client.post(
                reverse('core:send'),
                data=serialized_subtask_results_verify,
                content_type='application/octet-stream',
            )

        assert response.status_code == 200

        subtask.refresh_from_db()
        self.assertEqual(subtask.state_enum, Subtask.SubtaskState.ACCEPTED)
        self.assertEqual(subtask.next_deadline, None)
        self._test_undelivered_pending_responses(
            subtask_id=subtask.subtask_id,
            client_public_key=self._get_encoded_provider_public_key(),
            client_public_key_out_of_band=self._get_encoded_provider_public_key(),
            expected_pending_responses_receive_out_of_band=[
                PendingResponse.ResponseType.SubtaskResultsSettled,
            ]
        )
        self._test_undelivered_pending_responses(
            subtask_id=subtask.subtask_id,
            client_public_key=self._get_encoded_requestor_public_key(),
            client_public_key_out_of_band=self._get_encoded_requestor_public_key(),
            expected_pending_responses_receive_out_of_band=[
                PendingResponse.ResponseType.SubtaskResultsSettled,
            ]
        )

        response_2 = self.client.post(
            reverse('core:receive_out_of_band'),
            data         = self._create_requestor_auth_message(),
            content_type = 'application/octet-stream',
        )

        self._test_response(
            response_2,
            status=200,
            key=self.REQUESTOR_PRIVATE_KEY,
            message_type=message.concents.SubtaskResultsSettled,
            fields={
                'origin': message.concents.SubtaskResultsSettled.Origin.ResultsRejected,
                'task_to_compute': self.report_computed_task.task_to_compute,
            }
        )

        response_3 = self.client.post(
            reverse('core:receive_out_of_band'),
            data=self._create_provider_auth_message(),
            content_type='application/octet-stream',
        )

        self._test_response(
            response_3,
            status=200,
            key=self.PROVIDER_PRIVATE_KEY,
            message_type=message.concents.SubtaskResultsSettled,
            fields={
                'origin': message.concents.SubtaskResultsSettled.Origin.ResultsRejected,
                'task_to_compute': self.report_computed_task.task_to_compute,
            }
        )

    def test_that_concent_should_change_subtask_state_to_failed_if_files_were_not_uploaded_on_time(self):
        """
        Provider -> Concent: SubtaskResultsVerify
        Concent -> Provider: SubtaskResultsRejected
        Concent -> Requester: SubtaskResultsRejected
        """

        # given
        (serialized_subtask_results_verify,
         subtask_results_verify_time_str) = self._create_serialized_subtask_results_verify()
        subtask_results_verify_date_time = self._create_datetime_from_string(subtask_results_verify_time_str)

        # when
        with mock.patch("core.message_handlers.payments_service.is_account_status_positive", autospec=True, return_value=True):
            with mock.patch("core.message_handlers.send_blender_verification_request", autospec=True):
                with freeze_time(subtask_results_verify_date_time):
                    ack_subtask_results_verify = self.client.post(
                        reverse('core:send'),
                        data=serialized_subtask_results_verify,
                        content_type='application/octet-stream',
                    )

                    self._test_response(
                        ack_subtask_results_verify,
                        status=200,
                        key=self.PROVIDER_PRIVATE_KEY,
                        message_type=message.concents.AckSubtaskResultsVerify,
                    )

        too_late = subtask_results_verify_date_time + timedelta((self.compute_task_def['deadline'] - self.task_to_compute.timestamp))
        with freeze_time(too_late):
            response_2 = self.client.post(
                reverse('core:receive_out_of_band'),
                data=self._create_requestor_auth_message(),
                content_type='application/octet-stream',
            )

            response_3 = self.client.post(
                reverse('core:receive_out_of_band'),
                data=self._create_provider_auth_message(),
                content_type='application/octet-stream',
            )

            # then
            self._test_response(
                response_2,
                status=200,
                key=self.REQUESTOR_PRIVATE_KEY,
                message_type=message.tasks.SubtaskResultsRejected,
                fields={
                    'reason': message.tasks.SubtaskResultsRejected.REASON.ConcentResourcesFailure,
                    'report_computed_task': self.report_computed_task,
                }
            )

            self._test_response(
                response_3,
                status=200,
                key=self.PROVIDER_PRIVATE_KEY,
                message_type=message.tasks.SubtaskResultsRejected,
                fields={
                    'reason': message.tasks.SubtaskResultsRejected.REASON.ConcentResourcesFailure,
                    'report_computed_task': self.report_computed_task,
                }
            )

    def _prepare_subtask_results_verify(self, serialized_subtask_results_verify):
        subtask_results_verify = load(
            serialized_subtask_results_verify,
            CONCENT_PRIVATE_KEY,
            self.PROVIDER_PUBLIC_KEY,
            check_time=False,
        )
        subtask_results_verify.encrypted = False
        return subtask_results_verify

    def _prepare_file_transfer_token(self, subtask_results_verify_time_str):
        with freeze_time(subtask_results_verify_time_str):
            file_transfer_token = create_file_transfer_token_for_golem_client(
                self.report_computed_task,
                self.PROVIDER_PUBLIC_KEY,
                message.FileTransferToken.Operation.upload,
            )
        return file_transfer_token

    def _create_serialized_subtask_results_verify(
        self,
        reason_of_rejection=message.tasks.SubtaskResultsRejected.REASON.VerificationNegative,
        time_offset=None,
        key=None,
    ):
        if time_offset is None:
            time_offset = (self.compute_task_def['deadline'] - self.task_to_compute.timestamp)

        subtask_results_rejected = self._get_deserialized_subtask_results_rejected(
            reason=reason_of_rejection,
            timestamp=self.subtask_result_rejected_time_str,
            report_computed_task=self.report_computed_task,
            signer_private_key=key,
        )
        subtask_results_verify_time_str = add_time_offset_to_date(
            self.subtask_result_rejected_time_str,
            time_offset
        )

        subtask_results_verify = self._get_deserialized_subtask_results_verify(
            timestamp=subtask_results_verify_time_str,
            subtask_results_rejected=subtask_results_rejected)

        serialized_subtask_results_verify = self._get_serialized_subtask_results_verify(
            subtask_results_verify=subtask_results_verify
        )
        return serialized_subtask_results_verify, subtask_results_verify_time_str

    def _create_report_computed_task(self):
        time_str = "2018-04-01 10:00:00"
        self.compute_task_def = self._get_deserialized_compute_task_def(
            deadline=add_time_offset_to_date(time_str, 3600),
            task_id=self.task_id,
            subtask_id=self.subtask_id,
            extra_data={
                'end_task': 6,
                'frames': [1],
                'outfilebasename': 'Heli-cycles(3)',
                'output_format': BlenderSubtaskDefinition.OutputFormat.JPG.name,  # pylint: disable=no-member
                'path_root': '/home/dariusz/Documents/tasks/resources',
                'scene_file': '/golem/resources/scene-Helicopter-27-internal.blend',
                'script_src': '# This template is rendered by',
                'start_task': 6,
                'total_tasks': 8
            }
        )
        self.task_to_compute = self._get_deserialized_task_to_compute(
            timestamp=time_str,
            compute_task_def=self.compute_task_def,
        )

        report_computed_task = self._get_deserialized_report_computed_task(
            timestamp="2018-04-01 10:01:00",
            subtask_id=self.subtask_id,
            task_to_compute=self.task_to_compute
        )
        return report_computed_task
