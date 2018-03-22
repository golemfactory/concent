import datetime
from base64                         import b64encode

from freezegun                      import freeze_time
import dateutil.parser
from django.test                    import override_settings
from django.test                    import TestCase
from django.urls                    import reverse
from django.http                    import HttpResponse
from django.http                    import JsonResponse
from django.utils                   import timezone

from golem_messages                 import settings
from golem_messages.shortcuts       import dump
from golem_messages.shortcuts       import load
from golem_messages                 import message
from golem_messages.message         import Message as GolemMessage

from core.models                    import Client
from core.models                    import StoredMessage
from core.models                    import PendingResponse
from core.tests.utils               import ConcentIntegrationTestCase
from core.models                    import Subtask
from utils.helpers                  import get_current_utc_timestamp
from utils.testing_helpers          import generate_ecc_key_pair


(CONCENT_PRIVATE_KEY,   CONCENT_PUBLIC_KEY)   = generate_ecc_key_pair()
(PROVIDER_PRIVATE_KEY,  PROVIDER_PUBLIC_KEY)  = generate_ecc_key_pair()
(REQUESTOR_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY) = generate_ecc_key_pair()
(DIFFERENT_PRIVATE_KEY, DIFFERENT_PUBLIC_KEY) = generate_ecc_key_pair()


