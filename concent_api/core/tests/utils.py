from base64 import b64encode
from typing import List
from typing import Optional
from typing import Union
import datetime
import functools
import mock

import dateutil.parser
from numpy import ndarray

from django.conf import settings
from django.shortcuts import reverse
from django.test import TestCase
from django.utils import timezone
from freezegun import freeze_time

from golem_messages         import dump
from golem_messages         import load
from golem_messages         import message
from golem_messages.factories.tasks import ComputeTaskDefFactory
from golem_messages.factories.tasks import ReportComputedTaskFactory
from golem_messages.factories.tasks import TaskToComputeFactory
from golem_messages.message.base import Message
from golem_messages.message.concents import ForcePayment
from golem_messages.message.concents import ForceReportComputedTask
from golem_messages.message.concents import ForceSubtaskResults
from golem_messages.message.concents import ForceSubtaskResultsResponse
from golem_messages.message.concents import SubtaskResultsVerify
from golem_messages.message.tasks import AckReportComputedTask
from golem_messages.message.tasks import RejectReportComputedTask
from golem_messages.message.tasks import TaskFailure
from golem_messages.message.tasks import CannotComputeTask
from golem_messages.message.tasks import ComputeTaskDef
from golem_messages.message.tasks import ReportComputedTask
from golem_messages.message.tasks import SubtaskResultsAccepted
from golem_messages.message.tasks import SubtaskResultsRejected
from golem_messages.message.tasks import TaskToCompute
from golem_messages.utils import encode_hex

from core.models            import Client
from core.models            import PendingResponse
from core.models            import StoredMessage
from core.models            import Subtask
from core.utils import calculate_additional_verification_call_time

from common.helpers          import sign_message
from common.helpers          import get_current_utc_timestamp
from common.helpers          import parse_timestamp_to_utc_datetime
from common.testing_helpers  import generate_ecc_key_pair
from common.testing_helpers  import generate_priv_and_pub_eth_account_key


def get_timestamp_string() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def parse_iso_date_to_timestamp(date_string) -> int:
    return int(dateutil.parser.parse(date_string).timestamp())


