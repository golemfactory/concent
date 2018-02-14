from base64                 import b64encode

import datetime
import functools
import dateutil.parser

from django.conf            import settings
from django.test            import TestCase
from django.utils           import timezone

from freezegun              import freeze_time

from golem_messages         import dump
from golem_messages         import load
from golem_messages         import message
from core.models            import StoredMessage
from core.models            import MessageAuth
from core.models            import ReceiveStatus

from utils.testing_helpers  import generate_ecc_key_pair


class ConcentIntegrationTestCase(TestCase):

    def setUp(self):
        super().setUp()
        (self.PROVIDER_PRIVATE_KEY,  self.PROVIDER_PUBLIC_KEY)    = generate_ecc_key_pair()
        (self.REQUESTOR_PRIVATE_KEY, self.REQUESTOR_PUBLIC_KEY)   = generate_ecc_key_pair()
        (self.DIFFERENT_PROVIDER_PRIVATE_KEY, self.DIFFERENT_PROVIDER_PUBLIC_KEY) = generate_ecc_key_pair()
        (self.DIFFERENT_REQUESTOR_PRIVATE_KEY, self.DIFFERENT_REQUESTOR_PUBLIC_KEY) = generate_ecc_key_pair()

    def _get_encoded_key(self, key):  # pylint: disable=no-self-use
        """ Returns given key encoded. """
        return b64encode(key).decode('ascii')

    def _get_encoded_provider_public_key(self):
        """ Returns provider public key encoded. """
        return self._get_encoded_key(self.PROVIDER_PUBLIC_KEY)

    def _get_encoded_requestor_public_key(self):
        """ Returns provider public key encoded. """
        return self._get_encoded_key(self.REQUESTOR_PUBLIC_KEY)

    def _get_serialized_force_get_task_result(
        self,
        report_computed_task,
        timestamp,
        requestor_private_key = None
    ):
        """ Returns MessageForceGetTaskResult serialized. """
        with freeze_time(timestamp):
            force_get_task_result = message.concents.ForceGetTaskResult(
                report_computed_task    = report_computed_task,
            )
        return dump(
            force_get_task_result,
            requestor_private_key or self.REQUESTOR_PRIVATE_KEY,
            settings.CONCENT_PUBLIC_KEY
        )

    def _get_deserialized_report_computed_task(  # pylint: disable=no-self-use
        self,
        subtask_id      = '1',
        task_to_compute = None,
        size            = None,
        checksum        = None,
        timestamp       = None,
    ):
        """ Returns ReportComputedTask deserialized. """
        with freeze_time(timestamp or self._get_timestamp_string()):
            report_computed_task = message.ReportComputedTask(
                subtask_id      = subtask_id,
                task_to_compute = (
                    task_to_compute or
                    self._get_deserialized_task_to_compute()
                ),
                size            = size,
                checksum        = checksum
            )
        return report_computed_task

    def _get_deserialized_task_to_compute(
        self,
        timestamp           = None,
        deadline            = None,
        task_id             = '1',
        compute_task_def    = None
    ):
        """ Returns TaskToCompute deserialized. """
        if compute_task_def is None:
            compute_task_def                = message.ComputeTaskDef()
            compute_task_def['task_id']     = task_id
            if isinstance(deadline, int):
                compute_task_def['deadline'] = deadline
            elif isinstance(deadline, str):
                compute_task_def['deadline'] = self._parse_iso_date_to_timestamp(deadline)
            else:
                compute_task_def['deadline'] = self._parse_iso_date_to_timestamp(self._get_timestamp_string())

        with freeze_time(timestamp or self._get_timestamp_string()):
            task_to_compute = message.TaskToCompute(
                compute_task_def = compute_task_def,
            )
        return task_to_compute

    def _get_deserialized_ack_report_computed_task(
        self,
        timestamp       = None,
        deadline        = None,
        subtask_id      = '1',
        task_to_compute = None
    ):
        """ Returns AckReportComputedTask deserialized. """
        with freeze_time(timestamp or self._get_timestamp_string()):
            ack_report_computed_task = message.AckReportComputedTask(
                subtask_id      = subtask_id,
                task_to_compute = (
                    task_to_compute or
                    self._get_deserialized_task_to_compute(
                        timestamp = timestamp,
                        deadline  = deadline
                    )
                ),
            )
        return ack_report_computed_task

    def _get_serialized_ack_report_computed_task(
        self,
        timestamp                   = None,
        ack_report_computed_task    = None,
        requestor_private_key       = None,
    ):
        with freeze_time(timestamp or self._get_timestamp_string()):
            return dump(
                ack_report_computed_task,
                requestor_private_key or self.REQUESTOR_PRIVATE_KEY,
                settings.CONCENT_PUBLIC_KEY
            )

    def _parse_iso_date_to_timestamp(self, date_string):    # pylint: disable=no-self-use
        return int(dateutil.parser.parse(date_string).timestamp())

    def _get_timestamp_string(self):                        # pylint: disable=no-self-use
        return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _test_204_response(self, response):
        self.assertEqual(response.status_code, 204)
        self.assertEqual(len(response.content), 0)

    def _test_400_response(self, response):
        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.json().keys())

    def _test_response(self, response, status, key, message_type = None, fields = None):
        self.assertEqual(response.status_code, status)
        if message_type:
            message_from_concent = load(
                response.content,
                key,
                settings.CONCENT_PUBLIC_KEY,
                check_time = False
            )
            self.assertIsInstance(message_from_concent, message_type)

            if fields:
                for field_name, field_value in fields.items():
                    self.assertEqual(functools.reduce(getattr, field_name.split('.'), message_from_concent), field_value)
        else:
            self.assertEqual(len(response.content), 0)

    def _test_database_objects(
        self,
        last_object_type            = None,
        task_id                     = None,
        receive_delivered_status    = None,
    ):
        self.assertEqual(StoredMessage.objects.last().type,           last_object_type.TYPE)
        self.assertEqual(StoredMessage.objects.last().task_id,        task_id)

        if receive_delivered_status is not None:
            self.assertEqual(ReceiveStatus.objects.last().delivered,        receive_delivered_status)
            self.assertEqual(ReceiveStatus.objects.last().message.task_id,  task_id)

    def _get_deserialized_force_subtask_results(
        self,
        timestamp                   = None,
        ack_report_computed_task    = None,
    ):
        """ Returns ForceSubtaskResults deserialized. """
        with freeze_time(timestamp or self._get_timestamp_string()):
            force_subtask_results = message.concents.ForceSubtaskResults(
                # timestamp = self._parse_iso_date_to_timestamp(timestamp),
                ack_report_computed_task = (
                    ack_report_computed_task or
                    self._get_deserialized_ack_report_computed_task(
                        timestamp       = timestamp,
                        deadline        = (self._parse_iso_date_to_timestamp(timestamp) + 10),
                    )
                )
            )
        return force_subtask_results

    def _get_serialized_force_subtask_results(
        self,
        timestamp                   = None,
        ack_report_computed_task    = None,
        provider_private_key        = None,
    ):
        """ Returns ForceSubtaskResults serialized. """
        force_subtask_results = self._get_deserialized_force_subtask_results(
            timestamp                   = timestamp,
            ack_report_computed_task    = ack_report_computed_task
        )
        return dump(
            force_subtask_results,
            provider_private_key or self.PROVIDER_PRIVATE_KEY,
            settings.CONCENT_PUBLIC_KEY,
        )

    def _get_deserialized_subtask_results_accepted(
        self,
        timestamp   = None,
        subtask_id  = '1',
        payment_ts  = None,
    ):
        """ Return SubtaskResultsAccepted deserialized """
        with freeze_time(timestamp or self._get_timestamp_string()):
            subtask_results_accepted = message.tasks.SubtaskResultsAccepted(
                subtask_id      = subtask_id,
                payment_ts     = (
                    self._parse_iso_date_to_timestamp(payment_ts) or
                    self._parse_iso_date_to_timestamp(self._get_timestamp_string())
                )
            )
        return subtask_results_accepted

    def _get_serialized_subtask_results_accepted(
        self,
        timestamp               = None,
        subtask_id              = '1',
        payment_ts              = None,
        requestor_private_key   = None,
    ):
        """ Return SubtaskResultsAccepted serialized """
        subtask_results_accepted = self._get_deserialized_subtask_results_accepted(
            timestamp   = timestamp,
            subtask_id  = subtask_id,
            payment_ts  = payment_ts,
        )

        return dump(
            subtask_results_accepted,
            requestor_private_key or self.REQUESTOR_PRIVATE_KEY,
            settings.CONCENT_PUBLIC_KEY,
        )

    def _get_deserialized_subtask_results_rejected(
        self,
        timestamp               = None,
        reason                  = None,
        report_computed_task    = None,
    ):
        """ Return SubtaskResultsRejected deserialized """
        with freeze_time(timestamp or self._get_timestamp_string()):
            return message.tasks.SubtaskResultsRejected(
                reason = (
                    reason or
                    message.tasks.SubtaskResultsRejected.REASON.VerificationNegative
                ),
                report_computed_task = (
                    report_computed_task or
                    self._get_deserialized_report_computed_task(
                        subtask_id      = '1',
                        task_to_compute = self._get_deserialized_task_to_compute()
                    )
                ),
            )

    def _get_serialized_subtask_results_rejected(
        self,
        reason                  = None,
        timestamp               = None,
        requestor_private_key   = None,
        report_computed_task    = None,
    ):
        """ Return SubtaskResultsRejected serialized """
        with freeze_time(timestamp or self._get_timestamp_string()):
            subtask_results_rejected = self._get_deserialized_subtask_results_rejected(
                reason                  = reason,
                timestamp               = timestamp,
                report_computed_task    = report_computed_task,
            )
            return dump(
                subtask_results_rejected,
                requestor_private_key or self.REQUESTOR_PRIVATE_KEY,
                settings.CONCENT_PUBLIC_KEY,
            )

    def _get_deserialized_compute_task_def(
        self,
        task_id     = '1',
        deadline    = None,
    ):
        compute_task_def                = message.tasks.ComputeTaskDef()
        compute_task_def['task_id']     = task_id
        compute_task_def['deadline']    = self._parse_iso_date_to_timestamp(deadline)

        return compute_task_def

    def _get_deserialized_force_subtask_results_response(
        self,
        timestamp                   = None,
        subtask_results_accepted    = None,
        subtask_results_rejected    = None,
    ):
        with freeze_time(timestamp or self._get_timestamp_string()):
            force_subtask_results_response = message.concents.ForceSubtaskResultsResponse(
                subtask_results_accepted = subtask_results_accepted,
                subtask_results_rejected = subtask_results_rejected,
            )
            return force_subtask_results_response

    def _get_serialized_force_subtask_results_response(
        self,
        timestamp                   = None,
        subtask_results_accepted    = None,
        subtask_results_rejected    = None,
        requestor_private_key       = None,
    ):
        with freeze_time(timestamp or self._get_timestamp_string()):
            force_subtask_results_response = self._get_deserialized_force_subtask_results_response(
                timestamp                   = timestamp,
                subtask_results_accepted    = subtask_results_accepted,
                subtask_results_rejected    = subtask_results_rejected,
            )

        return dump(
            force_subtask_results_response,
            requestor_private_key or self.REQUESTOR_PRIVATE_KEY,
            settings.CONCENT_PUBLIC_KEY
        )

    def _get_deserialized_force_report_computed_task(
        self,
        timestamp       = None,
        task_to_compute = None,
    ):
        with freeze_time(timestamp or self._get_timestamp_string()):
            return message.concents.ForceReportComputedTask(
                task_to_compute = task_to_compute,
            )

    def _get_serialized_force_report_computed_task(
        self,
        timestamp                   = None,
        force_report_computed_task  = None,
        provider_private_key        = None,
    ):
        with freeze_time(timestamp or self._get_timestamp_string()):
            return dump(
                force_report_computed_task,
                provider_private_key or self.PROVIDER_PRIVATE_KEY,
                settings.CONCENT_PUBLIC_KEY
            )

    def _get_deserialized_cannot_compute_task(
        self,
        timestamp       = None,
        task_to_compute = None,
        reason          = None,
    ):
        with freeze_time(timestamp or self._get_timestamp_string()):
            return message.tasks.CannotComputeTask(
                task_to_compute = task_to_compute,
                reason          = reason,
            )

    def _get_deserialized_reject_report_computed_task(
        self,
        timestamp           = None,
        cannot_compute_task = None,
        task_to_compute     = None,
        reason              = None,
    ):
        with freeze_time(timestamp or self._get_timestamp_string()):
            return message.concents.RejectReportComputedTask(
                cannot_compute_task = cannot_compute_task,
                task_to_compute     = task_to_compute,
                reason              = reason,
            )

    def _get_serialized_reject_report_computed_task(
        self,
        timestamp                   = None,
        reject_report_computed_task = None,
        requestor_private_key       = None,
    ):
        with freeze_time(timestamp or self._get_timestamp_string()):
            return dump(
                reject_report_computed_task,
                requestor_private_key or self.REQUESTOR_PRIVATE_KEY,
                settings.CONCENT_PUBLIC_KEY
            )

    def _store_golem_messages_in_database(
        self,
        message_type,
        timestamp,
        data,
        task_id,
        status                  = None,
        delivered               = False,
        provider_public_key     = None,
        requestor_public_key    = None,
    ):
        with freeze_time(timestamp or self._get_timestamp_string()):
            message_timestamp = datetime.datetime.now(timezone.utc)
            data.sig = None
            golem_message = StoredMessage(
                type        = message_type,
                timestamp   = message_timestamp,
                data        = data.serialize(),
                task_id     = task_id
            )

            golem_message.full_clean()
            golem_message.save()

            message_auth = MessageAuth(
                message                    = golem_message,
                provider_public_key_bytes  = provider_public_key,
                requestor_public_key_bytes = requestor_public_key,
            )
            message_auth.full_clean()
            message_auth.save()

            if status is not None:
                message_status = status(
                    message     = golem_message,
                    timestamp   = message_timestamp,
                    delivered   = delivered,
                )
                message_status.full_clean()
                message_status.save()