@override_settings(
    CONCENT_PRIVATE_KEY    = CONCENT_PRIVATE_KEY,
    CONCENT_PUBLIC_KEY     = CONCENT_PUBLIC_KEY,
    CONCENT_MESSAGING_TIME = 3600,
)
class CoreViewSendTest(ConcentIntegrationTestCase):

    @freeze_time("2017-11-17 10:00:00")
    def setUp(self):
        super().setUp()
        self.stored_message_counter         = 0
        self.message_timestamp              = get_current_utc_timestamp()  # 1510912800
        self.compute_task_def               = message.ComputeTaskDef()
        self.compute_task_def['task_id']    = '8'
        self.compute_task_def['subtask_id'] = '8'
        self.compute_task_def['deadline']   = self.message_timestamp
        self.task_to_compute                = message.TaskToCompute(
            compute_task_def     = self.compute_task_def,
            provider_public_key  = self.PROVIDER_PUBLIC_KEY,
            requestor_public_key = self.REQUESTOR_PUBLIC_KEY,
        )

        self.correct_golem_data                                         = message.ForceReportComputedTask()
        self.correct_golem_data.report_computed_task                    = message.tasks.ReportComputedTask()
        self.correct_golem_data.report_computed_task.task_to_compute    = self.task_to_compute
        self.want_to_compute = message.WantToComputeTask(
            node_name           = 1,
            task_id             = 2,
            perf_index          = 3,
            price               = 4,
            max_resource_size   = 5,
            max_memory_size     = 6,
            num_cores           = 7,
        )

        self.task_to_compute_for_cannot_compute_message = message.TaskToCompute(
            provider_public_key  = self.PROVIDER_PUBLIC_KEY,
            requestor_public_key = self.REQUESTOR_PUBLIC_KEY,
        )

        self.cannot_compute_task = message.CannotComputeTask()
        self.cannot_compute_task.task_to_compute = message.TaskToCompute(
            provider_public_key  = self.PROVIDER_PUBLIC_KEY,
            requestor_public_key = self.REQUESTOR_PUBLIC_KEY,
        )

        self.cannot_compute_task.task_to_compute.compute_task_def               = message.ComputeTaskDef()
        self.cannot_compute_task.task_to_compute.compute_task_def['deadline']   = self.message_timestamp + 600
        self.cannot_compute_task.task_to_compute.compute_task_def['task_id']    = '8'
        self.cannot_compute_task.task_to_compute.compute_task_def['subtask_id'] = '8'

        self.reject_report_computed_task = message.RejectReportComputedTask()

        self.reject_report_computed_task.reason                 = message.RejectReportComputedTask.REASON.TaskTimeLimitExceeded
        self.reject_report_computed_task.cannot_compute_task    = self.cannot_compute_task

    @freeze_time("2017-11-17 10:00:00")
    def test_send_should_accept_valid_message(self):
        assert StoredMessage.objects.count() == 0

        response = self.client.post(
            reverse('core:send'),
            data = dump(
                self.correct_golem_data,
                PROVIDER_PRIVATE_KEY,
                CONCENT_PUBLIC_KEY),
            content_type                        = 'application/octet-stream',
            HTTP_CONCENT_CLIENT_PUBLIC_KEY      = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
        )

        self.assertEqual(response.status_code,                   202)
        self._assert_stored_message_counter_increased(increased_by = 2)
        self._test_last_stored_messages(
            expected_messages = [
                message.TaskToCompute,
                message.ReportComputedTask,
            ],
            task_id         = '8',
            subtask_id      = '8',
            timestamp       = "2017-11-17 10:00:00"
        )

    @freeze_time("2017-11-17 10:00:00")
    def test_send_should_return_http_200_if_message_timeout(self):
        assert StoredMessage.objects.count() == 0

        task_to_compute = self.task_to_compute
        task_to_compute.compute_task_def['deadline'] = self.message_timestamp - 1   # pylint: disable=no-member
        report_computed_task = message.tasks.ReportComputedTask(
            task_to_compute = task_to_compute
        )
        correct_golem_data = message.ForceReportComputedTask(
            report_computed_task = report_computed_task)

        response = self.client.post(
            reverse('core:send'),
            data = dump(
                correct_golem_data,
                PROVIDER_PRIVATE_KEY,
                CONCENT_PUBLIC_KEY
            ),
            content_type                        = 'application/octet-stream',
            HTTP_CONCENT_CLIENT_PUBLIC_KEY      = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
        )

        self.assertEqual(response.status_code, 200)
        response_message = load(
            response.content,
            PROVIDER_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY,
        )
        self.assertIsInstance(response_message, GolemMessage)

    @freeze_time("2017-11-17 10:00:00")
    def test_send_should_accept_valid_message_with_non_numeric_task_id(self):
        assert StoredMessage.objects.count() == 0

        compute_task_def = message.ComputeTaskDef()
        compute_task_def['task_id']     = 'ABC00XYZ'
        compute_task_def['subtask_id']  = 'ABC00XYZ'
        compute_task_def['deadline']    = self.message_timestamp
        task_to_compute                 = message.TaskToCompute(
            compute_task_def     = compute_task_def,
            provider_public_key  = PROVIDER_PUBLIC_KEY,
            requestor_public_key = REQUESTOR_PUBLIC_KEY,
        )

        report_computed_task = message.tasks.ReportComputedTask(
            task_to_compute = task_to_compute
        )

        correct_golem_data = message.ForceReportComputedTask(
            report_computed_task = report_computed_task,
        )

        response = self.client.post(
            reverse('core:send'),
            data = dump(
                correct_golem_data,
                PROVIDER_PRIVATE_KEY,
                CONCENT_PUBLIC_KEY),
            content_type = 'application/octet-stream',
            HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY=b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
        )

        self.assertEqual(response.status_code,                   202)
        self._assert_stored_message_counter_increased(increased_by = 2)
        self._test_last_stored_messages(
            expected_messages = [
                message.TaskToCompute,
                message.ReportComputedTask,
            ],
            task_id         = 'ABC00XYZ',
            subtask_id      = 'ABC00XYZ',
            timestamp       = "2017-11-17 10:00:00"
        )

    @freeze_time("2017-11-17 10:00:00")
    def test_send_should_return_http_400_if_data_is_incorrect(self):
        compute_task_def    = message.ComputeTaskDef()
        task_to_compute     = message.TaskToCompute(
            compute_task_def     = compute_task_def,
            provider_public_key  = PROVIDER_PUBLIC_KEY,
            requestor_public_key = REQUESTOR_PUBLIC_KEY,
        )
        report_computed_task = message.tasks.ReportComputedTask(
            task_to_compute = task_to_compute
        )
        with freeze_time("2017-11-17 9:56:00"):
            force_report_computed_task = message.ForceReportComputedTask(
                report_computed_task = report_computed_task
            )

        response = self.client.post(
            reverse('core:send'),
            data = dump(
                force_report_computed_task,
                PROVIDER_PRIVATE_KEY,
                CONCENT_PUBLIC_KEY,
            ),
            content_type                        = 'application/octet-stream',
            HTTP_CONCENT_CLIENT_PUBLIC_KEY      = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.json().keys())

        data                                        = message.ForceReportComputedTask()
        data.report_computed_task                   = message.tasks.ReportComputedTask()
        compute_task_def['deadline']                = self.message_timestamp - 3600
        data.report_computed_task.task_to_compute   = message.TaskToCompute(compute_task_def = compute_task_def)

        response = self.client.post(
            reverse('core:send'),
            data = dump(
                data,
                PROVIDER_PRIVATE_KEY,
                CONCENT_PUBLIC_KEY,
            ),
            content_type                        = 'application/octet-stream',
            HTTP_CONCENT_CLIENT_PUBLIC_KEY      = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.json().keys())

    @freeze_time("2017-11-17 10:00:00")
    def test_send_should_return_http_400_if_task_id_already_use(self):

        response_202 = self.client.post(
            reverse('core:send'),
            data = dump(
                self.correct_golem_data,
                PROVIDER_PRIVATE_KEY,
                CONCENT_PUBLIC_KEY,
            ),
            content_type                        = 'application/octet-stream',
            HTTP_CONCENT_CLIENT_PUBLIC_KEY      = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
        )

        self.assertIsInstance(response_202, HttpResponse)
        self.assertEqual(response_202.status_code, 202)
        self.correct_golem_data.encrypted  = None
        self.correct_golem_data.sig        = None
        response_400 = self.client.post(
            reverse('core:send'),
            data = dump(
                self.correct_golem_data,
                PROVIDER_PRIVATE_KEY,
                CONCENT_PUBLIC_KEY,
            ),
            content_type                        = 'application/octet-stream',
            HTTP_CONCENT_CLIENT_PUBLIC_KEY      = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
        )

        self.assertIsInstance(response_400, JsonResponse)
        self.assertEqual(response_400.status_code, 400)
        self.assertIn('error', response_400.json().keys())

    @freeze_time("2017-11-17 10:00:00")
    def test_send_should_return_http_400_if_get_invalid_type_of_message(self):

        assert isinstance(self.want_to_compute, message.Message)

        response_400 = self.client.post(
            reverse('core:send'),
            data = dump(
                self.want_to_compute,
                PROVIDER_PRIVATE_KEY,
                CONCENT_PUBLIC_KEY
            ),
            content_type                   = 'application/octet-stream',
            HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
        )

        self.assertEqual(response_400.status_code, 400)
        self.assertIn('error', response_400.json().keys())

    @freeze_time("2017-11-17 10:00:00")
    def test_send_should_return_http_400_if_task_to_compute_deadline_exceeded(self):
        compute_task_def = message.ComputeTaskDef()
        compute_task_def['task_id'] = '8'
        compute_task_def['deadline'] = self.message_timestamp - 9000

        with freeze_time(datetime.datetime.fromtimestamp(self.message_timestamp - 10000)):
            task_to_compute = message.TaskToCompute(
                compute_task_def     = self.compute_task_def,
                provider_public_key  = PROVIDER_PUBLIC_KEY,
                requestor_public_key = REQUESTOR_PUBLIC_KEY,
            )

        serialized_task_to_compute      = dump(task_to_compute,             REQUESTOR_PRIVATE_KEY,   PROVIDER_PUBLIC_KEY)
        deserialized_task_to_compute    = load(serialized_task_to_compute,  PROVIDER_PRIVATE_KEY,  REQUESTOR_PUBLIC_KEY, check_time = False)

        ack_report_computed_task = message.AckReportComputedTask()
        ack_report_computed_task.task_to_compute = deserialized_task_to_compute

        response_400 = self.client.post(
            reverse('core:send'),
            data = dump(
                ack_report_computed_task,
                PROVIDER_PRIVATE_KEY,
                CONCENT_PUBLIC_KEY
            ),
            content_type                    = 'application/octet-stream',
            HTTP_CONCENT_CLIENT_PUBLIC_KEY  = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
        )

        self.assertEqual(response_400.status_code, 400)
        self.assertIn('error', response_400.json().keys())

    @freeze_time("2017-11-17 10:00:00")
    def test_send_reject_message_save_as_receive_out_of_band_status(self):
        assert StoredMessage.objects.count() == 0

        force_response = self.client.post(
            reverse('core:send'),
            data = dump(
                self.correct_golem_data,
                PROVIDER_PRIVATE_KEY,
                CONCENT_PUBLIC_KEY),
            content_type                        = 'application/octet-stream',
            HTTP_CONCENT_CLIENT_PUBLIC_KEY      = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
        )

        self.assertEqual(force_response.status_code,                                202)
        self._test_last_stored_messages(
            expected_messages = [
                message.TaskToCompute,
                message.ReportComputedTask,
            ],
            task_id         = '8',
            subtask_id      = '8',
            timestamp       = "2017-11-17 10:00:00"
        )

        reject_response = self.client.post(
            reverse('core:send'),
            data = dump(
                self.reject_report_computed_task,
                REQUESTOR_PRIVATE_KEY,
                CONCENT_PUBLIC_KEY
            ),
            content_type                   = 'application/octet-stream',
            HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
        )

        self.assertEqual(reject_response.status_code,       202)
        self._test_last_stored_messages(
            expected_messages = [
                message.RejectReportComputedTask,
            ],
            task_id         = '8',
            subtask_id      = '8',
            timestamp       = "2017-11-17 10:00:00"
        )

    def test_send_should_reject_message_when_timestamp_too_old(self):
        with freeze_time("2017-11-17 09:40:00"):
            ping = message.Ping()

        with freeze_time("2017-11-17 10:00:00"):
            timestamp = dateutil.parser.parse("2017-11-17 09:40:00")
            assert datetime.datetime.now() - timestamp > settings.MSG_TTL
            response = self.client.post(
                reverse('core:send'),
                data = dump(
                    ping,
                    PROVIDER_PRIVATE_KEY,
                    CONCENT_PUBLIC_KEY
                ),
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii')
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.json().keys())

    def test_send_should_reject_message_when_timestamp_too_far_in_future(self):
        with freeze_time("2017-11-17 10:10:00"):
            ping = message.Ping()

        with freeze_time("2017-11-17 10:00:00"):
            timestamp = dateutil.parser.parse("2017-11-17 10:10:00")
            assert timestamp - datetime.datetime.now() > settings.FUTURE_TIME_TOLERANCE
            response = self.client.post(
                reverse('core:send'),
                data = dump(
                    ping,
                    PROVIDER_PRIVATE_KEY,
                    CONCENT_PUBLIC_KEY
                ),
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii')
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.json().keys())

    @freeze_time("2017-11-17 10:00:00")
    def test_send_should_return_http_400_if_task_to_compute_deadline_is_not_an_integer(self):
        compute_task_def = message.ComputeTaskDef()
        compute_task_def['task_id']    = '8'
        compute_task_def['subtask_id'] = '8'

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
            task_to_compute = message.TaskToCompute(
                compute_task_def     = compute_task_def,
                provider_public_key  = PROVIDER_PUBLIC_KEY,
                requestor_public_key = REQUESTOR_PUBLIC_KEY,
            )

            serialized_task_to_compute   = dump(task_to_compute,             REQUESTOR_PRIVATE_KEY,   PROVIDER_PUBLIC_KEY)
            deserialized_task_to_compute = load(serialized_task_to_compute,  PROVIDER_PRIVATE_KEY,  REQUESTOR_PUBLIC_KEY, check_time = False)

            with freeze_time("2017-11-17 10:00:00"):
                force_report_computed_task = message.ForceReportComputedTask(
                    report_computed_task = message.tasks.ReportComputedTask(
                        task_to_compute = deserialized_task_to_compute
                    )
                )

                response_400 = self.client.post(
                    reverse('core:send'),
                    data=dump(
                        force_report_computed_task,
                        PROVIDER_PRIVATE_KEY,
                        CONCENT_PUBLIC_KEY
                    ),
                    content_type = 'application/octet-stream',
                    HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
                )

            self.assertEqual(response_400.status_code, 400)
            self.assertIn('error', response_400.json().keys())

    def test_send_should_return_http_202_if_task_to_compute_deadline_is_correct(self):
        compute_task_def = message.ComputeTaskDef()

        invalid_values = [
            11,
            '1112',
            True,
            0,
            False,
        ]

        for i, deadline in enumerate(invalid_values):
            StoredMessage.objects.all().delete()
            compute_task_def['task_id']     = str(i)
            compute_task_def['subtask_id']  = str(i)
            compute_task_def['deadline']    = deadline
            task_to_compute                 = message.TaskToCompute(
                compute_task_def     = compute_task_def,
                provider_public_key  = PROVIDER_PUBLIC_KEY,
                requestor_public_key = REQUESTOR_PUBLIC_KEY,
            )

            serialized_task_to_compute   = dump(task_to_compute,             REQUESTOR_PRIVATE_KEY,   PROVIDER_PUBLIC_KEY)
            deserialized_task_to_compute = load(serialized_task_to_compute,  PROVIDER_PRIVATE_KEY,  REQUESTOR_PUBLIC_KEY, check_time = False)

            with freeze_time("2017-11-17 10:00:00"):
                report_computed_task = message.tasks.ReportComputedTask(
                    task_to_compute = deserialized_task_to_compute
                )
                force_report_computed_task = message.ForceReportComputedTask(
                    report_computed_task = report_computed_task
                )

                response_202 = self.client.post(
                    reverse('core:send'),
                    data = dump(
                        force_report_computed_task,
                        PROVIDER_PRIVATE_KEY,
                        CONCENT_PUBLIC_KEY
                    ),
                    content_type                        = 'application/octet-stream',
                    HTTP_CONCENT_CLIENT_PUBLIC_KEY      = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
                    HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
                )

            self.assertIn(response_202.status_code, [200, 202])

    @freeze_time("2017-11-17 10:00:00")
    def test_send_task_to_compute_without_public_key_should_return_http_400(self):
        assert StoredMessage.objects.count() == 0

        for field_name in [
            'provider_public_key',
            'requestor_public_key',
        ]:
            setattr(self.task_to_compute, field_name, None)

            response = self._send_force_report_computed_task()

            self._test_400_response(response)
            self._assert_stored_message_counter_not_increased()
            self._assert_client_count_is_equal(0)

    @freeze_time("2017-11-17 10:00:00")
    def test_send_task_to_compute_with_public_key_with_wrong_length_should_return_http_400(self):
        assert StoredMessage.objects.count() == 0

        for field_name in [
            'provider_public_key',
            'requestor_public_key',
        ]:
            setattr(
                self.task_to_compute,
                field_name,
                getattr(self.task_to_compute, field_name)[:-1]
            )

            response = self._send_force_report_computed_task()

            self._test_400_response(response)
            self._assert_stored_message_counter_not_increased()
            self._assert_client_count_is_equal(0)

    def test_send_with_empty_data_should_return_http_400_error(self):
        response = self.client.post(
            reverse('core:send'),
            data                                = '',
            content_type                        = 'application/octet-stream',
            HTTP_CONCENT_CLIENT_PUBLIC_KEY      = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
        )

        self.assertEqual(response.status_code, 400)


