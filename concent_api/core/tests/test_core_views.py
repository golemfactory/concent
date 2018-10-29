import mock
from freezegun import freeze_time
from django.conf import settings
from django.http import HttpResponse
from django.http import JsonResponse
from django.test import override_settings
from django.urls import reverse

from golem_messages import message
from golem_messages import settings as golem_settings
from golem_messages.factories import tasks
from golem_messages.factories.tasks import ComputeTaskDefFactory
from golem_messages.factories.tasks import WantToComputeTaskFactory
from golem_messages.shortcuts import dump
from golem_messages.shortcuts import load

from common.constants import ErrorCode
from common.constants import ERROR_IN_GOLEM_MESSAGE
from common.helpers import get_current_utc_timestamp
from common.helpers import parse_timestamp_to_utc_datetime
from common.testing_helpers import generate_ecc_key_pair
from core.message_handlers import store_subtask
from core.models import Client
from core.models import StoredMessage
from core.models import PendingResponse
from core.models import Subtask
from core.tests.utils import ConcentIntegrationTestCase
from core.utils import hex_to_bytes_convert

(CONCENT_PRIVATE_KEY, CONCENT_PUBLIC_KEY) = generate_ecc_key_pair()


@override_settings(
    CONCENT_PRIVATE_KEY=CONCENT_PRIVATE_KEY,
    CONCENT_PUBLIC_KEY=CONCENT_PUBLIC_KEY,
    CONCENT_MESSAGING_TIME=3600,
)
class CoreViewSendTest(ConcentIntegrationTestCase):

    @freeze_time("2017-11-17 10:00:00")
    def setUp(self):
        super().setUp()
        self.stored_message_counter = 0
        self.message_timestamp = get_current_utc_timestamp()  # 1510912800
        self.compute_task_def = self._get_deserialized_compute_task_def(
            deadline=self.message_timestamp + settings.CONCENT_MESSAGING_TIME
        )
        self.task_to_compute = self._get_deserialized_task_to_compute(
            compute_task_def=self.compute_task_def,
        )
        self.report_computed_task = self._get_deserialized_report_computed_task(
            task_to_compute=self.task_to_compute
        )
        self.correct_golem_data = self._get_deserialized_force_report_computed_task(
            report_computed_task=self.report_computed_task
        )

        self.want_to_compute = WantToComputeTaskFactory(
            node_name=1,
            task_id=self._get_uuid(),
            perf_index=3,
            price=4,
            max_resource_size=5,
            max_memory_size=6,
            num_cores=7,
        )

        self.cannot_compute_task = message.CannotComputeTask(
            task_to_compute=self.task_to_compute
        )
        self.reject_report_computed_task = self._get_deserialized_reject_report_computed_task(
            task_to_compute=self.task_to_compute,
            reason=message.tasks.RejectReportComputedTask.REASON.SubtaskTimeLimitExceeded,
        )

    @freeze_time("2017-11-17 10:00:00")
    def test_send_should_accept_valid_message(self):
        assert StoredMessage.objects.count() == 0

        response = self.send_request(
            url='core:send',
            data=dump(
                self.correct_golem_data,
                self.PROVIDER_PRIVATE_KEY,
                CONCENT_PUBLIC_KEY),
        )
        self.assertEqual(response.status_code, 202)
        self._assert_stored_message_counter_increased(increased_by=3)
        self._test_last_stored_messages(
            expected_messages=[
                message.TaskToCompute,
                message.WantToComputeTask,
                message.ReportComputedTask,
            ],
            task_id=self.correct_golem_data.task_id,
            subtask_id=self.correct_golem_data.subtask_id,
        )

    @freeze_time("2017-11-17 10:00:00")
    def test_send_should_return_http_200_if_message_timeout(self):
        assert StoredMessage.objects.count() == 0

        task_to_compute = self._get_deserialized_task_to_compute(
            deadline=self.message_timestamp - 1
        )
        report_computed_task = self._get_deserialized_report_computed_task(
            task_to_compute=task_to_compute
        )
        correct_golem_data = self._get_deserialized_force_report_computed_task(
            report_computed_task=report_computed_task
        )

        response = self.send_request(
            url='core:send',
            data=dump(
                correct_golem_data,
                self.PROVIDER_PRIVATE_KEY,
                CONCENT_PUBLIC_KEY),
        )

        self.assertEqual(response.status_code, 200)
        response_message = load(
            response.content,
            self.PROVIDER_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY,
        )
        self.assertIsInstance(response_message, message.concents.ForceReportComputedTaskResponse)
        self.assertEqual(response_message.reason,
                         message.concents.ForceReportComputedTaskResponse.REASON.SubtaskTimeout)

    @freeze_time("2017-11-17 10:00:00")
    def test_send_should_accept_valid_message_with_non_numeric_task_id(self):
        assert StoredMessage.objects.count() == 0

        compute_task_def = self._get_deserialized_compute_task_def(
            deadline=self.message_timestamp
        )
        task_to_compute = self._get_deserialized_task_to_compute(
            compute_task_def=compute_task_def,
        )
        report_computed_task = self._get_deserialized_report_computed_task(
            task_to_compute=task_to_compute
        )
        correct_golem_data = self._get_deserialized_force_report_computed_task(
            report_computed_task=report_computed_task,
        )

        response = self.send_request(
            url='core:send',
            data=dump(
                correct_golem_data,
                self.PROVIDER_PRIVATE_KEY,
                CONCENT_PUBLIC_KEY),
        )

        self.assertEqual(response.status_code, 202)
        self._assert_stored_message_counter_increased(increased_by=3)
        self._test_last_stored_messages(
            expected_messages=[
                message.TaskToCompute,
                message.WantToComputeTask,
                message.ReportComputedTask,
            ],
            task_id=task_to_compute.task_id,
            subtask_id=task_to_compute.subtask_id,
        )

    @freeze_time("2017-11-17 10:00:00")
    def test_send_should_return_http_400_if_data_is_incorrect(self):
        compute_task_def = message.ComputeTaskDef()
        task_to_compute = message.TaskToCompute(
            compute_task_def=compute_task_def,
            requestor_public_key=self._get_encoded_requestor_public_key(),
            want_to_compute_task=WantToComputeTaskFactory(),
        )
        report_computed_task = message.tasks.ReportComputedTask(
            task_to_compute=task_to_compute
        )
        with freeze_time("2017-11-17 9:56:00"):
            force_report_computed_task = message.concents.ForceReportComputedTask(
                report_computed_task=report_computed_task
            )

        response = self.send_request(
            url='core:send',
            data=dump(
                force_report_computed_task,
                self.PROVIDER_PRIVATE_KEY,
                CONCENT_PUBLIC_KEY),
        )
        self._test_400_response(response)

        data = message.concents.ForceReportComputedTask()
        data.report_computed_task = message.tasks.ReportComputedTask()
        compute_task_def['deadline'] = self.message_timestamp - 3600
        data.report_computed_task.task_to_compute = message.TaskToCompute(compute_task_def=compute_task_def)

        response = self.send_request(
            url='core:send',
            data=dump(
                data,
                self.PROVIDER_PRIVATE_KEY,
                CONCENT_PUBLIC_KEY),
        )
        self._test_400_response(response)
        self.assertTrue(response.json()['error'].startswith('Error in Golem Message'))

    @freeze_time("2017-11-17 10:00:00")
    def test_send_should_return_http_400_if_task_id_already_use(self):

        response_202 = self.send_request(
            url='core:send',
            data=dump(
                self.correct_golem_data,
                self.PROVIDER_PRIVATE_KEY,
                CONCENT_PUBLIC_KEY,
            ),
        )

        self.assertIsInstance(response_202, HttpResponse)
        self.assertEqual(response_202.status_code, 202)
        self.correct_golem_data.encrypted = None
        self.correct_golem_data.sig = None
        response_400 = self.send_request(
            url='core:send',
            data=dump(
                self.correct_golem_data,
                self.PROVIDER_PRIVATE_KEY,
                CONCENT_PUBLIC_KEY,
            ),
        )

        self.assertIsInstance(response_400, JsonResponse)
        self._test_400_response(
            response_400,
            error_code=ErrorCode.SUBTASK_DUPLICATE_REQUEST
        )

    @freeze_time("2017-11-17 10:00:00")
    def test_send_should_return_http_400_if_get_invalid_type_of_message(self):

        assert isinstance(self.want_to_compute, message.Message)

        response_400 = self.send_request(
            url='core:send',
            data=dump(
                self.want_to_compute,
                self.PROVIDER_PRIVATE_KEY,
                CONCENT_PUBLIC_KEY
            ),
        )

        self._test_400_response(
            response_400,
            error_code=ErrorCode.MESSAGE_UNKNOWN
        )

    @freeze_time("2017-11-17 10:00:00")
    def test_send_should_return_http_400_if_task_to_compute_deadline_exceeded(self):
        compute_task_def = ComputeTaskDefFactory()
        compute_task_def['deadline'] = self.message_timestamp - 9000

        with freeze_time(parse_timestamp_to_utc_datetime(self.message_timestamp - 10000)):
            task_to_compute = self._get_deserialized_task_to_compute(
                compute_task_def=self.compute_task_def,
                provider_public_key=self._get_provider_hex_public_key(),
                requestor_public_key=self._get_requestor_hex_public_key(),
            )

        report_computed_task = message.ReportComputedTask(
            task_to_compute=task_to_compute
        )
        report_computed_task.sign_message(self.PROVIDER_PRIVATE_KEY)

        ack_report_computed_task = message.tasks.AckReportComputedTask(
            report_computed_task=report_computed_task
        )

        response_400 = self.send_request(
            url='core:send',
            data=dump(
                ack_report_computed_task,
                self.PROVIDER_PRIVATE_KEY,
                CONCENT_PUBLIC_KEY
            ),
        )

        self._test_400_response(
            response_400,
            error_code=ErrorCode.QUEUE_COMMUNICATION_NOT_STARTED
        )

    @freeze_time("2017-11-17 10:00:00")
    def test_send_reject_message_save_as_receive_out_of_band_status(self):
        assert StoredMessage.objects.count() == 0

        self.correct_golem_data.report_computed_task = self._get_deserialized_report_computed_task(
            task_to_compute=self.cannot_compute_task.task_to_compute  # pylint: disable=no-member
        )

        force_response = self.send_request(
            url='core:send',
            data=dump(
                self.correct_golem_data,
                self.PROVIDER_PRIVATE_KEY,
                CONCENT_PUBLIC_KEY),
        )

        self.assertEqual(force_response.status_code, 202)
        self._test_last_stored_messages(
            expected_messages=[
                message.TaskToCompute,
                message.WantToComputeTask,
                message.ReportComputedTask,
            ],
            task_id=self.correct_golem_data.report_computed_task.task_id,
            subtask_id=self.correct_golem_data.report_computed_task.subtask_id,
        )

        reject_response = self.send_request(
            url='core:send',
            data=dump(
                self.reject_report_computed_task,
                self.REQUESTOR_PRIVATE_KEY,
                CONCENT_PUBLIC_KEY
            ),
        )

        self.assertEqual(reject_response.status_code, 202)
        self._test_last_stored_messages(
            expected_messages=[
                message.tasks.RejectReportComputedTask,
            ],
            task_id=self.reject_report_computed_task.task_id,
            subtask_id=self.reject_report_computed_task.subtask_id,
        )

    def test_send_should_reject_message_when_timestamp_too_old(self):
        with freeze_time("2017-11-17 09:40:00"):
            ping = message.Ping()

        with freeze_time("2017-11-17 10:00:00"):
            timestamp = self._create_datetime_from_string("2017-11-17 09:40:00")
            assert parse_timestamp_to_utc_datetime(get_current_utc_timestamp()) - timestamp > golem_settings.MSG_TTL
            response = self.send_request(
                url='core:send',
                data=dump(
                    ping,
                    self.PROVIDER_PRIVATE_KEY,
                    CONCENT_PUBLIC_KEY
                ),
            )

        self._test_400_response(response)

    def test_send_should_reject_message_when_timestamp_too_far_in_future(self):
        with freeze_time("2017-11-17 10:10:00"):
            ping = message.Ping()

        with freeze_time("2017-11-17 10:00:00"):
            timestamp = self._create_datetime_from_string("2017-11-17 10:10:00")
            assert timestamp - parse_timestamp_to_utc_datetime(get_current_utc_timestamp()) > golem_settings.FUTURE_TIME_TOLERANCE
            response = self.send_request(
                url='core:send',
                data=dump(
                    ping,
                    self.PROVIDER_PRIVATE_KEY,
                    CONCENT_PUBLIC_KEY
                ),
            )

        self._test_400_response(response)

    @freeze_time("2017-11-17 10:00:00")
    def test_send_should_return_http_400_if_task_to_compute_deadline_is_not_an_integer(self):
        compute_task_def = ComputeTaskDefFactory()

        invalid_values = [
            -11,
            'a11b',
            {},
            [],
            (1, 2, 3),
            None,
        ]

        for deadline in invalid_values:
            StoredMessage.objects.all().delete()
            compute_task_def['deadline'] = deadline
            task_to_compute = tasks.TaskToComputeFactory(
                compute_task_def=compute_task_def,
                provider_public_key=self._get_provider_hex_public_key(),
                requestor_public_key=self._get_requestor_hex_public_key(),
            )

            serialized_task_to_compute = dump(
                task_to_compute,
                self.REQUESTOR_PRIVATE_KEY,
                self.PROVIDER_PUBLIC_KEY,
            )
            deserialized_task_to_compute = load(
                serialized_task_to_compute,
                self.PROVIDER_PRIVATE_KEY,
                self.REQUESTOR_PUBLIC_KEY,
                check_time=False,
            )

            with freeze_time("2017-11-17 10:00:00"):
                force_report_computed_task = message.concents.ForceReportComputedTask(
                    report_computed_task=message.tasks.ReportComputedTask(
                        task_to_compute=deserialized_task_to_compute
                    )
                )

                response_400 = self.send_request(
                    url='core:send',
                    data=dump(
                        force_report_computed_task,
                        self.PROVIDER_PRIVATE_KEY,
                        CONCENT_PUBLIC_KEY
                    ),
                )

            self._test_400_response(response_400)

    @freeze_time("2017-11-17 10:00:00")
    def test_send_should_return_http_202_if_task_to_compute_deadline_is_correct(self):
        compute_task_def = ComputeTaskDefFactory()

        valid_values = [
            11,
            True,
            0,
            False,
        ]
        for deadline in valid_values:
            StoredMessage.objects.all().delete()
            compute_task_def['deadline'] = deadline

            deserialized_task_to_compute = self._get_deserialized_task_to_compute(
                compute_task_def=compute_task_def,
            )

            force_report_computed_task = self._get_deserialized_force_report_computed_task(
                report_computed_task=self._get_deserialized_report_computed_task(
                    task_to_compute=deserialized_task_to_compute
                )
            )

            response_202 = self.send_request(
                url='core:send',
                data=dump(
                    force_report_computed_task,
                    self.PROVIDER_PRIVATE_KEY,
                    CONCENT_PUBLIC_KEY
                ),
            )

            self.assertIn(response_202.status_code, [200, 202])

    @freeze_time("2017-11-17 10:00:00")
    def test_send_task_to_compute_without_public_key_should_return_http_400(self):
        assert StoredMessage.objects.count() == 0

        setattr(self.task_to_compute, 'requestor_public_key', None)

        response = self._send_force_report_computed_task()

        self._test_400_response(
            response,
            error_message=ERROR_IN_GOLEM_MESSAGE
        )
        self._assert_stored_message_counter_not_increased()
        self._assert_client_count_is_equal(0)

    @freeze_time("2017-11-17 10:00:00")
    def test_send_task_to_compute_with_public_key_with_wrong_length_should_return_http_400(self):
        assert StoredMessage.objects.count() == 0

        setattr(self.task_to_compute, 'requestor_public_key', getattr(self.task_to_compute, 'requestor_public_key')[:-1])

        response = self._send_force_report_computed_task()

        self._test_400_response(
            response,
            error_message=ERROR_IN_GOLEM_MESSAGE,
        )
        self._assert_stored_message_counter_not_increased()
        self._assert_client_count_is_equal(0)

    def test_send_with_empty_data_should_return_http_400_error(self):
        response = self.send_request(
            url='core:send',
            data='',
        )

        self.assertEqual(response.status_code, 400)

    def test_send_should_return_http_400_if_task_to_compute_younger_than_report_computed(self):

        deserialized_task_to_compute = self._get_deserialized_task_to_compute(
            deadline=get_current_utc_timestamp() + (60 * 37),
        )
        with freeze_time("2017-11-17 10:00:00"):
            force_report_computed_task = self._get_deserialized_force_report_computed_task(
                report_computed_task=self._get_deserialized_report_computed_task(
                    subtask_id=deserialized_task_to_compute.subtask_id,
                    task_to_compute=deserialized_task_to_compute
                )
            )
            response = self.send_request(
                url='core:send',
                data=dump(
                    force_report_computed_task,
                    self.PROVIDER_PRIVATE_KEY,
                    CONCENT_PUBLIC_KEY
                ),
            )

        self._test_400_response(
            response,
            error_code=ErrorCode.MESSAGE_TIMESTAMP_TOO_OLD
        )


