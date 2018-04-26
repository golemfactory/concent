from base64 import b64encode
import datetime
import functools
import mock

import dateutil.parser
from django.conf import settings
from django.shortcuts import reverse
from django.test import TestCase
from django.utils import timezone
from freezegun import freeze_time

from golem_messages         import dump
from golem_messages         import load
from golem_messages         import message

from core.models            import Client
from core.models            import PendingResponse
from core.models            import StoredMessage
from core.models            import Subtask

from utils.helpers          import sign_message
from utils.helpers          import get_current_utc_timestamp
from utils.testing_helpers  import generate_ecc_key_pair
from utils.testing_helpers  import generate_priv_and_pub_eth_account_key


class ConcentIntegrationTestCase(TestCase):

    def setUp(self):
        super().setUp()

        # Keys
        (self.PROVIDER_PRIVATE_KEY,                 self.PROVIDER_PUBLIC_KEY)               = generate_ecc_key_pair()
        (self.REQUESTOR_PRIVATE_KEY,                self.REQUESTOR_PUBLIC_KEY)              = generate_ecc_key_pair()
        (self.DIFFERENT_PROVIDER_PRIVATE_KEY,       self.DIFFERENT_PROVIDER_PUBLIC_KEY)     = generate_ecc_key_pair()
        (self.DIFFERENT_REQUESTOR_PRIVATE_KEY,      self.DIFFERENT_REQUESTOR_PUBLIC_KEY)    = generate_ecc_key_pair()
        (self.PROVIDER_PRIV_ETH_KEY,                self.PROVIDER_PUB_ETH_KEY)              = generate_priv_and_pub_eth_account_key()
        (self.REQUESTOR_PRIV_ETH_KEY,               self.REQUESTOR_PUB_ETH_KEY)             = generate_priv_and_pub_eth_account_key()
        (self.DIFFERENT_PROVIDER_PRIV_ETH_KEY,      self.DIFFERENT_PROVIDER_PUB_ETH_KEY)    = generate_priv_and_pub_eth_account_key()
        (self.DIFFERENT_REQUESTOR_PRIV_ETH_KEY,     self.DIFFERENT_REQUESTOR_PUB_ETH_KEY)   = generate_priv_and_pub_eth_account_key()

        # StoredMessage
        self.stored_message_counter = 0

        # Auth
        self.auth_message_counter = 0

    def _get_encoded_key(self, key):  # pylint: disable=no-self-use
        """ Returns given key encoded. """
        return b64encode(key).decode('ascii')

    def _get_encoded_provider_public_key(self):
        """ Returns provider public key encoded. """
        return self._get_encoded_key(self.PROVIDER_PUBLIC_KEY)

    def _get_encoded_requestor_public_key(self):
        """ Returns requestor public key encoded. """
        return self._get_encoded_key(self.REQUESTOR_PUBLIC_KEY)

    def _get_encoded_requestor_different_public_key(self):
        """ Returns requestor public key encoded. """
        return self._get_encoded_key(self.DIFFERENT_REQUESTOR_PUBLIC_KEY)

    def _get_requestor_ethereum_private_key(self):
        """ Return requestor private ethereum key """
        return self.REQUESTOR_PRIV_ETH_KEY

    def _get_requestor_ethereum_public_key(self):
        """ Returns requestor ethereum public key encoded. """
        return self.REQUESTOR_PUB_ETH_KEY

    def _get_requestor_ethereum_public_key_different(self):
        """ Returns requestor ethereum public key encoded. """
        return self.DIFFERENT_REQUESTOR_PUB_ETH_KEY

    def _get_provider_ethereum_private_key(self):
        """ Returns provider ethereum private key """
        return self.PROVIDER_PRIV_ETH_KEY

    def _get_provider_ethereum_public_key(self):
        """ Returns provider ethereum address """
        return self.PROVIDER_PUB_ETH_KEY

    def _get_provider_ethereum_public_key_different(self):
        """ Returns provider ethereum diffrent address """
        return self.DIFFERENT_PROVIDER_PUB_ETH_KEY

    def _sign_message(self, golem_message, client_private_key = None):
        return sign_message(
            golem_message,
            self.REQUESTOR_PRIVATE_KEY if client_private_key is None else client_private_key,
        )

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
            requestor_private_key if requestor_private_key is not None else self.REQUESTOR_PRIVATE_KEY,
            settings.CONCENT_PUBLIC_KEY
        )

    def _get_deserialized_report_computed_task(  # pylint: disable=no-self-use
        self,
        subtask_id      = '1',
        task_to_compute = None,
        size            = 1,
        package_hash    = None,
        timestamp       = None,
    ):
        """ Returns ReportComputedTask deserialized. """
        with freeze_time(timestamp or self._get_timestamp_string()):
            report_computed_task = message.ReportComputedTask(
                task_to_compute = (
                    task_to_compute or
                        self._get_deserialized_task_to_compute(
                            subtask_id=subtask_id
                        )
                ),
                size            = size,
                package_hash    = package_hash
            )
        return report_computed_task

    def _get_deserialized_task_to_compute(
        self,
        timestamp                       = None,
        deadline                        = None,
        task_id                         = '1',
        subtask_id                      = '2',
        compute_task_def                = None,
        requestor_public_key            = None,
        requestor_ethereum_public_key   = None,
        provider_public_key             = None,
        provider_ethereum_public_key    = None,
        price                           = 0,
        sign_with_private_key           = None,
    ):
        """ Returns TaskToCompute deserialized. """
        if compute_task_def is None:
            compute_task_def                = message.ComputeTaskDef()
            compute_task_def['task_id']     = task_id
            compute_task_def['subtask_id']  = subtask_id
            if isinstance(deadline, int):
                compute_task_def['deadline'] = deadline
            elif isinstance(deadline, str):
                compute_task_def['deadline'] = self._parse_iso_date_to_timestamp(deadline)
            else:
                compute_task_def['deadline'] = self._parse_iso_date_to_timestamp(self._get_timestamp_string()) + 10

        with freeze_time(timestamp or self._get_timestamp_string()):
            task_to_compute = message.TaskToCompute(
                compute_task_def                = compute_task_def,
                requestor_public_key            = (
                    requestor_public_key if requestor_public_key is not None else self.REQUESTOR_PUBLIC_KEY
                ),
                requestor_ethereum_public_key   = (
                    requestor_ethereum_public_key if requestor_ethereum_public_key is not None else self._get_requestor_ethereum_public_key()
                ),
                provider_public_key             = (
                    provider_public_key if provider_public_key is not None else self.PROVIDER_PUBLIC_KEY
                ),
                price=price,
                provider_ethereum_public_key    = (
                    provider_ethereum_public_key if provider_ethereum_public_key is not None else self._get_provider_ethereum_public_key()
                ),
            )
            task_to_compute = self._sign_message(
                task_to_compute,
                sign_with_private_key,
            )
        return task_to_compute

    def _get_deserialized_ack_report_computed_task(
        self,
        timestamp       = None,
        deadline        = None,
        subtask_id      = '1',
        report_computed_task = None,
        task_to_compute = None
    ):
        """ Returns AckReportComputedTask deserialized. """
        with freeze_time(timestamp or self._get_timestamp_string()):
            ack_report_computed_task = message.AckReportComputedTask(
                report_computed_task = (
                    report_computed_task if report_computed_task is not None else message.ReportComputedTask(
                        task_to_compute = (
                            task_to_compute or
                            self._get_deserialized_task_to_compute(
                                timestamp = timestamp,
                                deadline  = deadline,
                                subtask_id=subtask_id
                            )
                        ),
                    )
                )
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
                requestor_private_key if requestor_private_key is not None else self.REQUESTOR_PRIVATE_KEY,
                settings.CONCENT_PUBLIC_KEY
            )

    def _parse_iso_date_to_timestamp(self, date_string):    # pylint: disable=no-self-use
        return int(dateutil.parser.parse(date_string).timestamp())

    def _get_timestamp_string(self):                        # pylint: disable=no-self-use
        return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _test_204_response(self, response):
        self.assertEqual(response.status_code, 204)
        self.assertEqual(len(response.content), 0)

    def _test_400_response(self, response, error_message = None):
        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.json().keys())
        if error_message is not None:
            self.assertEqual(response.json()['error'], error_message)

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

    def _test_subtask_state(
        self,
        task_id:                    str,
        subtask_id:                 str,
        subtask_state:              Subtask.SubtaskState,
        provider_key:               str,
        requestor_key:              str,
        expected_nested_messages:   set,
        next_deadline:              int = None,
    ):
        self.assertTrue(StoredMessage.objects.filter(subtask_id = subtask_id).exists())
        subtask = Subtask.objects.get(subtask_id = subtask_id)
        self.assertEqual(subtask.task_id,              task_id)
        self.assertEqual(subtask.subtask_id,           subtask_id)
        self.assertEqual(subtask.state,                subtask_state.name)
        self.assertEqual(subtask.provider.public_key,  provider_key)
        self.assertEqual(subtask.requestor.public_key, requestor_key)

        assert Client.objects.filter(public_key = provider_key).exists()
        assert Client.objects.filter(public_key = requestor_key).exists()

        subtask_deadline = None
        if subtask.state_enum in Subtask.ACTIVE_STATES:
            subtask_deadline = subtask.next_deadline.timestamp()
        self.assertEqual(subtask_deadline, next_deadline)

        self._test_subtask_nested_messages(subtask, expected_nested_messages)

    def _test_subtask_nested_messages(self, subtask, expected_nested_messages):
        all_possible_messages = {
            'task_to_compute', 'report_computed_task', 'ack_report_computed_task', 'reject_report_computed_task', 'subtask_results_accepted', 'subtask_results_rejected'
        }
        required_messages = all_possible_messages & expected_nested_messages
        for nested_message in required_messages:
            self.assertIsNotNone(getattr(subtask, nested_message))
        unset_messages = all_possible_messages - expected_nested_messages
        for nested_message in unset_messages:
            self.assertIsNone(getattr(subtask, nested_message))

    def _test_last_stored_messages(self, expected_messages, task_id, subtask_id, timestamp):
        assert isinstance(expected_messages, list)
        assert isinstance(task_id,           str)
        assert isinstance(subtask_id,        str)

        expected_message_types = [expected_message.TYPE for expected_message in expected_messages]

        for stored_message in StoredMessage.objects.order_by('-id')[:len(expected_message_types)]:
            self.assertIn(stored_message.type,                      expected_message_types)
            self.assertEqual(stored_message.task_id,                task_id)
            self.assertEqual(stored_message.subtask_id,             subtask_id)
            self.assertEqual(stored_message.timestamp.timestamp(),  self._parse_iso_date_to_timestamp(timestamp))

            expected_message_types.remove(stored_message.type)

        assert expected_message_types == []

    def _test_undelivered_pending_responses(
        self,
        client_public_key,
        subtask_id,
        client_public_key_out_of_band                   = None,
        expected_pending_responses_receive              = None,
        expected_pending_responses_receive_out_of_band  = None,
    ):
        if expected_pending_responses_receive is None:
            expected_pending_responses_receive = []

        if expected_pending_responses_receive_out_of_band is None:
            expected_pending_responses_receive_out_of_band = []

        assert isinstance(expected_pending_responses_receive,               list)
        assert isinstance(expected_pending_responses_receive_out_of_band,   list)
        assert isinstance(client_public_key,                                str)
        assert isinstance(subtask_id,                                       str)
        if client_public_key_out_of_band is not None:
            assert isinstance(client_public_key_out_of_band, str)

        expected_pending_responses_receive_types = [
            expected_pending_response_receive.name for expected_pending_response_receive in expected_pending_responses_receive
        ]
        expected_pending_responses_receive_out_of_band_types = [
            expected_pending_response_receive_out_of_band.name for expected_pending_response_receive_out_of_band in expected_pending_responses_receive_out_of_band
        ]

        for pending_response in PendingResponse.objects.filter(
            delivered   = False,
            queue       = PendingResponse.Queue.Receive.name,  # pylint: disable=no-member
        ):
            self.assertIn(pending_response.response_type,           expected_pending_responses_receive_types)
            self.assertEqual(pending_response.subtask.subtask_id,   subtask_id)
            self.assertEqual(pending_response.client.public_key,    client_public_key)

            expected_pending_responses_receive_types.remove(pending_response.response_type)

        assert expected_pending_responses_receive_types == []

        for pending_response in PendingResponse.objects.filter(
            delivered   = False,
            queue       = PendingResponse.Queue.ReceiveOutOfBand.name,  # pylint: disable=no-member
        ):
            self.assertIn(pending_response.response_type,           expected_pending_responses_receive_out_of_band_types)
            self.assertEqual(pending_response.subtask.subtask_id,   subtask_id)
            self.assertEqual(pending_response.client.public_key,    client_public_key_out_of_band)

            expected_pending_responses_receive_out_of_band_types.remove(pending_response.response_type)

        assert expected_pending_responses_receive_out_of_band_types == []

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
            provider_private_key if provider_private_key is not None else self.PROVIDER_PRIVATE_KEY,
            settings.CONCENT_PUBLIC_KEY,
        )

    def _get_deserialized_subtask_results_accepted(
        self,
        timestamp           = None,
        task_to_compute     = None,
        payment_ts          = None,
    ):
        """ Return SubtaskResultsAccepted deserialized """
        with freeze_time(timestamp or self._get_timestamp_string()):
            subtask_results_accepted = message.tasks.SubtaskResultsAccepted(
                task_to_compute = task_to_compute,
                payment_ts     = (
                    self._parse_iso_date_to_timestamp(payment_ts) or
                    self._parse_iso_date_to_timestamp(self._get_timestamp_string())
                )
            )
        return subtask_results_accepted

    def _get_serialized_subtask_results_accepted(
        self,
        timestamp                   = None,
        payment_ts                  = None,
        requestor_private_key       = None,
        task_to_compute             = None,
        subtask_results_accepted    = None
    ):
        """ Return SubtaskResultsAccepted serialized """
        subtask_results_accepted = (
            subtask_results_accepted or
            self._get_deserialized_subtask_results_accepted(
                timestamp       = timestamp,
                payment_ts      = payment_ts,
                task_to_compute = task_to_compute
            )
        )

        return dump(
            subtask_results_accepted,
            requestor_private_key if requestor_private_key is not None else self.REQUESTOR_PRIVATE_KEY,
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
                        task_to_compute = self._sign_message(
                            self._get_deserialized_task_to_compute()
                        )
                    )
                ),
            )

    def _get_serialized_subtask_results_rejected(
        self,
        reason                      = None,
        timestamp                   = None,
        requestor_private_key       = None,
        report_computed_task        = None,
        subtask_results_rejected    = None
    ):
        """ Return SubtaskResultsRejected serialized """
        with freeze_time(timestamp or self._get_timestamp_string()):
            subtask_results_rejected = (
                subtask_results_rejected or
                self._get_deserialized_subtask_results_rejected(
                    reason                  = reason,
                    timestamp               = timestamp,
                    report_computed_task    = report_computed_task,
                )
            )
            return dump(
                subtask_results_rejected,
                requestor_private_key if requestor_private_key is not None else self.REQUESTOR_PRIVATE_KEY,
                settings.CONCENT_PUBLIC_KEY,
            )

    def _get_deserialized_compute_task_def(
        self,
        task_id     = '1',
        subtask_id  = '2',
        deadline    = None,
    ):
        compute_task_def                = message.tasks.ComputeTaskDef()
        compute_task_def['task_id']     = task_id
        compute_task_def['subtask_id']  = subtask_id
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
            requestor_private_key if requestor_private_key is not None else self.REQUESTOR_PRIVATE_KEY,
            settings.CONCENT_PUBLIC_KEY
        )

    def _get_deserialized_force_report_computed_task(
        self,
        timestamp               = None,
        report_computed_task    = None,
    ):
        with freeze_time(timestamp or self._get_timestamp_string()):
            return message.concents.ForceReportComputedTask(
                report_computed_task = report_computed_task,
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
                provider_private_key if provider_private_key is not None else self.PROVIDER_PRIVATE_KEY,
                settings.CONCENT_PUBLIC_KEY
            )

    def _get_deserialized_cannot_compute_task(
        self,
        timestamp       = None,
        task_to_compute = None,
        reason          = None,
    ):
        with freeze_time(timestamp or self._get_timestamp_string()):
            cannot_compute_task = message.tasks.CannotComputeTask(
                task_to_compute = task_to_compute,
                reason          = reason,
            )
            return self._sign_message(cannot_compute_task, self.PROVIDER_PRIVATE_KEY)

    def _get_deserialized_task_failure(
        self,
        timestamp=None,
        subtask_id='2',
        err=None,
        task_to_compute=None,
    ):
        with freeze_time(timestamp or self._get_timestamp_string()):
            task_failure = message.tasks.TaskFailure(
                subtask_id=subtask_id,
                err=err,
                task_to_compute=task_to_compute,
            )
            return self._sign_message(task_failure, self.PROVIDER_PRIVATE_KEY)

    def _get_deserialized_reject_report_computed_task(
        self,
        timestamp           = None,
        cannot_compute_task = None,
        task_failure        = None,
        task_to_compute     = None,
        reason              = None,
    ):
        with freeze_time(timestamp or self._get_timestamp_string()):
            return message.RejectReportComputedTask(
                cannot_compute_task = cannot_compute_task,
                task_to_compute     = task_to_compute,
                task_failure        = task_failure,
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
                requestor_private_key if requestor_private_key is not None else self.REQUESTOR_PRIVATE_KEY,
                settings.CONCENT_PUBLIC_KEY
            )

    def _get_deserialized_force_payment(
        self,
        timestamp = None,
        subtask_results_accepted_list = None
    ):
        with freeze_time(timestamp or self._get_timestamp_string()):
            force_payment = message.concents.ForcePayment(
                subtask_results_accepted_list = subtask_results_accepted_list
            )
            return force_payment

    def _get_serialized_force_payment(
        self,
        timestamp                       = None,
        subtask_results_accepted_list   = None,
        provider_private_key            = None
    ):
        with freeze_time(timestamp or self._get_timestamp_string()):
            force_payment = self._get_deserialized_force_payment(
                timestamp                       = timestamp,
                subtask_results_accepted_list   = subtask_results_accepted_list,
            )
        return dump(
            force_payment,
            provider_private_key if provider_private_key is not None else self.PROVIDER_PRIVATE_KEY,
            settings.CONCENT_PUBLIC_KEY
        )

    def _get_deserialized_subtask_results_verify(
        self,
        timestamp=None,
        subtask_results_rejected=None,
    ):
        """ Return SubtaskResultsVerify deserialized """
        with freeze_time(timestamp or self._get_timestamp_string()):
            return message.concents.SubtaskResultsVerify(
                subtask_results_rejected=(
                    subtask_results_rejected if subtask_results_rejected is not None else
                    self._get_deserialized_subtask_results_rejected()
                ),
            )

    def _get_serialized_subtask_results_verify(
        self,
        timestamp=None,
        subtask_results_verify=None,
        provider_private_key=None
    ):
        return dump(
            msg=(subtask_results_verify if subtask_results_verify is not None
                 else self._get_deserialized_subtask_results_verify(timestamp)),
            privkey=provider_private_key if provider_private_key is not None else self.PROVIDER_PRIVATE_KEY,
            pubkey=settings.CONCENT_PUBLIC_KEY,
        )

    def _store_golem_messages_in_database(
        self,
        message_type,
        timestamp,
        data,
        task_id,
    ):
        with freeze_time(timestamp or self._get_timestamp_string()):
            message_timestamp = datetime.datetime.now(timezone.utc)
            golem_message = StoredMessage(
                type        = message_type,
                timestamp   = message_timestamp,
                data        = data.serialize(),
                task_id     = task_id
            )

            golem_message.full_clean()
            golem_message.save()

    def _send_force_report_computed_task(self):
        report_computed_task = message.tasks.ReportComputedTask(
            task_to_compute = self.task_to_compute  # pylint: disable=no-member
        )
        force_report_computed_task = message.ForceReportComputedTask(
            report_computed_task = report_computed_task,
        )
        return self.client.post(
            reverse('core:send'),
            data                                = dump(
                force_report_computed_task,
                self.PROVIDER_PRIVATE_KEY,
                settings.CONCENT_PUBLIC_KEY
            ),
            content_type                        = 'application/octet-stream',
        )

    def _assert_stored_message_counter_increased(self, increased_by = 1):
        self.assertEqual(StoredMessage.objects.count(), self.stored_message_counter + increased_by)
        self.stored_message_counter += increased_by

    def _assert_stored_message_counter_not_increased(self):
        self.assertEqual(self.stored_message_counter, StoredMessage.objects.count())

    def _assert_client_count_is_equal(self, count):
        self.assertEqual(Client.objects.count(), count)

    def _add_signature_to_message(self, golem_message, priv_key):
        golem_message.sig = None
        golem_message = self._sign_message(
            golem_message,
            priv_key,
        )
        return golem_message.sig

    def _create_client_auth_message(self, client_priv_key, client_public_key):  # pylint: disable=no-self-use
        client_auth = message.concents.ClientAuthorization()
        client_auth.client_public_key = client_public_key
        return dump(client_auth, client_priv_key, settings.CONCENT_PUBLIC_KEY)

    def _create_client_auth_message_as_header(self, client_priv_key, client_public_key):  # pylint: disable=no-self-use
        return b64encode(
            self._create_client_auth_message(
                client_priv_key,
                client_public_key,
            )
        ).decode()

    def _create_provider_auth_message(self):
        return self._create_client_auth_message(self.PROVIDER_PRIVATE_KEY, self.PROVIDER_PUBLIC_KEY)

    def _create_diff_provider_auth_message(self):
        return self._create_client_auth_message(self.DIFFERENT_PROVIDER_PRIVATE_KEY, self.DIFFERENT_PROVIDER_PUBLIC_KEY)

    def _create_requestor_auth_message(self):
        return self._create_client_auth_message(self.REQUESTOR_PRIVATE_KEY, self.REQUESTOR_PUBLIC_KEY)

    def _create_diff_requestor_auth_message(self):
        return self._create_client_auth_message(self.DIFFERENT_REQUESTOR_PRIVATE_KEY, self.DIFFERENT_REQUESTOR_PUBLIC_KEY)

    def _create_test_ping_message(self):  # pylint: disable=no-self-use
        ping_message = message.Ping()
        return ping_message

    def _add_time_offset_to_date(self, base_time, offset):
        """
        :param base_time: string format
        :param offset: timestamp format
        :return: new time in a string format
        """
        return datetime.datetime.fromtimestamp(self._parse_iso_date_to_timestamp(base_time) + offset).strftime(
            '%Y-%m-%d %H:%M:%S'
        )

    def _create_payment_object(self, amount, closure_time):  # pylint: disable=no-self-use
        payment_item = mock.Mock()
        payment_item.amount         = amount
        payment_item.closure_time   = closure_time
        return payment_item

    def _get_list_of_batch_transactions(self, requestor_eth_address = None, provider_eth_address = None, payment_ts = None, current_time = None, transaction_type = None):  # pylint: disable=unused-argument
        current_time = get_current_utc_timestamp()
        item1 = self._create_payment_object(amount = 1000, closure_time = current_time - 4000)
        item2 = self._create_payment_object(amount = 2000, closure_time = current_time - 3000)
        item3 = self._create_payment_object(amount = 3000, closure_time = current_time - 2000)
        item4 = self._create_payment_object(amount = 4000, closure_time = current_time - 1000)
        return [item1, item2, item3, item4]

    def _get_list_of_force_transactions(self, requestor_eth_address = None, provider_eth_address = None, payment_ts = None, current_time = None, transaction_type = None):  # pylint: disable=unused-argument
        current_time = get_current_utc_timestamp()
        item1 = self._create_payment_object(amount = 1000, closure_time = current_time - 2000)
        item2 = self._create_payment_object(amount = 2000, closure_time = current_time - 1000)
        return [item1, item2]

    def _get_empty_list_of_transactions(self, requestor_eth_address = None, provider_eth_address = None, payment_ts = None, current_time = None, transaction_type = None):  # pylint: disable=no-self-use, unused-argument
        return []

    def _make_force_payment_to_provider(self, requestor_eth_address, provider_eth_address, value, payment_ts):  # pylint: disable=no-self-use, unused-argument
        return None

    def _get_number_of_eth_block(self):  # pylint: disable=no-self-use
        return 200000

    def _pass_rpc_synchronization(self, _rpc, _address, _tx_sign):  # pylint: disable=no-self-use
        return None

    def is_account_status_positive_true_mock(self, client_eth_address, pending_value):  # pylint: disable=unused-argument, no-self-use
        return True

    def _test_report_computed_task_in_database(self, report_computed_task):
        subtask = Subtask.objects.get(subtask_id = report_computed_task.subtask_id)
        stored_report_computed_task = message.Message.deserialize(subtask.report_computed_task.data.tobytes(), decrypt_func = None, check_time = False)
        self.assertEqual(stored_report_computed_task, report_computed_task)