@override_settings(
    CONCENT_PRIVATE_KEY    = CONCENT_PRIVATE_KEY,
    CONCENT_PUBLIC_KEY     = CONCENT_PUBLIC_KEY,
    CONCENT_MESSAGING_TIME = 3600,
)
class CoreViewReceiveTest(TestCase):

    def setUp(self):
        with freeze_time("2017-11-17 10:00:00"):
            self.compute_task_def               = message.ComputeTaskDef()
            self.compute_task_def['task_id']    = '1'
            self.compute_task_def['subtask_id'] = '1'
            self.compute_task_def['deadline']   = get_current_utc_timestamp() + (60 * 37)
            self.task_to_compute = message.TaskToCompute(
                compute_task_def     = self.compute_task_def,
                provider_public_key  = PROVIDER_PUBLIC_KEY,
                requestor_public_key = REQUESTOR_PUBLIC_KEY,
            )
            self.force_golem_data = message.ForceReportComputedTask(
                report_computed_task = message.tasks.ReportComputedTask(
                    task_to_compute = self.task_to_compute
                )
            )

    @freeze_time("2017-11-17 10:00:00")
    def test_receive_should_accept_valid_message(self):
        message_timestamp = datetime.datetime.now(timezone.utc)
        new_message       = StoredMessage(
            type        = self.force_golem_data.report_computed_task.TYPE,
            timestamp   = message_timestamp,
            data        = self.force_golem_data.report_computed_task.serialize(),
            task_id     = self.task_to_compute.compute_task_def['task_id'],  # pylint: disable=no-member
            subtask_id  = self.task_to_compute.compute_task_def['subtask_id'],  # pylint: disable=no-member
        )
        new_message.full_clean()
        new_message.save()

        client_provider = Client(
            public_key_bytes = PROVIDER_PUBLIC_KEY
        )
        client_provider.full_clean()
        client_provider.save()

        client_requestor = Client(
            public_key_bytes = REQUESTOR_PUBLIC_KEY
        )
        client_requestor.full_clean()
        client_requestor.save()

        task_to_compute_message = StoredMessage(
            type        = self.task_to_compute.TYPE,
            timestamp   = message_timestamp,
            data        = self.task_to_compute.serialize(),
            task_id     = self.task_to_compute.compute_task_def['task_id'],  # pylint: disable=no-member
            subtask_id  = self.task_to_compute.compute_task_def['subtask_id'],  # pylint: disable=no-member
        )
        task_to_compute_message.full_clean()
        task_to_compute_message.save()

        subtask = Subtask(
            task_id                 = self.compute_task_def['task_id'],
            subtask_id              = self.compute_task_def['subtask_id'],
            task_to_compute         = task_to_compute_message,
            report_computed_task    = new_message,
            state                   = Subtask.SubtaskState.REPORTED.name,  # pylint: disable=no-member
            provider                = client_provider,
            requestor               = client_requestor,
        )
        subtask.full_clean()
        subtask.save()

        new_message_inbox = PendingResponse(
            response_type = PendingResponse.ResponseType.ForceReportComputedTask.name,  # pylint: disable=no-member
            client        = client_requestor,
            queue         = PendingResponse.Queue.Receive.name,  # pylint: disable=no-member
            subtask       = subtask,
        )
        new_message_inbox.full_clean()
        new_message_inbox.save()

        response = self.client.post(
            reverse('core:receive'),
            content_type                   = 'application/octet-stream',
            data                           = '',
            HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii')
        )
        decoded_response = load(
            response.content,
            REQUESTOR_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY,
        )
        self.assertEqual(response.status_code,   200)
        self.assertEqual(new_message.task_id,    decoded_response.report_computed_task.task_to_compute.compute_task_def['task_id'])
        self.assertEqual(new_message.subtask_id, decoded_response.report_computed_task.task_to_compute.compute_task_def['subtask_id'])

    @freeze_time("2017-11-17 10:00:00")
    def test_receive_return_http_204_if_no_messages_in_database(self):
        response = self.client.post(
            reverse('core:receive'),
            data                           = '',
            content_type                   = 'application/octet-stream',
            HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii')
        )

        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content.decode(), '')

    def test_receive_should_return_ack_if_the_receive_queue_contains_only_force_report_and_its_past_deadline(self):

        with freeze_time("2017-11-17 10:00:00"):
            self.compute_task_def               = message.ComputeTaskDef()
            self.compute_task_def['task_id']    = '2'
            self.compute_task_def['subtask_id'] = '2'
            self.compute_task_def['deadline']   = get_current_utc_timestamp()
            self.task_to_compute = message.TaskToCompute(
                compute_task_def     = self.compute_task_def,
                provider_public_key  = PROVIDER_PUBLIC_KEY,
                requestor_public_key = REQUESTOR_PUBLIC_KEY,
            )
            self.force_golem_data = message.ForceReportComputedTask(
                report_computed_task = message.tasks.ReportComputedTask(
                    task_to_compute = self.task_to_compute
                )
            )

    def test_receive_should_return_first_messages_in_order_they_were_added_to_queue_if_the_receive_queue_contains_only_force_report_and_its_past_deadline(self):
        message_timestamp = datetime.datetime.now(timezone.utc)
        new_message       = StoredMessage(
            type        = self.force_golem_data.report_computed_task.TYPE,
            timestamp   = message_timestamp,
            data        = self.force_golem_data.report_computed_task.serialize(),
            task_id     = self.task_to_compute.compute_task_def['task_id'],  # pylint: disable=no-member
            subtask_id  = self.task_to_compute.compute_task_def['subtask_id'],  # pylint: disable=no-member
        )
        new_message.full_clean()
        new_message.save()

        task_to_compute_message = StoredMessage(
            type        = self.task_to_compute.TYPE,
            timestamp   = message_timestamp,
            data        = self.task_to_compute.serialize(),
            task_id     = self.task_to_compute.compute_task_def['task_id'],  # pylint: disable=no-member
            subtask_id  = self.task_to_compute.compute_task_def['subtask_id'],  # pylint: disable=no-member
        )
        task_to_compute_message.full_clean()
        task_to_compute_message.save()

        ack_report_computed_task = message.concents.AckReportComputedTask(
            task_to_compute = self.task_to_compute,
            subtask_id      = self.task_to_compute.compute_task_def['subtask_id']  # pylint: disable=no-member
        )

        stored_ack_report_computed_task = StoredMessage(
            type        = ack_report_computed_task.TYPE,
            timestamp   = message_timestamp,
            data        = ack_report_computed_task.serialize(),
            task_id     = self.task_to_compute.compute_task_def['task_id'],  # pylint: disable=no-member
            subtask_id  = self.task_to_compute.compute_task_def['subtask_id'],  # pylint: disable=no-member
        )
        stored_ack_report_computed_task.full_clean()
        stored_ack_report_computed_task.save()

        client_provider = Client(
            public_key_bytes = PROVIDER_PUBLIC_KEY
        )
        client_provider.full_clean()
        client_provider.save()

        client_requestor = Client(
            public_key_bytes = REQUESTOR_PUBLIC_KEY
        )
        client_requestor.full_clean()
        client_requestor.save()

        subtask = Subtask(
            task_id                  = self.compute_task_def['task_id'],
            subtask_id               = self.compute_task_def['subtask_id'],
            report_computed_task     = new_message,
            task_to_compute          = task_to_compute_message,
            ack_report_computed_task = stored_ack_report_computed_task,
            state                    = Subtask.SubtaskState.REPORTED.name,  # pylint: disable=no-member
            provider                 = client_provider,
            requestor                = client_requestor,
        )
        subtask.full_clean()
        subtask.save()

        new_message_inbox = PendingResponse(
            response_type = PendingResponse.ResponseType.ForceReportComputedTask.name,  # pylint: disable=no-member
            client        = client_requestor,
            queue         = PendingResponse.Queue.Receive.name,  # pylint: disable=no-member
            subtask       = subtask,
        )
        new_message_inbox.full_clean()
        new_message_inbox.save()

        new_message_inbox_out_of_band = PendingResponse(
            response_type = PendingResponse.ResponseType.VerdictReportComputedTask.name,  # pylint: disable=no-member
            client        = client_requestor,
            queue         = PendingResponse.Queue.ReceiveOutOfBand.name,  # pylint: disable=no-member
            subtask       = subtask,
        )
        new_message_inbox_out_of_band.full_clean()
        new_message_inbox_out_of_band.save()

        with freeze_time("2017-11-17 12:00:00"):
            response = self.client.post(
                reverse('core:receive'),
                content_type                   = 'application/octet-stream',
                data                           = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii')
            )

        decoded_message = load(
            response.content,
            REQUESTOR_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY,
            check_time = False,
        )

        self.assertIsInstance(decoded_message,                                                  message.concents.ForceReportComputedTask)
        self.assertEqual(response.status_code,                                                  200)
        self.assertEqual(decoded_message.timestamp,                                             int(dateutil.parser.parse("2017-11-17 12:00:00").timestamp()))
        self.assertEqual(decoded_message.report_computed_task.task_to_compute.compute_task_def, self.task_to_compute.compute_task_def)  # pylint: disable=no-member
        self.assertEqual(decoded_message.report_computed_task.task_to_compute.sig,              self.task_to_compute.sig)
        self.assertEqual(decoded_message.report_computed_task.subtask_id,                       None)

        with freeze_time("2017-11-17 12:00:00"):
            response = self.client.post(
                reverse('core:receive_out_of_band'),
                content_type                   = 'application/octet-stream',
                data                           = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii')
            )

        decoded_message = load(
            response.content,
            REQUESTOR_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY,
            check_time = False,
        )

        self.assertIsInstance(decoded_message,                                                      message.concents.VerdictReportComputedTask)
        self.assertEqual(response.status_code,                                                      200)
        self.assertEqual(decoded_message.timestamp,                                                 int(dateutil.parser.parse("2017-11-17 12:00:00").timestamp()))
        self.assertEqual(decoded_message.ack_report_computed_task.task_to_compute.compute_task_def, self.task_to_compute.compute_task_def)  # pylint: disable=no-member
        self.assertEqual(decoded_message.ack_report_computed_task.task_to_compute.sig,              self.task_to_compute.sig)
        self.assertEqual(decoded_message.ack_report_computed_task.subtask_id,                       '1')


