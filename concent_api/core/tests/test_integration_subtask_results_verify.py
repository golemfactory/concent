from base64 import b64encode

import mock
from django.conf import settings
from django.test import override_settings
from django.urls import reverse
from freezegun import freeze_time

from golem_messages import message, load

from core.message_handlers import store_or_update_subtask
from core.models import Subtask
from core.tests.utils import ConcentIntegrationTestCase
from core.transfer_operations import create_file_transfer_token
from utils.helpers import decode_key
from utils.testing_helpers import generate_ecc_key_pair

(CONCENT_PRIVATE_KEY, CONCENT_PUBLIC_KEY) = generate_ecc_key_pair()


@override_settings(
    CONCENT_PRIVATE_KEY  = CONCENT_PRIVATE_KEY,
    CONCENT_PUBLIC_KEY   = CONCENT_PUBLIC_KEY,
)
class SubtaskResultsVerifyIntegrationTest(ConcentIntegrationTestCase):
    def setUp(self):
        super().setUp()
        self.task_id = "task_1"
        self.subtask_id = "subtask_1"
        self.report_computed_task = self._create_report_computed_task()

    def test_that_concent_responds_with_service_refused_when_verification_for_this_subtask_done_before(self):
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
            next_deadline=self._parse_iso_date_to_timestamp(
                subtask_results_verify_time_str) + settings.ADDITIONAL_VERIFICATION_CALL_TIME
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
                'reason': message.concents.ServiceRefused.REASON.DuplicateRequest,
            }
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
            time_offset=settings.ADDITIONAL_VERIFICATION_CALL_TIME + 1
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

    def test_that_concent_reponds_with_too_small_requestor_deposit_when_requestor_doesnt_have_funds(self):
        """
        Provider -> Concent: SubtaskResultsVerify
        Concent -> Provider: ServiceRefused (TooSmallRequestorDeposit)
        """
        # given
        (serialized_subtask_results_verify,
         subtask_results_verify_time_str) = self._create_serialized_subtask_results_verify()

        # when
        with mock.patch("core.message_handlers.base.is_requestor_account_status_positive", return_value=False):
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
        with mock.patch("core.message_handlers.base.is_requestor_account_status_positive", return_value=True):
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
        with mock.patch("core.message_handlers.base.is_requestor_account_status_positive", return_value=True):
            with mock.patch("core.message_handlers.send_blender_verification_request") as send_verification_request_mock:
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
            message_type=message.concents.AckSubtaskResultsVerify,
            fields={
                'subtask_results_verify': self._prepare_subtask_results_verify(serialized_subtask_results_verify),
                'file_transfer_token': self._prepare_file_transfer_token(subtask_results_verify_time_str),
            }
        )
        self._assert_stored_message_counter_increased(increased_by=2)
        send_verification_request_mock.assert_called_once()  # TODO: once verification_request implemented change to 'assert_called_once_with'

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
            file_transfer_token = create_file_transfer_token(
                self.report_computed_task,
                b64encode(decode_key(self._get_encoded_provider_public_key())),
                "upload"
            )
            file_transfer_token.encrypted = False
        return file_transfer_token

    def _create_serialized_subtask_results_verify(
        self,
        reason_of_rejection=message.tasks.SubtaskResultsRejected.REASON.VerificationNegative,
        time_offset=settings.ADDITIONAL_VERIFICATION_CALL_TIME / 2
    ):
        subtask_result_rejected_time_str = "2018-04-01 10:30:00"
        subtask_results_rejected = self._get_deserialized_subtask_results_rejected(
            reason=reason_of_rejection,
            timestamp=subtask_result_rejected_time_str,
            report_computed_task=self.report_computed_task)
        subtask_results_verify_time_str = self._add_time_offset_to_date(subtask_result_rejected_time_str,
                                                                        time_offset)
        subtask_results_verify = self._get_deserialized_subtask_results_verify(
            timestamp=subtask_results_verify_time_str,
            subtask_results_rejected=subtask_results_rejected)

        serialized_subtask_results_verify = self._get_serialized_subtask_results_verify(
            subtask_results_verify=subtask_results_verify
        )
        return serialized_subtask_results_verify, subtask_results_verify_time_str

    def _create_report_computed_task(self):
        time_str = "2018-04-01 10:00:00"
        task_to_compute = self._get_deserialized_task_to_compute(
            timestamp=time_str,
            deadline=self._add_time_offset_to_date(time_str, 3600),
            task_id=self.task_id,
            subtask_id=self.subtask_id
        )
        report_computed_task = self._get_deserialized_report_computed_task(
            timestamp="2018-04-01 10:01:00",
            subtask_id=self.subtask_id,
            task_to_compute=task_to_compute
        )
        return report_computed_task