@override_settings(
    CONCENT_PRIVATE_KEY=CONCENT_PRIVATE_KEY,
    CONCENT_PUBLIC_KEY=CONCENT_PUBLIC_KEY,
    CONCENT_MESSAGING_TIME=3600,
)
class CoreViewReceiveTest(ConcentIntegrationTestCase):

    def setUp(self):
        with freeze_time("2017-11-17 10:00:00"):
            super().setUp()
            self.compute_task_def = ComputeTaskDefFactory()
            self.compute_task_def['deadline'] = get_current_utc_timestamp() + (60 * 37)
            self.want_to_compute_task = WantToComputeTaskFactory(
                node_name=1,
                task_id=self._get_uuid(),
                perf_index=3,
                price=4,
                max_resource_size=5,
                max_memory_size=6,
                num_cores=7,
            )
            self.task_to_compute = tasks.TaskToComputeFactory(
                compute_task_def=self.compute_task_def,
                want_to_compute_task=self.want_to_compute_task,
                provider_public_key=self._get_provider_hex_public_key(),
                requestor_public_key=self._get_requestor_hex_public_key(),
            )
            self.size = 58
            self.report_computed_task = message.tasks.ReportComputedTask(
                task_to_compute=self.task_to_compute,
                size=self.size
            )
            self.force_golem_data = message.concents.ForceReportComputedTask(
                report_computed_task=self.report_computed_task,
            )

    @freeze_time("2017-11-17 10:00:00")
    def test_receive_should_accept_valid_message(self):
        message_timestamp = parse_timestamp_to_utc_datetime(get_current_utc_timestamp())
        new_message = StoredMessage(
            type=self.force_golem_data.report_computed_task.header.type_,
            timestamp=message_timestamp,
            data=self.force_golem_data.report_computed_task.serialize(),
            task_id=self.compute_task_def['task_id'],  # pylint: disable=no-member
            subtask_id=self.compute_task_def['subtask_id'],  # pylint: disable=no-member
            protocol_version=settings.GOLEM_MESSAGES_VERSION,
        )
        new_message.full_clean()
        new_message.save()

        client_provider = Client(
            public_key_bytes=self.PROVIDER_PUBLIC_KEY
        )
        client_provider.full_clean()
        client_provider.save()

        client_requestor = Client(
            public_key_bytes=self.REQUESTOR_PUBLIC_KEY
        )
        client_requestor.full_clean()
        client_requestor.save()

        want_to_compute_message = StoredMessage(
            type=self.want_to_compute_task.header.type_,
            timestamp=message_timestamp,
            data=self.want_to_compute_task.serialize(),
            task_id=self.compute_task_def['task_id'],  # pylint: disable=no-member
            subtask_id=self.compute_task_def['subtask_id'],  # pylint: disable=no-member
            protocol_version=settings.GOLEM_MESSAGES_VERSION,
        )
        want_to_compute_message.full_clean()
        want_to_compute_message.save()

        task_to_compute_message = StoredMessage(
            type=self.task_to_compute.header.type_,
            timestamp=message_timestamp,
            data=self.task_to_compute.serialize(),
            task_id=self.compute_task_def['task_id'],  # pylint: disable=no-member
            subtask_id=self.compute_task_def['subtask_id'],  # pylint: disable=no-member
            protocol_version=settings.GOLEM_MESSAGES_VERSION,
        )
        task_to_compute_message.full_clean()
        task_to_compute_message.save()

        subtask = Subtask(
            task_id                 = self.compute_task_def['task_id'],
            subtask_id              = self.compute_task_def['subtask_id'],
            task_to_compute         = task_to_compute_message,
            want_to_compute_task=want_to_compute_message,
            report_computed_task    = new_message,
            state                   = Subtask.SubtaskState.REPORTED.name,  # pylint: disable=no-member
            provider                = client_provider,
            requestor               = client_requestor,
            result_package_size=self.size,
            computation_deadline=parse_timestamp_to_utc_datetime(self.compute_task_def['deadline'])
        )
        subtask.full_clean()
        subtask.save()

        new_message_inbox = PendingResponse(
            response_type=PendingResponse.ResponseType.ForceReportComputedTask.name,  # pylint: disable=no-member
            client=client_requestor,
            queue=PendingResponse.Queue.Receive.name,  # pylint: disable=no-member
            subtask=subtask,
        )
        new_message_inbox.full_clean()
        new_message_inbox.save()

        response = self.send_request(
            url='core:receive',
            data=self._create_client_auth_message(self.REQUESTOR_PRIVATE_KEY, self.REQUESTOR_PUBLIC_KEY),
        )
        decoded_response = load(
            response.content,
            self.REQUESTOR_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(new_message.task_id,
                         decoded_response.report_computed_task.task_to_compute.compute_task_def['task_id'])
        self.assertEqual(new_message.subtask_id,
                         decoded_response.report_computed_task.task_to_compute.compute_task_def['subtask_id'])

    @freeze_time("2017-11-17 10:00:00")
    def test_receive_return_http_204_if_no_messages_in_database(self):
        response = self.send_request(
            url='core:receive',
            data=self._create_client_auth_message(self.REQUESTOR_PRIVATE_KEY, self.REQUESTOR_PUBLIC_KEY),
        )

        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content.decode(), '')

    def test_receive_should_return_first_messages_in_order_they_were_added_to_queue_if_the_receive_queue_contains_only_force_report_and_its_past_deadline(self):
        message_timestamp = parse_timestamp_to_utc_datetime(get_current_utc_timestamp())
        new_message = StoredMessage(
            type=self.force_golem_data.report_computed_task.header.type_,
            timestamp=message_timestamp,
            data=self.force_golem_data.report_computed_task.serialize(),
            task_id=self.compute_task_def['task_id'],  # pylint: disable=no-member
            subtask_id=self.compute_task_def['subtask_id'],  # pylint: disable=no-member
            protocol_version=settings.GOLEM_MESSAGES_VERSION,
        )
        new_message.full_clean()
        new_message.save()

        want_to_compute_message = StoredMessage(
            type=self.want_to_compute_task.header.type_,
            timestamp=message_timestamp,
            data=self.want_to_compute_task.serialize(),
            task_id=self.compute_task_def['task_id'],  # pylint: disable=no-member
            subtask_id=self.compute_task_def['subtask_id'],  # pylint: disable=no-member
            protocol_version=settings.GOLEM_MESSAGES_VERSION,
        )
        want_to_compute_message.full_clean()
        want_to_compute_message.save()

        task_to_compute_message = StoredMessage(
            type=self.task_to_compute.header.type_,
            timestamp=message_timestamp,
            data=self.task_to_compute.serialize(),
            task_id=self.compute_task_def['task_id'],  # pylint: disable=no-member
            subtask_id=self.compute_task_def['subtask_id'],  # pylint: disable=no-member
            protocol_version=settings.GOLEM_MESSAGES_VERSION,
        )
        task_to_compute_message.full_clean()
        task_to_compute_message.save()

        ack_report_computed_task = message.tasks.AckReportComputedTask(
            report_computed_task=self.report_computed_task
        )

        stored_ack_report_computed_task = StoredMessage(
            type=ack_report_computed_task.header.type_,
            timestamp=message_timestamp,
            data=ack_report_computed_task.serialize(),
            task_id=self.compute_task_def['task_id'],  # pylint: disable=no-member
            subtask_id=self.compute_task_def['subtask_id'],  # pylint: disable=no-member
            protocol_version=settings.GOLEM_MESSAGES_VERSION,
        )
        stored_ack_report_computed_task.full_clean()
        stored_ack_report_computed_task.save()

        client_provider = Client(
            public_key_bytes=self.PROVIDER_PUBLIC_KEY
        )
        client_provider.full_clean()
        client_provider.save()

        client_requestor = Client(
            public_key_bytes=self.REQUESTOR_PUBLIC_KEY
        )
        client_requestor.full_clean()
        client_requestor.save()

        subtask = Subtask(
            task_id                  = self.compute_task_def['task_id'],
            subtask_id               = self.compute_task_def['subtask_id'],
            report_computed_task     = new_message,
            task_to_compute          = task_to_compute_message,
            want_to_compute_task=want_to_compute_message,
            ack_report_computed_task = stored_ack_report_computed_task,
            state                    = Subtask.SubtaskState.REPORTED.name,  # pylint: disable=no-member
            provider                 = client_provider,
            requestor                = client_requestor,
            result_package_size=self.size,
            computation_deadline=parse_timestamp_to_utc_datetime(self.compute_task_def['deadline'])
        )
        subtask.full_clean()
        subtask.save()

        new_message_inbox = PendingResponse(
            response_type=PendingResponse.ResponseType.ForceReportComputedTask.name,  # pylint: disable=no-member
            client=client_requestor,
            queue=PendingResponse.Queue.Receive.name,  # pylint: disable=no-member
            subtask=subtask,
        )
        new_message_inbox.full_clean()
        new_message_inbox.save()

        new_message_inbox_out_of_band = PendingResponse(
            response_type=PendingResponse.ResponseType.VerdictReportComputedTask.name,  # pylint: disable=no-member
            client=client_requestor,
            queue=PendingResponse.Queue.ReceiveOutOfBand.name,  # pylint: disable=no-member
            subtask=subtask,
        )
        new_message_inbox_out_of_band.full_clean()
        new_message_inbox_out_of_band.save()

        with freeze_time("2017-11-17 12:00:00"):
            response = self.send_request(
                url='core:receive',
                data=self._create_client_auth_message(self.REQUESTOR_PRIVATE_KEY, self.REQUESTOR_PUBLIC_KEY),
            )

        decoded_message = load(
            response.content,
            self.REQUESTOR_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY,
            check_time=False,
        )

        self.assertIsInstance(decoded_message, message.concents.ForceReportComputedTask)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(decoded_message.timestamp, self._create_timestamp_from_string("2017-11-17 12:00:00"))
        self.assertEqual(decoded_message.report_computed_task.task_to_compute.compute_task_def,
                         self.task_to_compute.compute_task_def)  # pylint: disable=no-member
        self.assertEqual(decoded_message.report_computed_task.task_to_compute.sig, self.task_to_compute.sig)

        with freeze_time("2017-11-17 12:00:00"):
            response = self.send_request(
                url='core:receive',
                data=self._create_client_auth_message(self.REQUESTOR_PRIVATE_KEY, self.REQUESTOR_PUBLIC_KEY),
            )

        decoded_message = load(
            response.content,
            self.REQUESTOR_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY,
            check_time=False,
        )

        self.assertIsInstance(decoded_message, message.concents.VerdictReportComputedTask)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(decoded_message.timestamp, self._create_timestamp_from_string("2017-11-17 12:00:00"))
        self.assertEqual(decoded_message.ack_report_computed_task.report_computed_task.task_to_compute.compute_task_def,
                         self.task_to_compute.compute_task_def)  # pylint: disable=no-member
        self.assertEqual(decoded_message.ack_report_computed_task.report_computed_task.task_to_compute.sig,
                         self.task_to_compute.sig)