@override_settings(
    CONCENT_PRIVATE_KEY    = CONCENT_PRIVATE_KEY,
    CONCENT_PUBLIC_KEY     = CONCENT_PUBLIC_KEY,
    CONCENT_MESSAGING_TIME = 3600,
)
class CoreViewReceiveOutOfBandTest(TestCase):

    def setUp(self):
        self.compute_task_def               = message.ComputeTaskDef()
        self.compute_task_def['task_id']    = '1'
        self.compute_task_def['subtask_id'] = '1'
        self.compute_task_def['deadline']   = get_current_utc_timestamp() - 60
        self.task_to_compute                = message.TaskToCompute(
            compute_task_def     = self.compute_task_def,
            provider_public_key  = PROVIDER_PUBLIC_KEY,
            requestor_public_key = REQUESTOR_PUBLIC_KEY,
        )

        self.force_golem_data = message.ForceReportComputedTask(
            report_computed_task = message.tasks.ReportComputedTask(
                task_to_compute = self.task_to_compute
            )
        )

        with freeze_time("2017-11-17 10:00:00"):
            self.force_golem_data = message.ForceReportComputedTask(
                report_computed_task = message.tasks.ReportComputedTask(
                    task_to_compute = self.task_to_compute
                )
            )
        message_timestamp = datetime.datetime.now(timezone.utc)
        new_message       = StoredMessage(
            type        = self.force_golem_data.report_computed_task.TYPE,
            timestamp   = message_timestamp,
            data        = self.force_golem_data.report_computed_task.serialize(),
            task_id     = self.task_to_compute.compute_task_def['task_id'],  # pylint: disable=no-member
            subtask_id  = self.task_to_compute.compute_task_def['subtask_id'],  # pylint: disable=no-member
        )
        new_message.full_clean()
        new_message.save()

        task_to_compute_message = StoredMessage(
            type        = self.task_to_compute.TYPE,
            timestamp   = message_timestamp,
            data        = self.task_to_compute.serialize(),
            task_id     = self.task_to_compute.compute_task_def['task_id'],  # pylint: disable=no-member
            subtask_id  = self.task_to_compute.compute_task_def['subtask_id'],  # pylint: disable=no-member
        )
        task_to_compute_message.full_clean()
        task_to_compute_message.save()

        ack_report_computed_task = message.concents.AckReportComputedTask(
            task_to_compute = self.task_to_compute,
            subtask_id      = self.task_to_compute.compute_task_def['subtask_id']  # pylint: disable=no-member
        )

        stored_ack_report_computed_task = StoredMessage(
            type        = ack_report_computed_task.TYPE,
            timestamp   = message_timestamp,
            data        = ack_report_computed_task.serialize(),
            task_id     = self.task_to_compute.compute_task_def['task_id'],  # pylint: disable=no-member
            subtask_id  = self.task_to_compute.compute_task_def['subtask_id'],  # pylint: disable=no-member
        )
        stored_ack_report_computed_task.full_clean()
        stored_ack_report_computed_task.save()

        client_provider = Client(
            public_key_bytes = PROVIDER_PUBLIC_KEY
        )
        client_provider.full_clean()
        client_provider.save()

        client_requestor = Client(
            public_key_bytes = REQUESTOR_PUBLIC_KEY
        )
        client_requestor.full_clean()
        client_requestor.save()

        subtask = Subtask(
            task_id                  = self.compute_task_def['task_id'],
            subtask_id               = self.compute_task_def['subtask_id'],
            report_computed_task     = new_message,
            task_to_compute          = task_to_compute_message,
            ack_report_computed_task = stored_ack_report_computed_task,
            state                    = Subtask.SubtaskState.REPORTED.name,  # pylint: disable=no-member
            provider                 = client_provider,
            requestor                = client_requestor,
        )
        subtask.full_clean()
        subtask.save()

        new_message_inbox = PendingResponse(
            response_type = PendingResponse.ResponseType.ForceReportComputedTask.name,  # pylint: disable=no-member
            client        = client_requestor,
            queue         = PendingResponse.Queue.ReceiveOutOfBand.name,  # pylint: disable=no-member
            subtask       = subtask,
        )
        new_message_inbox.full_clean()
        new_message_inbox.save()

    @freeze_time("2017-11-17 11:40:00")
    def test_view_receive_out_of_band_should_accept_valid_message(self):

        response = self.client.post(
            reverse('core:receive_out_of_band'),
            data                                = '',
            content_type                        = 'application/octet-stream',
            HTTP_CONCENT_CLIENT_PUBLIC_KEY      = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
        )

        self.assertEqual(response.status_code, 200)

    @freeze_time("2017-11-17 9:20:00")
    def test_view_receive_out_of_band_return_http_204_if_no_messages_in_database(self):
        response = self.client.post(
            reverse('core:receive_out_of_band'),
            data                                = '',
            content_type                        = 'application/octet-stream',
            HTTP_CONCENT_CLIENT_PUBLIC_KEY      = b64encode(DIFFERENT_PUBLIC_KEY).decode('ascii'),
        )

        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content.decode(), '')
