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

from core.models                    import Message
from core.models                    import ReceiveStatus
from utils.testing_helpers          import generate_ecc_key_pair


(CONCENT_PRIVATE_KEY,   CONCENT_PUBLIC_KEY)   = generate_ecc_key_pair()
(PROVIDER_PRIVATE_KEY,  PROVIDER_PUBLIC_KEY)  = generate_ecc_key_pair()
(REQUESTOR_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY) = generate_ecc_key_pair()


@override_settings(
    CONCENT_PRIVATE_KEY    = CONCENT_PRIVATE_KEY,
    CONCENT_PUBLIC_KEY     = CONCENT_PUBLIC_KEY,
    CONCENT_MESSAGING_TIME = 3600,
)
class CoreViewSendTest(TestCase):

    @freeze_time("2017-11-17 10:00:00")
    def setUp(self):
        self.message_timestamp = int(datetime.datetime.now().timestamp())  # 1510912800
        self.compute_task_def = message.ComputeTaskDef()
        self.compute_task_def['task_id'] = 8
        self.compute_task_def['deadline'] = self.message_timestamp
        self.task_to_compute = message.TaskToCompute(
            timestamp = self.message_timestamp,
            compute_task_def = self.compute_task_def,
        )

        self.correct_golem_data = message.ForceReportComputedTask(
            timestamp = self.message_timestamp,
        )
        self.correct_golem_data.task_to_compute = self.task_to_compute
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
            timestamp = self.message_timestamp,
        )

        self.cannot_compute_task = message.CannotComputeTask()
        self.cannot_compute_task.task_to_compute = message.TaskToCompute(
            timestamp = self.message_timestamp,
        )

        self.cannot_compute_task.task_to_compute.compute_task_def               = message.ComputeTaskDef()
        self.cannot_compute_task.task_to_compute.compute_task_def['deadline']   = self.message_timestamp + 600
        self.cannot_compute_task.task_to_compute.compute_task_def['task_id']    = 8

        self.reject_report_computed_task = message.RejectReportComputedTask(
            timestamp = self.message_timestamp,
        )

        self.reject_report_computed_task.reason                 = message.RejectReportComputedTask.REASON.TaskTimeLimitExceeded
        self.reject_report_computed_task.cannot_compute_task    = self.cannot_compute_task

    @freeze_time("2017-11-17 10:00:00")
    def test_send_should_accept_valid_message(self):
        assert Message.objects.count()       == 0
        assert ReceiveStatus.objects.count() == 0

        response = self.client.post(
            reverse('core:send'),
            data = dump(
                self.correct_golem_data,
                PROVIDER_PRIVATE_KEY,
                CONCENT_PUBLIC_KEY),
            content_type = 'application/octet-stream',
            HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii')
        )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(len(Message.objects.all()),       1)
        self.assertEqual(Message.objects.last().type,      message.ForceReportComputedTask.TYPE)
        self.assertEqual(len(ReceiveStatus.objects.all()), 1)
        self.assertEqual(Message.objects.last().id,        ReceiveStatus.objects.last().message_id)

    @freeze_time("2017-11-17 10:00:00")
    def test_send_should_return_http_200_if_message_timeout(self):
        assert Message.objects.count()       == 0
        assert ReceiveStatus.objects.count() == 0

        task_to_compute = self.task_to_compute
        task_to_compute.compute_task_def['deadline'] = self.message_timestamp - 1   # pylint: disable=no-member
        correct_golem_data = message.ForceReportComputedTask(
            timestamp = self.message_timestamp,
        )
        correct_golem_data.task_to_compute = task_to_compute

        response = self.client.post(
            reverse('core:send'),
            data = dump(
                correct_golem_data,
                PROVIDER_PRIVATE_KEY,
                CONCENT_PUBLIC_KEY
            ),
            content_type = 'application/octet-stream',
            HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii')
        )

        self.assertEqual(response.status_code, 200)
        response_message = load(
            response.content,
            PROVIDER_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY,
        )
        self.assertIsInstance(response_message, GolemMessage)

    @freeze_time("2017-11-17 10:00:00")
    def test_send_should_return_http_400_if_data_is_incorrect(self):
        force_report_computed_task = message.ForceReportComputedTask(
            timestamp = int(dateutil.parser.parse("2017-11-17 9:56:00").timestamp())
        )
        compute_task_def = message.ComputeTaskDef()
        task_to_compute = message.TaskToCompute(compute_task_def = compute_task_def)
        force_report_computed_task.task_to_compute = task_to_compute
        response = self.client.post(
            reverse('core:send'),
            data = dump(
                force_report_computed_task,
                PROVIDER_PRIVATE_KEY,
                CONCENT_PUBLIC_KEY,
            ),
            content_type = 'application/octet-stream',
            HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii')
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.json().keys())

        data = message.ForceReportComputedTask(
            timestamp = self.message_timestamp,
        )
        compute_task_def['deadline'] = int(dateutil.parser.parse("2017-11-17 9:00:00").timestamp())
        data.task_to_compute = message.TaskToCompute(compute_task_def = compute_task_def)

        response = self.client.post(
            reverse('core:send'),
            data = dump(
                data,
                PROVIDER_PRIVATE_KEY,
                CONCENT_PUBLIC_KEY,
            ),
            content_type = 'application/octet-stream',
            HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
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
            content_type = 'application/octet-stream',
            HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
        )

        self.assertIsInstance(response_202, HttpResponse)
        self.assertEqual(response_202.status_code, 202)
        self.correct_golem_data.encrypted = None
        self.correct_golem_data.sig = None
        self.correct_golem_data.task_to_compute.sig = None
        response_400 = self.client.post(
            reverse('core:send'),
            data = dump(
                self.correct_golem_data,
                PROVIDER_PRIVATE_KEY,
                CONCENT_PUBLIC_KEY,
            ),
            content_type = 'application/octet-stream',
            HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
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
        compute_task_def['task_id'] = 8
        compute_task_def['deadline'] = self.message_timestamp - 9000
        task_to_compute = message.TaskToCompute(
            timestamp = self.message_timestamp - 10000,
            compute_task_def = self.compute_task_def,
        )

        serialized_task_to_compute      = dump(task_to_compute,             REQUESTOR_PRIVATE_KEY,   PROVIDER_PUBLIC_KEY)
        deserialized_task_to_compute    = load(serialized_task_to_compute,  PROVIDER_PRIVATE_KEY,  REQUESTOR_PUBLIC_KEY, check_time = False)

        ack_report_computed_task = message.AckReportComputedTask(
            timestamp = self.message_timestamp,
        )
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
        assert Message.objects.count()       == 0
        assert ReceiveStatus.objects.count() == 0

        force_response = self.client.post(
            reverse('core:send'),
            data = dump(
                self.correct_golem_data,
                PROVIDER_PRIVATE_KEY,
                CONCENT_PUBLIC_KEY),
            content_type                   = 'application/octet-stream',
            HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii')
        )

        self.assertEqual(force_response.status_code, 202)
        self.assertEqual(Message.objects.last().type, message.ForceReportComputedTask.TYPE)

        reject_response = self.client.post(
            reverse('core:send'),
            data = dump(
                self.reject_report_computed_task,
                PROVIDER_PRIVATE_KEY,
                CONCENT_PUBLIC_KEY
            ),
            content_type                   = 'application/octet-stream',
            HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii')
        )

        self.assertEqual(reject_response.status_code, 202)
        self.assertEqual(Message.objects.last().type, message.RejectReportComputedTask.TYPE)

    def test_send_should_reject_message_when_timestamp_too_old(self):
        with freeze_time("2017-11-17 10:00:00"):
            timestamp = dateutil.parser.parse("2017-11-17 09:40:00")
            assert datetime.datetime.now() - timestamp > settings.MSG_TTL
            response = self.client.post(
                reverse('core:send'),
                data = dump(
                    message.Ping(
                        timestamp=int(timestamp.timestamp())
                    ),
                    PROVIDER_PRIVATE_KEY,
                    CONCENT_PUBLIC_KEY
                ),
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii')
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.json().keys())

    def test_send_should_reject_message_when_timestamp_too_far_in_future(self):
        with freeze_time("2017-11-17 10:00:00"):
            timestamp = dateutil.parser.parse("2017-11-17 10:10:00")
            assert timestamp - datetime.datetime.now() > settings.FUTURE_TIME_TOLERANCE
            response = self.client.post(
                reverse('core:send'),
                data = dump(
                    message.Ping(
                        timestamp=int(dateutil.parser.parse("2017-11-17 10:10:00").timestamp())
                    ),
                    PROVIDER_PRIVATE_KEY,
                    CONCENT_PUBLIC_KEY
                ),
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii')
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.json().keys())


@override_settings(
    CONCENT_PRIVATE_KEY    = CONCENT_PRIVATE_KEY,
    CONCENT_PUBLIC_KEY     = CONCENT_PUBLIC_KEY,
    CONCENT_MESSAGING_TIME = 3600,
)
class CoreViewReceiveTest(TestCase):

    def setUp(self):
        self.compute_task_def = message.ComputeTaskDef()
        self.compute_task_def['task_id'] = 1
        self.compute_task_def['deadline'] = int(dateutil.parser.parse("2017-11-17 10:37:00").timestamp())
        self.task_to_compute = message.TaskToCompute(
            timestamp = int(dateutil.parser.parse("2017-11-17 10:00:00").timestamp()),
            compute_task_def = self.compute_task_def,
        )
        self.force_golem_data = message.ForceReportComputedTask(
            timestamp = int(dateutil.parser.parse("2017-11-17 10:00:00").timestamp()),
        )
        self.force_golem_data.task_to_compute = self.task_to_compute

    @freeze_time("2017-11-17 10:00:00")
    def test_receive_should_accept_valid_message(self):
        message_timestamp   = datetime.datetime.now(timezone.utc)
        new_message         = Message(
            type        = self.force_golem_data.TYPE,
            timestamp   = message_timestamp,
            data        = self.force_golem_data.serialize(),
            task_id     = self.task_to_compute.compute_task_def['task_id']  # pylint: disable=no-member
        )
        new_message.full_clean()
        new_message.save()
        new_message_status = ReceiveStatus(
            message   = new_message,
            timestamp = message_timestamp,
            delivered = False
        )
        new_message_status.full_clean()
        new_message_status.save()

        assert len(ReceiveStatus.objects.filter(delivered=False)) == 1

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
        self.assertEqual(response.status_code, 200)
        self.assertEqual(new_message.task_id, decoded_response.task_to_compute.compute_task_def['task_id'])

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
        assert len(ReceiveStatus.objects.filter(delivered=False)) == 0

    def test_receive_should_return_ack_if_the_receive_queue_contains_only_force_report_and_its_past_deadline(self):
        self.compute_task_def               = message.ComputeTaskDef()
        self.compute_task_def['task_id']    = 2
        self.compute_task_def['deadline']   = int(dateutil.parser.parse("2017-11-17 10:00:00").timestamp())

        self.task_to_compute = message.TaskToCompute(
            timestamp           = int(dateutil.parser.parse("2017-11-17 10:00:00").timestamp()),
            compute_task_def    = self.compute_task_def,
        )
        self.force_golem_data = message.ForceReportComputedTask(
            timestamp       = int(dateutil.parser.parse("2017-11-17 10:00:00").timestamp()),
            task_to_compute = self.task_to_compute
        )
        message_timestamp = datetime.datetime.now(timezone.utc)
        new_message = Message(
            type        = self.force_golem_data.TYPE,
            timestamp   = message_timestamp,
            data        = self.force_golem_data.serialize(),
            task_id     = self.task_to_compute.compute_task_def['task_id']  # pylint: disable=no-member
        )
        new_message.full_clean()
        new_message.save()
        new_message_status = ReceiveStatus(
            message   = new_message,
            timestamp = message_timestamp,
            delivered = False
        )
        new_message_status.full_clean()
        new_message_status.save()

        with freeze_time("2017-11-17 12:00:00"):
            response = self.client.post(
                reverse('core:receive'),
                content_type                   = 'application/octet-stream',
                data                           = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii')
            )

        decoded_ack_response = load(
            response.content,
            REQUESTOR_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY,
            check_time = False,
        )

        undelivered_messages = ReceiveStatus.objects.filter(delivered = False).count()

        self.assertIsInstance(decoded_ack_response, message.AckReportComputedTask)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(undelivered_messages, 0)
        self.assertGreaterEqual(decoded_ack_response.timestamp,                 int(dateutil.parser.parse("2017-11-17 12:00:00").timestamp()))
        self.assertLessEqual(   decoded_ack_response.timestamp,                 int(dateutil.parser.parse("2017-11-17 12:00:15").timestamp()))
        self.assertEqual(decoded_ack_response.task_to_compute.compute_task_def, self.task_to_compute.compute_task_def)  # pylint: disable=no-member
        self.assertEqual(decoded_ack_response.task_to_compute.sig,              self.task_to_compute.sig)
        self.assertEqual(decoded_ack_response.subtask_id,                       None)


@override_settings(
    CONCENT_PRIVATE_KEY    = CONCENT_PRIVATE_KEY,
    CONCENT_PUBLIC_KEY     = CONCENT_PUBLIC_KEY,
    CONCENT_MESSAGING_TIME = 3600,
)
class CoreViewReceiveOutOfBandTest(TestCase):

    @freeze_time("2017-11-17 10:00:00")
    def setUp(self):
        self.compute_task_def = message.ComputeTaskDef()
        self.compute_task_def['task_id'] = 1
        self.compute_task_def['deadline'] = int(dateutil.parser.parse("2017-11-17 9:59:00").timestamp())
        self.task_to_compute = message.TaskToCompute(
            timestamp = int(dateutil.parser.parse("2017-11-17 10:00:00").timestamp()),
            compute_task_def = self.compute_task_def,
        )

        self.force_golem_data = message.ForceReportComputedTask(
            timestamp = int(dateutil.parser.parse("2017-11-17 10:00:00").timestamp()),
        )
        self.force_golem_data.task_to_compute = self.task_to_compute
        assert self.force_golem_data.timestamp == 1510912800

        message_timestamp   = datetime.datetime.now(timezone.utc)
        new_message         = Message(
            type        = self.force_golem_data.TYPE,
            timestamp   = message_timestamp,
            data        = self.force_golem_data.serialize(),
            task_id     = self.force_golem_data.task_to_compute.compute_task_def['task_id'],
        )
        new_message.full_clean()
        new_message.save()
        new_message_status = ReceiveStatus(

            message   = new_message,
            timestamp = message_timestamp,
            delivered = False
        )
        new_message_status.full_clean()
        new_message_status.save()

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
            HTTP_CONCENT_CLIENT_PUBLIC_KEY      = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
        )

        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content.decode(), '')
