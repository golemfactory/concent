from datetime import datetime
from unittest import expectedFailure

from django.conf import settings
from django.urls import reverse
from freezegun import freeze_time

from core.message_handlers import store_or_update_subtask
from core.models import Subtask
from core.tests.utils import ConcentIntegrationTestCase
from golem_messages import message


class SubtaskResultsVerifyIntegrationTest(ConcentIntegrationTestCase):
    def test_that_concent_responds_with_service_refused_when_verification_for_this_subtask_done_before(self):
        # given
        task_id = "task_1"
        subtask_id = "subtask_1"

        (serialized_subtask_results_verify, subtask_results_verify_time_str) = self._create_serialized_subtask_results_verify(
            subtask_id, task_id)

        store_or_update_subtask(
            task_id=task_id,
            subtask_id=subtask_id,
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

    def _create_serialized_subtask_results_verify(
        self,
        subtask_id,
        task_id,
        reason_of_rejection=message.tasks.SubtaskResultsRejected.REASON.VerificationNegative
    ):
        time_str = "2018-04-01 10:00:00"
        task_to_compute = self._get_deserialized_task_to_compute(
            timestamp=time_str,
            deadline=self._add_time_offset_to_date(time_str, 3600),
            task_id=task_id,
            subtask_id=subtask_id
        )
        report_computed_task = self._get_deserialized_report_computed_task(
            timestamp="2018-04-01 10:01:00",
            subtask_id=subtask_id,
            task_to_compute=task_to_compute
        )
        subtask_result_rejected_time_str = "2018-04-01 10:30:00"
        subtask_results_rejected = self._get_deserialized_subtask_results_rejected(
            reason=reason_of_rejection,
            timestamp=subtask_result_rejected_time_str,
            report_computed_task=report_computed_task)
        subtask_results_verify_time_str = self._add_time_offset_to_date(subtask_result_rejected_time_str,
                                                                        settings.ADDITIONAL_VERIFICATION_CALL_TIME / 2)
        subtask_results_verify = self._get_deserialized_subtask_results_verify(
            timestamp=subtask_results_verify_time_str,
            subtask_results_rejected=subtask_results_rejected)
        serialized_subtask_results_verify = self._get_serialized_subtask_results_verify(
            subtask_results_verify=subtask_results_verify
        )
        return serialized_subtask_results_verify, subtask_results_verify_time_str

    @expectedFailure
    def test_that_concent_responds_with_service_refused_when_requestor_does_not_complain_about_verification(self):
        self.fail("not implemented yet")

    @expectedFailure
    def test_that_concent_reponds_with_service_refused_when_subtask_results_rejected_is_invalid(self):
        self.fail("not implemented yet")

    @expectedFailure
    def test_that_concent_reponds_with_insufficient_funds_when_requestor_doesnt_have_funds(self):
        pass

    @expectedFailure
    def test_that_concent_accepts_valid_request_and_sends_verification_order_to_work_queue(self):
        self.fail("not implemented yet")

    def _add_time_offset_to_date(self, base_time, offset):
        """
        :param base_time: string format
        :param offset: timestamp format
        :return: new time in a string format
        """
        return datetime.fromtimestamp(self._parse_iso_date_to_timestamp(base_time) + offset).strftime(
            '%Y-%m-%d %H:%M:%S'
        )