@override_settings(
    CONCENT_PRIVATE_KEY=CONCENT_PRIVATE_KEY,
    CONCENT_PUBLIC_KEY=CONCENT_PUBLIC_KEY,
    CONCENT_MESSAGING_TIME=3600,
)
class CoreViewReceiveOutOfBandTest(ConcentIntegrationTestCase):

    def setUp(self):
        super().setUp()
        self.compute_task_def = ComputeTaskDefFactory()
        self.compute_task_def['deadline'] = get_current_utc_timestamp() - 60
        self.want_to_compute_task = WantToComputeTaskFactory(
            node_name=1,
            task_id=self._get_uuid(),
            perf_index=3,
            price=4,
            max_resource_size=5,
            max_memory_size=6,
            num_cores=7,
        )
        self.task_to_compute = tasks.TaskToComputeFactory(
            compute_task_def=self.compute_task_def,
            want_to_compute_task=self.want_to_compute_task,
            provider_public_key=self._get_provider_hex_public_key(),
            requestor_public_key=self._get_requestor_hex_public_key(),
        )
        self.size = 58

        with freeze_time("2017-11-17 10:00:00"):
            self.report_computed_task = message.tasks.ReportComputedTask(
                task_to_compute=self.task_to_compute,
                size=self.size
            )
            self.force_golem_data = message.concents.ForceReportComputedTask(
                report_computed_task=self.report_computed_task
            )
        message_timestamp = parse_timestamp_to_utc_datetime(get_current_utc_timestamp())
        new_message = StoredMessage(
            type=self.force_golem_data.report_computed_task.header.type_,
            timestamp=message_timestamp,
            data=self.force_golem_data.report_computed_task.serialize(),
            task_id=self.compute_task_def['task_id'],  # pylint: disable=no-member
            subtask_id=self.compute_task_def['subtask_id'],  # pylint: disable=no-member
            protocol_version=settings.GOLEM_MESSAGES_VERSION,
        )
        new_message.full_clean()
        new_message.save()

        want_to_compute_message = StoredMessage(
            type=self.want_to_compute_task.header.type_,
            timestamp=message_timestamp,
            data=self.want_to_compute_task.serialize(),
            task_id=self.compute_task_def['task_id'],  # pylint: disable=no-member
            subtask_id=self.compute_task_def['subtask_id'],  # pylint: disable=no-member
            protocol_version=settings.GOLEM_MESSAGES_VERSION,
        )
        want_to_compute_message.full_clean()
        want_to_compute_message.save()

        task_to_compute_message = StoredMessage(
            type=self.task_to_compute.header.type_,
            timestamp=message_timestamp,
            data=self.task_to_compute.serialize(),
            task_id=self.compute_task_def['task_id'],  # pylint: disable=no-member
            subtask_id=self.compute_task_def['subtask_id'],  # pylint: disable=no-member
            protocol_version=settings.GOLEM_MESSAGES_VERSION,
        )
        task_to_compute_message.full_clean()
        task_to_compute_message.save()

        ack_report_computed_task = message.tasks.AckReportComputedTask(
            report_computed_task=self.report_computed_task
        )

        stored_ack_report_computed_task = StoredMessage(
            type=ack_report_computed_task.header.type_,
            timestamp=message_timestamp,
            data=ack_report_computed_task.serialize(),
            task_id=self.compute_task_def['task_id'],  # pylint: disable=no-member
            subtask_id=self.compute_task_def['subtask_id'],  # pylint: disable=no-member
            protocol_version=settings.GOLEM_MESSAGES_VERSION,
        )
        stored_ack_report_computed_task.full_clean()
        stored_ack_report_computed_task.save()

        client_provider = Client(
            public_key_bytes=self.PROVIDER_PUBLIC_KEY
        )
        client_provider.full_clean()
        client_provider.save()

        client_requestor = Client(
            public_key_bytes=self.REQUESTOR_PUBLIC_KEY
        )
        client_requestor.full_clean()
        client_requestor.save()

        subtask = Subtask(
            task_id                  = self.compute_task_def['task_id'],
            subtask_id               = self.compute_task_def['subtask_id'],
            report_computed_task     = new_message,
            task_to_compute          = task_to_compute_message,
            want_to_compute_task=want_to_compute_message,
            ack_report_computed_task = stored_ack_report_computed_task,
            state                    = Subtask.SubtaskState.REPORTED.name,  # pylint: disable=no-member
            provider                 = client_provider,
            requestor                = client_requestor,
            result_package_size=self.size,
            computation_deadline=parse_timestamp_to_utc_datetime(self.compute_task_def['deadline'])
        )
        subtask.full_clean()
        subtask.save()

        new_message_inbox = PendingResponse(
            response_type=PendingResponse.ResponseType.ForceReportComputedTask.name,  # pylint: disable=no-member
            client=client_requestor,
            queue=PendingResponse.Queue.ReceiveOutOfBand.name,  # pylint: disable=no-member
            subtask=subtask,
        )
        new_message_inbox.full_clean()
        new_message_inbox.save()

    @freeze_time("2017-11-17 11:40:00")
    def test_view_receive_out_of_band_should_accept_valid_message(self):
        response = self.send_request(
            url='core:receive',
            data=self._create_client_auth_message(self.REQUESTOR_PRIVATE_KEY, self.REQUESTOR_PUBLIC_KEY),
        )
        self.assertEqual(response.status_code, 200)

    @freeze_time("2017-11-17 9:20:00")
    def test_view_receive_out_of_band_return_http_204_if_no_messages_in_database(self):
        response = self.send_request(
            url='core:receive',
            data=self._create_client_auth_message(self.DIFFERENT_REQUESTOR_PRIVATE_KEY,
                                                  self.DIFFERENT_REQUESTOR_PUBLIC_KEY),
        )
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content.decode(), '')