class ConcentIntegrationTestCase(TestCase):

    multi_db = True

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

    def _get_requestor_ethereum_hex_public_key(self):
        """ Returns requestor ethereum public key encoded. """
        return encode_hex(self.REQUESTOR_PUB_ETH_KEY)

    def _get_requestor_ethereum_hex_public_key_different(self):
        """ Returns requestor ethereum public key encoded. """
        return encode_hex(self.DIFFERENT_REQUESTOR_PUB_ETH_KEY)

    def _get_provider_ethereum_private_key(self):
        """ Returns provider ethereum private key """
        return self.PROVIDER_PRIV_ETH_KEY

    def _get_provider_ethereum_hex_public_key(self):
        """ Returns provider ethereum address """
        return encode_hex(self.PROVIDER_PUB_ETH_KEY)

    def _get_provider_ethereum_hex_public_key_different(self):
        """ Returns provider ethereum diffrent address """
        return encode_hex(self.DIFFERENT_PROVIDER_PUB_ETH_KEY)

    def _get_provider_hex_public_key(self):
        """ Returns provider hex public key """
        return encode_hex(self.PROVIDER_PUBLIC_KEY)

    def _get_requestor_hex_public_key(self):
        return encode_hex(self.REQUESTOR_PUBLIC_KEY)

    def _get_diffrent_provider_hex_public_key(self):
        return encode_hex(self.DIFFERENT_PROVIDER_PUBLIC_KEY)

    def _get_diffrent_requestor_hex_public_key(self):
        return encode_hex(self.DIFFERENT_REQUESTOR_PUBLIC_KEY)

    def _sign_message(self, golem_message, client_private_key = None):
        return sign_message(
            golem_message,
            self.REQUESTOR_PRIVATE_KEY if client_private_key is None else client_private_key,
        )

    def _get_serialized_force_get_task_result(
        self,
        report_computed_task: ReportComputedTask,
        timestamp: Union[str, datetime.datetime, None],
        requestor_private_key: Optional[bytes] = None,
    ) -> bytes:

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

    def _get_deserialized_report_computed_task(
        self,
        subtask_id: str = '2',
        task_id: str = '1',
        task_to_compute: Optional[TaskToCompute] = None,
        size: int = 1,
        package_hash: str = 'sha1:4452d71687b6bc2c9389c3349fdc17fbd73b833b',
        timestamp: Optional[str] = None,
        signer_private_key: Optional[bytes] = None,
        frames: Optional[List[int]] = None,
    ) -> ReportComputedTask:

        """ Returns ReportComputedTask deserialized. """
        with freeze_time(timestamp or get_timestamp_string()):
            report_computed_task = ReportComputedTaskFactory(
                task_to_compute=(
                    task_to_compute or self._get_deserialized_task_to_compute(
                        subtask_id=subtask_id,
                        task_id=task_id,
                        frames=frames if frames is not None else [1]
                    )
                ),
                package_hash=package_hash,
                size=size,
            )
        report_computed_task = self._sign_message(
            report_computed_task,
            signer_private_key if signer_private_key is not None else self.PROVIDER_PRIVATE_KEY,
        )
        return report_computed_task

    def _get_deserialized_task_to_compute(
        self,
        timestamp: Union[str, datetime.datetime, None] = None,
        deadline: Union[str, int, None] = None,
        task_id: str = '1',
        subtask_id: str = '2',
        compute_task_def: Optional[ComputeTaskDef] = None,
        requestor_id: Optional[bytes] = None,
        requestor_public_key: Optional[bytes] = None,
        requestor_ethereum_public_key: Optional[bytes] = None,
        provider_id: Optional[bytes] = None,
        provider_public_key: Optional[bytes] = None,
        provider_ethereum_public_key: Optional[bytes] = None,
        price: int = 0,
        package_hash: str = 'sha1:230fb0cad8c7ed29810a2183f0ec1d39c9df3f4a',
        signer_private_key: Optional[bytes] = None,
        size: int = 1,
        frames: Optional[List[int]] = None,
    ) -> TaskToCompute:

        """ Returns TaskToCompute deserialized. """
        compute_task_def = (
            compute_task_def if compute_task_def is not None else self._get_deserialized_compute_task_def(
                task_id=task_id,
                subtask_id=subtask_id,
                deadline=deadline,
                frames=frames if frames is not None else [1],
            )
        )
        assert isinstance(requestor_id, str) or requestor_id is None
        assert isinstance(requestor_public_key, str) or requestor_public_key is None
        assert isinstance(provider_id, str) or provider_id is None
        assert isinstance(provider_public_key, str) or provider_public_key is None
        assert isinstance(timestamp, (str, datetime.datetime)) or timestamp is None

        with freeze_time(timestamp or get_timestamp_string()):
            task_to_compute = TaskToComputeFactory(
                compute_task_def=compute_task_def,
                requestor_id=(
                    requestor_id if requestor_id is not None else self._get_requestor_hex_public_key()
                ),
                requestor_public_key            = (
                    requestor_public_key if requestor_public_key is not None else self._get_requestor_hex_public_key()
                ),
                requestor_ethereum_public_key   = (
                    requestor_ethereum_public_key if requestor_ethereum_public_key is not None else self._get_requestor_ethereum_hex_public_key()
                ),
                provider_id                     = (
                    provider_id if provider_id is not None else self._get_provider_hex_public_key()
                ),
                provider_public_key             = (
                    provider_public_key if provider_public_key is not None else self._get_provider_hex_public_key()
                ),
                provider_ethereum_public_key    = (
                    provider_ethereum_public_key if provider_ethereum_public_key is not None else self._get_provider_ethereum_hex_public_key()
                ),
                price=price,
                package_hash=package_hash,
                size=size,
            )
        task_to_compute = self._sign_message(
            task_to_compute,
            signer_private_key,
        )
        return task_to_compute

    def _get_deserialized_ack_report_computed_task(
        self,
        timestamp: Union[str, datetime.datetime, None] = None,
        deadline: Union[str, int, None] = None,
        subtask_id: str = '1',
        report_computed_task: Optional[ReportComputedTask] = None,
        task_to_compute: Optional[TaskToCompute] = None,
        signer_private_key: Optional[bytes] = None,
    )-> AckReportComputedTask:
        """ Returns AckReportComputedTask deserialized. """
        with freeze_time(timestamp or get_timestamp_string()):
            ack_report_computed_task = message.AckReportComputedTask(
                report_computed_task=(
                    report_computed_task if report_computed_task is not None else self._get_deserialized_report_computed_task(
                        task_to_compute=(
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
        if signer_private_key is not None:
            ack_report_computed_task = self._sign_message(
                ack_report_computed_task,
                signer_private_key,
            )
        return ack_report_computed_task

    def _get_serialized_ack_report_computed_task(
        self,
        ack_report_computed_task: AckReportComputedTask,
        timestamp: Union[str, datetime.datetime, None] = None,
        requestor_private_key: Optional[bytes] = None,
    ) -> bytes:
        with freeze_time(timestamp or get_timestamp_string()):
            return dump(
                ack_report_computed_task,
                requestor_private_key if requestor_private_key is not None else self.REQUESTOR_PRIVATE_KEY,
                settings.CONCENT_PUBLIC_KEY
            )

    def _test_204_response(self, response):
        self.assertEqual(response.status_code, 204)
        self.assertEqual(len(response.content), 0)

    def _test_400_response(self, response, error_message = None, error_code = None):
        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.json())
        if error_message is not None:
            self.assertIn(error_message, response.json()['error'])
            self.assertEqual(response.json()['error_code'], error_code.value)

    def _test_response(self, response, status, key, message_type=None, fields=None, nested_message_verifiable_by=None):
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

        if nested_message_verifiable_by is not None:
            assert isinstance(nested_message_verifiable_by, dict)
            for nested_message, public_key in nested_message_verifiable_by.items():
                nested_message = functools.reduce(getattr, nested_message.split('.'), message_from_concent)
                self.assertTrue(Message.verify_signature(nested_message, public_key))

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

        assert Client.objects.filter(public_key = provider_key).exists()  # pylint: disable=no-member
        assert Client.objects.filter(public_key = requestor_key).exists()  # pylint: disable=no-member

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

    def _test_last_stored_messages(self, expected_messages, task_id, subtask_id):
        assert isinstance(expected_messages, list)
        assert isinstance(task_id,           str)
        assert isinstance(subtask_id,        str)

        expected_message_types = [expected_message.TYPE for expected_message in expected_messages]

        for stored_message in StoredMessage.objects.order_by('-id')[:len(expected_message_types)]:
            self.assertIn(stored_message.type,                      expected_message_types)
            self.assertEqual(stored_message.task_id,                task_id)
            self.assertEqual(stored_message.subtask_id,             subtask_id)

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
            client__public_key=client_public_key_out_of_band,
        ):
            self.assertIn(pending_response.response_type,           expected_pending_responses_receive_out_of_band_types)
            self.assertEqual(pending_response.subtask.subtask_id,   subtask_id)
            self.assertEqual(pending_response.client.public_key,    client_public_key_out_of_band)

            expected_pending_responses_receive_out_of_band_types.remove(pending_response.response_type)

        assert expected_pending_responses_receive_out_of_band_types == []

    def _get_deserialized_force_subtask_results(
        self,
        timestamp: Union[str, datetime.datetime, None] = None,
        ack_report_computed_task: Optional[AckReportComputedTask] = None,
    ) -> ForceSubtaskResults:

        """ Returns ForceSubtaskResults deserialized. """
        with freeze_time(timestamp or get_timestamp_string()):
            force_subtask_results = message.concents.ForceSubtaskResults(
                ack_report_computed_task = (
                    ack_report_computed_task or
                    self._get_deserialized_ack_report_computed_task(
                        timestamp       = timestamp,
                        deadline        = (parse_iso_date_to_timestamp(timestamp) + 10),
                    )
                )
            )
        return force_subtask_results

    def _get_serialized_force_subtask_results(
        self,
        timestamp                   = None,
        ack_report_computed_task    = None,
        provider_private_key        = None,
    ) -> bytes:
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
        task_to_compute: TaskToCompute,
        timestamp: Union[str, datetime.datetime, None] = None,
        payment_ts: Optional[str] = None,
        signer_private_key: Optional[bytes] = None,
    ) -> SubtaskResultsAccepted:

        """ Return SubtaskResultsAccepted deserialized """
        with freeze_time(timestamp or get_timestamp_string()):
            subtask_results_accepted = SubtaskResultsAccepted(
                task_to_compute = task_to_compute,
                payment_ts     = (
                        parse_iso_date_to_timestamp(payment_ts) is not None else
                        parse_iso_date_to_timestamp(get_timestamp_string())
                )
            )
        subtask_results_accepted = self._sign_message(
            subtask_results_accepted,
            signer_private_key if signer_private_key is not None else self.REQUESTOR_PRIVATE_KEY,
        )
        return subtask_results_accepted

    def _get_serialized_subtask_results_accepted(
        self,
        timestamp                   = None,
        payment_ts                  = None,
        requestor_private_key       = None,
        task_to_compute             = None,
        subtask_results_accepted    = None
    ) -> bytes:
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
        reason: message.tasks.SubtaskResultsRejected.REASON,
        timestamp: Union[str, datetime.datetime, None] = None,
        report_computed_task: Optional[ReportComputedTask] = None,
        signer_private_key: Optional[bytes] = None,
    ) -> SubtaskResultsRejected:

        """ Return SubtaskResultsRejected deserialized """
        with freeze_time(timestamp or get_timestamp_string()):
            subtask_results_rejected = SubtaskResultsRejected(
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
        subtask_results_rejected = self._sign_message(
            subtask_results_rejected,
            signer_private_key if signer_private_key is not None else self.REQUESTOR_PRIVATE_KEY,
        )
        return subtask_results_rejected

    def _get_serialized_subtask_results_rejected(
        self,
        subtask_results_rejected: SubtaskResultsRejected,
        timestamp: Union[str, datetime.datetime, None] = None,
        requestor_private_key: Optional[bytes] = None,
    ) -> bytes:

        """ Return SubtaskResultsRejected serialized """
        with freeze_time(timestamp or get_timestamp_string()):
            return dump(
                subtask_results_rejected,
                requestor_private_key if requestor_private_key is not None else self.REQUESTOR_PRIVATE_KEY,
                settings.CONCENT_PUBLIC_KEY,
            )

    def _get_deserialized_compute_task_def(  # pylint: disable=no-self-use
        self,
        task_id: str = '1',
        subtask_id: str = '2',
        deadline: Union[str, int, None] = None,
        extra_data: Optional[dict] = None,
        short_description: str = 'path_root: /home/dariusz/Documents/tasks/resources, start_task: 6, end_task: 6...',
        working_directory: str = '.',
        performance: float = 829.7531773625524,
        docker_images: Optional[List[set]] = None,
        frames: Optional[List[int]] = None
    ) -> ComputeTaskDef:
        compute_task_def = ComputeTaskDefFactory(
            task_id=task_id,
            subtask_id=subtask_id,
            extra_data=extra_data,
            short_description=short_description,
            working_directory=working_directory,
            performance=performance,
        )
        if isinstance(deadline, int):
            compute_task_def['deadline'] = deadline
        elif isinstance(deadline, str):
            compute_task_def['deadline'] = parse_iso_date_to_timestamp(deadline)
        else:
            compute_task_def['deadline'] = parse_iso_date_to_timestamp(get_timestamp_string()) + 10

        if extra_data is None:
            compute_task_def['extra_data'] = {
                'end_task': 6,
                'frames': frames if frames is not None else [1],
                'outfilebasename': 'Heli-cycles(3)',
                'output_format': 'PNG',
                'path_root': '/home/dariusz/Documents/tasks/resources',
                'scene_file': '/golem/resources/scene-Helicopter-27-internal.blend',
                'script_src': '# This template is rendered by',
                'start_task': 6,
                'total_tasks': 8
            }
        if docker_images is None:
            compute_task_def['docker_images'] = [{'image_id': None, 'repository': 'golemfactory/blender', 'tag': '1.4'}]

        return compute_task_def

    def _get_deserialized_force_subtask_results_response(  # pylint: disable=no-self-use
        self,
        timestamp: Union[str, datetime.datetime, None] = None,
        subtask_results_accepted: Optional[SubtaskResultsAccepted] = None,
        subtask_results_rejected: Optional[SubtaskResultsRejected] = None,
    ) -> ForceSubtaskResultsResponse:
        with freeze_time(timestamp or get_timestamp_string()):
            force_subtask_results_response = message.concents.ForceSubtaskResultsResponse(
                subtask_results_accepted = subtask_results_accepted,
                subtask_results_rejected = subtask_results_rejected,
            )
            return force_subtask_results_response

    def _get_serialized_force_subtask_results_response(
        self,
        timestamp: Union[str, datetime.datetime, None] = None,
        subtask_results_accepted: Optional[SubtaskResultsAccepted] = None,
        subtask_results_rejected: Optional[SubtaskResultsRejected] = None,
        requestor_private_key: Optional[bytes] = None,
    ) -> bytes:
        with freeze_time(timestamp or get_timestamp_string()):
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

    def _get_deserialized_force_report_computed_task(  # pylint: disable=no-self-use
        self,
        report_computed_task: ReportComputedTask,
        timestamp: Union[str, datetime.datetime, None] = None,
    ) -> ForceReportComputedTask:
        with freeze_time(timestamp or get_timestamp_string()):
            return message.concents.ForceReportComputedTask(
                report_computed_task = report_computed_task,
            )

    def _get_serialized_force_report_computed_task(
        self,
        force_report_computed_task: ForceReportComputedTask,
        timestamp: Union[str, datetime.datetime, None] = None,
        provider_private_key: Optional[bytes] = None,
    ) -> bytes:
        with freeze_time(timestamp or get_timestamp_string()):
            return dump(
                force_report_computed_task,
                provider_private_key if provider_private_key is not None else self.PROVIDER_PRIVATE_KEY,
                settings.CONCENT_PUBLIC_KEY
            )

    def _get_deserialized_cannot_compute_task(
        self,
        task_to_compute: TaskToCompute,
        reason: message.tasks.SubtaskResultsRejected.REASON,
        timestamp: Union[str, datetime.datetime, None] = None,
    ) -> CannotComputeTask:
        with freeze_time(timestamp or get_timestamp_string()):
            cannot_compute_task = message.tasks.CannotComputeTask(
                task_to_compute = task_to_compute,
                reason          = reason,
            )
            return self._sign_message(cannot_compute_task, self.PROVIDER_PRIVATE_KEY)

    def _get_deserialized_task_failure(
        self,
        err: str,
        task_to_compute: TaskToCompute,
        timestamp: Union[str, datetime.datetime, None] = None,
    ) -> TaskFailure:
        with freeze_time(timestamp or get_timestamp_string()):
            task_failure = message.tasks.TaskFailure(
                err=err,
                task_to_compute=task_to_compute,
            )
            return self._sign_message(task_failure, self.PROVIDER_PRIVATE_KEY)

    def _get_deserialized_reject_report_computed_task(  # pylint: disable=no-self-use
        self,
        reason: message.tasks.SubtaskResultsRejected.REASON,
        task_to_compute: TaskToCompute,
        timestamp: Union[str, datetime.datetime, None] = None,
        cannot_compute_task: Optional[CannotComputeTask] = None,
        task_failure: Optional[TaskFailure] = None,
    )-> RejectReportComputedTask:
        with freeze_time(timestamp or get_timestamp_string()):
            return message.RejectReportComputedTask(
                cannot_compute_task = cannot_compute_task,
                attached_task_to_compute = task_to_compute,
                task_failure        = task_failure,
                reason              = reason,
            )

    def _get_serialized_reject_report_computed_task(
        self,
        reject_report_computed_task: RejectReportComputedTask,
        timestamp: Union[str, datetime.datetime, None] = None,
        requestor_private_key: Optional[bytes] = None,
    ) -> bytes:
        with freeze_time(timestamp or get_timestamp_string()):
            return dump(
                reject_report_computed_task,
                requestor_private_key if requestor_private_key is not None else self.REQUESTOR_PRIVATE_KEY,
                settings.CONCENT_PUBLIC_KEY
            )

    def _get_deserialized_force_payment(  # pylint: disable=no-self-use
        self,
        subtask_results_accepted_list: List[SubtaskResultsAccepted],
        timestamp: Union[str, datetime.datetime, None] = None,
    ) -> ForcePayment:
        with freeze_time(timestamp or get_timestamp_string()):
            force_payment = message.concents.ForcePayment(
                subtask_results_accepted_list = subtask_results_accepted_list
            )
            return force_payment

    def _get_serialized_force_payment(
        self,
        subtask_results_accepted_list: List[SubtaskResultsAccepted],
        timestamp: Union[str, datetime.datetime, None] = None,
        provider_private_key: Optional[bytes] = None,
    ) -> bytes:
        with freeze_time(timestamp or get_timestamp_string()):
            force_payment = self._get_deserialized_force_payment(
                timestamp                       = timestamp,
                subtask_results_accepted_list   = subtask_results_accepted_list,
            )
        return dump(
            force_payment,
            provider_private_key if provider_private_key is not None else self.PROVIDER_PRIVATE_KEY,
            settings.CONCENT_PUBLIC_KEY
        )

    def _get_deserialized_subtask_results_verify(  # pylint: disable=no-self-use
        self,
        subtask_results_rejected: SubtaskResultsRejected,
        timestamp: Union[str, datetime.datetime, None] = None,
    ) -> SubtaskResultsVerify:
        """ Return SubtaskResultsVerify deserialized """
        with freeze_time(timestamp or get_timestamp_string()):
            return message.concents.SubtaskResultsVerify(
                subtask_results_rejected=subtask_results_rejected
            )

    def _get_serialized_subtask_results_verify(
        self,
        subtask_results_verify: SubtaskResultsVerify,
        subtask_results_rejected: Optional[SubtaskResultsRejected] = None,
        timestamp: Union[str, datetime.datetime, None] = None,
        provider_private_key: Optional[bytes] = None,
    ) -> bytes:
        return dump(
            msg=(subtask_results_verify if subtask_results_verify is not None
                 else self._get_deserialized_subtask_results_verify(subtask_results_rejected, timestamp)),
            privkey=provider_private_key if provider_private_key is not None else self.PROVIDER_PRIVATE_KEY,
            pubkey=settings.CONCENT_PUBLIC_KEY,
        )

    def _store_golem_messages_in_database(
        self,
        message_type,
        timestamp,
        data,
        task_id,
    ):  # pylint: disable=no-self-use
        with freeze_time(timestamp or get_timestamp_string()):
            message_timestamp = datetime.datetime.now(timezone.utc)
            golem_message = StoredMessage(
                type        = message_type,
                timestamp   = message_timestamp,
                data        = data.serialize(),
                task_id     = task_id
            )

            golem_message.full_clean()
            golem_message.save()

        return golem_message

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

    def _add_time_offset_to_date(self, base_time, offset):  # pylint: disable=no-self-use
        """
        :param base_time: string format
        :param offset: timestamp format
        :return: new time in a string format
        """
        return datetime.datetime.fromtimestamp(parse_iso_date_to_timestamp(base_time) + offset).strftime(
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

    @staticmethod
    def _create_datetime_from_string(date_time_str):
        return datetime.datetime.strptime(date_time_str, "%Y-%m-%d %H:%M:%S")

    def _prepare_cv2_mock(self, desired_behaviour='image'):  # pylint: disable=no-self-use
        mocked_cv2 = mock.Mock()
        mocked_cv2.imread = mock.Mock()
        if desired_behaviour == 'image':
            mocked_cv2.imread.return_value = ndarray((1024, 768, 3))
        elif desired_behaviour == 'none':
            mocked_cv2.imread.return_value = None
        elif desired_behaviour == 'exception':
            mocked_cv2.imread.side_effect = MemoryError('error')
        return mocked_cv2

    def _get_verification_deadline_as_datetime(
        self,
        subtask_results_rejected_timestamp: int,
        task_to_compute: message.tasks.TaskToCompute,
    ) -> datetime.datetime:
        return parse_timestamp_to_utc_datetime(
            self._get_verification_deadline_as_timestamp(
                subtask_results_rejected_timestamp,
                task_to_compute,
            )
        )

    @staticmethod
    def _get_verification_deadline_as_timestamp(
        subtask_results_rejected_timestamp: int,
        task_to_compute: message.tasks.TaskToCompute,
    ) -> int:
        return calculate_additional_verification_call_time(
            subtask_results_rejected_timestamp,
            task_to_compute.compute_task_def['deadline'],
            task_to_compute.timestamp,
        )