@override_settings(
    CONCENT_PRIVATE_KEY=CONCENT_PRIVATE_KEY,
    CONCENT_PUBLIC_KEY=CONCENT_PUBLIC_KEY,
    CONCENT_MESSAGING_TIME=3600,
)
class ConcentProtocolVersionTest(ConcentIntegrationTestCase):

    def setUp(self):
        super().setUp()

        self.compute_task_def = self._get_deserialized_compute_task_def(
            deadline=get_current_utc_timestamp() + 100
        )

        self.task_to_compute = self._get_deserialized_task_to_compute(
            timestamp=parse_timestamp_to_utc_datetime(get_current_utc_timestamp()),
            compute_task_def=self.compute_task_def,
        )

        self.report_computed_task = self._get_deserialized_report_computed_task(
            task_to_compute=self.task_to_compute,
        )

        self.force_report_computed_task = self._get_deserialized_force_report_computed_task(
            report_computed_task=self.report_computed_task
        )

        self.reject_report_computed_task = self._get_deserialized_reject_report_computed_task(
            reason=message.tasks.RejectReportComputedTask.REASON.SubtaskTimeLimitExceeded,
            task_to_compute=self.task_to_compute,
        )

        self.force_get_task_result = self._get_deserialized_force_subtask_results(
            timestamp=parse_timestamp_to_utc_datetime(get_current_utc_timestamp()),
            task_to_compute=self.task_to_compute,
        )

        self.provider_public_key = hex_to_bytes_convert(self.task_to_compute.provider_public_key)
        self.requestor_public_key = hex_to_bytes_convert(self.task_to_compute.requestor_public_key)

    @override_settings(GOLEM_MESSAGES_VERSION='2.15.0')
    def test_that_concent_should_refuse_request_with_incompatible_protocol_version(self):
        with mock.patch('core.utils.log') as log_mock:
            response = self.send_request(
                url='core:send',
                data=dump(
                    self.force_report_computed_task,
                    self.PROVIDER_PRIVATE_KEY,
                    CONCENT_PUBLIC_KEY),
                golem_messages_version='1.12.0'
            )
        self._test_response(
            response,
            status=200,
            key=self.PROVIDER_PRIVATE_KEY,
            message_type=message.concents.ServiceRefused,
            fields={
                'reason': message.concents.ServiceRefused.REASON.InvalidRequest,
            }
        )
        self.assertIn('Wrong version of golem messages. Clients version is 1.12.0, Concent version is 2.15.0', str(log_mock.call_args))

    def test_that_concent_should_accept_request_without_protocol_version(self):
        response = self.client.post(
            reverse('core:send'),
            data=dump(
                self.force_report_computed_task,
                self.PROVIDER_PRIVATE_KEY,
                CONCENT_PUBLIC_KEY),
            content_type='application/octet-stream',
        )
        self._test_response(
            response,
            status=202,
            key=self.PROVIDER_PRIVATE_KEY,

        )

    def test_that_send_should_refuse_request_if_all_stored_messages_have_incompatible_protocol_version(self):
        with override_settings(GOLEM_MESSAGES_VERSION='1.11.0'):
            store_subtask(
                task_id=self.task_to_compute.compute_task_def['task_id'],
                subtask_id=self.task_to_compute.compute_task_def['subtask_id'],
                provider_public_key=self.provider_public_key,
                requestor_public_key=self.requestor_public_key,
                state=Subtask.SubtaskState.FORCING_REPORT,
                next_deadline=int(self.task_to_compute.compute_task_def['deadline']) + settings.CONCENT_MESSAGING_TIME,
                task_to_compute=self.task_to_compute,
                report_computed_task=self.report_computed_task,
            )
        with mock.patch('core.utils.log') as log_not_called_mock, \
                mock.patch('core.subtask_helpers.log') as log_called_mock:
            response = self.send_request(
                url='core:send',
                data=dump(
                    self.force_report_computed_task,
                    self.PROVIDER_PRIVATE_KEY,
                    CONCENT_PUBLIC_KEY),
            )
        self._test_response(
            response,
            status=200,
            key=self.PROVIDER_PRIVATE_KEY,
            message_type=message.concents.ServiceRefused,
            fields={
                'reason': message.concents.ServiceRefused.REASON.InvalidRequest,
            }
        )

        log_called_mock.assert_called()
        log_not_called_mock.assert_not_called()

        self.assertIn(f'Version stored in database is 1.11.0, Concent version is {settings.GOLEM_MESSAGES_VERSION}', str(log_called_mock.call_args))

    def test_that_receive_should_refuse_request_if_stored_messages_in_database_have_incompatible_protocol_version(self):
        """
        This case may happen, if client sends a request to core:send and in next step sends request to core:receive
        using different protocol version. The client is always required to stay on the same protocol version while
        communicating about the same subtask.
        """
        response = self.send_request(
            url='core:send',
            data=dump(
                self.force_report_computed_task,
                self.PROVIDER_PRIVATE_KEY,
                CONCENT_PUBLIC_KEY),
        )
        self._test_response(
            response,
            status=202,
            key=self.PROVIDER_PRIVATE_KEY,
        )

        response1 = self.send_request(
            url='core:send',
            data=dump(
                self.reject_report_computed_task,
                self.REQUESTOR_PRIVATE_KEY,
                CONCENT_PUBLIC_KEY),
        )
        self._test_response(
            response1,
            status=202,
            key=self.REQUESTOR_PRIVATE_KEY,
        )

        with override_settings(GOLEM_MESSAGES_VERSION='1.11.0'):
            response2 = self.send_request(
                url='core:receive',
                data=self._create_client_auth_message(self.PROVIDER_PRIVATE_KEY, self.PROVIDER_PUBLIC_KEY),
                golem_messages_version='1.11.0'
            )
            self._test_response(
                response2,
                status=200,
                key=self.PROVIDER_PRIVATE_KEY,
                message_type=message.concents.ServiceRefused,
                fields={
                    'reason': message.concents.ServiceRefused.REASON.InvalidRequest,
                }
            )
