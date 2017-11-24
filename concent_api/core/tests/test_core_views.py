import json
import datetime
from base64                         import b64encode

from freezegun                      import freeze_time
from django.test                    import Client
from django.test                    import override_settings
from django.test                    import TestCase
from django.urls                    import reverse
from django.http                    import HttpResponse
from django.http                    import JsonResponse
from django.conf                    import settings
from django.utils                   import timezone

from golem_messages.shortcuts       import dump
from golem_messages.shortcuts       import load
from golem_messages.message         import MessageForceReportComputedTask
from golem_messages.message         import MessageTaskToCompute

from core.models                    import Message
from core.models                    import MessageStatus
from utils.testing_helpers          import generate_ecc_key_pair


(CONCENT_PRIVATE_KEY,   CONCENT_PUBLIC_KEY)   = generate_ecc_key_pair()
(PROVIDER_PRIVATE_KEY,  PROVIDER_PUBLIC_KEY)  = generate_ecc_key_pair()
(REQUESTOR_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY) = generate_ecc_key_pair()


@override_settings(
    CONCENT_PRIVATE_KEY = CONCENT_PRIVATE_KEY,
    CONCENT_PUBLIC_KEY  = CONCENT_PUBLIC_KEY,
)
class CoreViewSendTest(TestCase):

    @freeze_time("2017-11-17 10:00:00")
    def setUp(self):
        self.client = Client()
        self.message_timestamp = int(datetime.datetime.now().timestamp())  # 1510912800
        self.message_task_to_compute = MessageTaskToCompute(
            timestamp = self.message_timestamp,
            task_id = 8,
            deadline = self.message_timestamp,
        )
        self.message_force_report_computed_task = MessageForceReportComputedTask(
            timestamp = self.message_timestamp,
            message_task_to_compute = dump(
                self.message_task_to_compute,
                PROVIDER_PRIVATE_KEY,
                REQUESTOR_PUBLIC_KEY
            )
        )

    @freeze_time("2017-11-17 10:00:00")
    def test_send_should_accept_valid_message(self):
        assert Message.objects.count()       == 0
        assert MessageStatus.objects.count() == 0

        response = self.client.post(
            reverse('core:send'),
            data                           = dump(self.message_force_report_computed_task, PROVIDER_PRIVATE_KEY, settings.CONCENT_PUBLIC_KEY),
            content_type                   = 'application/octet-stream',
            HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii')
        )

        self.assertEqual(response.status_code, 202)  # pylint: disable=no-member
        self.assertEqual(len(Message.objects.all()),       1)
        self.assertEqual(Message.objects.last().type,      "MessageForceReportComputedTask")
        self.assertEqual(len(MessageStatus.objects.all()), 1)
        self.assertEqual(Message.objects.last().id,        MessageStatus.objects.last().message_id)

    @freeze_time("2017-11-17 10:00:00")
    def test_send_should_return_http_200_if_message_timeout(self):
        self.assertEqual(len(Message.objects.all()), 0)
        self.assertEqual(len(MessageStatus.objects.all()), 0)

        message_task_to_compute            = self.message_task_to_compute
        message_task_to_compute.deadline   = self.message_timestamp - 1
        message_force_report_computed_task = MessageForceReportComputedTask(
            timestamp = self.message_timestamp,
            message_task_to_compute = dump(
                message_task_to_compute,
                PROVIDER_PRIVATE_KEY,
                REQUESTOR_PUBLIC_KEY,
            )
        )

        response = self.client.post(
            reverse('core:send'),
            data                           = dump(message_force_report_computed_task, PROVIDER_PRIVATE_KEY, settings.CONCENT_PUBLIC_KEY),
            content_type                   = 'application/octet-stream',
            HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii')
        )

        self.assertEqual(response.status_code, 200)  # pylint: disable=no-member
        response_message_type = load(
            response.content,
            PROVIDER_PRIVATE_KEY,
            settings.CONCENT_PUBLIC_KEY,
        )
        self.assertEqual(response_message_type.TYPE, 4003)  # pylint: disable=no-member

    @freeze_time("2017-11-17 10:00:00")
    def test_send_should_return_http_400_if_data_is_incorrect(self):
        message_force_report_computed_task_1 = MessageForceReportComputedTask(
            timestamp = 1510911047,
            message_task_to_compute = dump(
                MessageTaskToCompute(),
                PROVIDER_PRIVATE_KEY,
                REQUESTOR_PUBLIC_KEY
            )
        )

        response = self.client.post(
            reverse('core:send'),
            data                           = dump(message_force_report_computed_task_1, settings.CONCENT_PRIVATE_KEY, settings.CONCENT_PUBLIC_KEY),
            content_type                   = 'application/octet-stream',
            HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii')
        )
        self.assertEqual(response.status_code, 400)  # pylint: disable=no-member
        self.assertIn('error', response.json().keys())

        message_force_report_computed_task_2 = MessageForceReportComputedTask(
            timestamp = self.message_timestamp,
            message_task_to_compute = dump(
                MessageTaskToCompute(deadline = 1510909200),
                PROVIDER_PRIVATE_KEY,
                settings.CONCENT_PUBLIC_KEY
            )
        )

        response = self.client.post(
            reverse('core:send'),
            data                           = dump(message_force_report_computed_task_2, settings.CONCENT_PRIVATE_KEY, settings.CONCENT_PUBLIC_KEY),
            content_type                   = 'application/octet-stream',
            HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
        )

        self.assertEqual(response.status_code, 400)  # pylint: disable=no-member
        self.assertIn('error', response.json().keys())

    @freeze_time("2017-11-17 10:00:00")
    def test_send_should_return_http_400_if_task_id_already_use(self):
        response_202 = self.client.post(
            reverse('core:send'),
            data                           = dump(self.message_force_report_computed_task, settings.CONCENT_PRIVATE_KEY, settings.CONCENT_PUBLIC_KEY),
            content_type                   = 'application/octet-stream',
            HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
        )

        self.assertIsInstance(response_202, HttpResponse)
        self.assertEqual(response_202.status_code, 202)

        response_400 = self.client.post(
            reverse('core:send'),
            data                           = dump(self.message_force_report_computed_task, settings.CONCENT_PRIVATE_KEY, settings.CONCENT_PUBLIC_KEY),
            content_type                   = 'application/octet-stream',
            HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
        )

        self.assertIsInstance(response_400, JsonResponse)
        self.assertEqual(response_400.status_code, 400)  # pylint: disable=no-member
        self.assertIn('error', response_400.json().keys())


@override_settings(
    CONCENT_PRIVATE_KEY = CONCENT_PRIVATE_KEY,
    CONCENT_PUBLIC_KEY  = CONCENT_PUBLIC_KEY,
)
class CoreViewReceiveTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.public_key = '85cZzVjahnRpUBwm0zlNnqTdYom1LF1P1WNShLg17cmhN2UssnPrCjHKTi5susO3wrr/q07eswumbL82b4HgOw=='
        self.force_data = {
            "type":      "MessageForceReportComputedTask",
            "timestamp": 1510911047,
            "message_task_to_compute": {
                "type":               "MessageTaskToCompute",
                "timestamp":          1510909200,
                "task_id":            1,
                "deadline":           1510915047
            }
        }
        self.ack_data = {
            "type":      "MessageAckReportComputedTask",
            "timestamp": 1510911047,
            "message_task_to_compute": {
                "type":               "MessageTaskToCompute",
                "timestamp":          1510909200,
                "task_id":            1,
                "deadline":           1510915047
            }
        }
        self.reject_data = {
            "type":         "MessageRejectReportComputedTask",
            "timestamp":    1510911047,
            "reason":       "cannot-compute-task",
            "message_cannot_commpute_task": {
                "type":         "MessageCannotComputeTask",
                "timestamp":    1510909200,
                "reason":       "provider-quit",
                "task_id":      1
            }
        }

    @freeze_time("2017-11-17 10:00:00")
    def test_receive_should_accept_valid_message(self):
        message_timestamp   = datetime.datetime.now(timezone.utc)
        new_message         = Message(
            type        = self.force_data['type'],
            timestamp   = message_timestamp,
            data        = json.dumps(self.force_data).encode('utf-8'),
            task_id     = self.force_data['message_task_to_compute']['task_id']
        )
        new_message.save()
        new_message_status = MessageStatus(
            message   = new_message,
            timestamp   = message_timestamp,
            delivered = False
        )
        new_message_status.save()

        assert len(MessageStatus.objects.filter(delivered=False)) == 1

        response = self.client.post(
            reverse('core:receive'),
            content_type = 'application/json',
            HTTP_CONCENT_CLIENT_PUBLIC_KEY = self.public_key
        )

        self.assertEqual(response.status_code, 200)  # pylint: disable=no-member
        self.assertEqual(new_message.task_id, response.json()['message_task_to_compute']['task_id'])
        assert len(MessageStatus.objects.filter(delivered=False)) == 0

    @freeze_time("2017-11-17 10:00:00")
    def test_receive_return_http_204_if_no_messages_in_database(self):

        response = self.client.post(reverse('core:receive'), content_type = 'application/json', HTTP_CONCENT_CLIENT_PUBLIC_KEY = self.public_key)

        self.assertEqual(response.status_code, 204)  # pylint: disable=no-member
        self.assertEqual(response.content.decode(), '')
        assert len(MessageStatus.objects.filter(delivered=False)) == 0


class CoreViewReceiveOutOfBandTest(TestCase):

    @freeze_time("2017-11-17 10:00:00")
    def setUp(self):
        self.client = Client()
        self.public_key = '85cZzVjahnRpUBwm0zlNnqTdYom1LF1P1WNShLg17cmhN2UssnPrCjHKTi5susO3wrr/q07eswumbL82b4HgOw=='
        self.force_data = {
            "type":      "MessageForceReportComputedTask",
            "timestamp": 1510911047,  # 2017-11-17 9:30
            "message_task_to_compute": {
                "type":               "MessageTaskToCompute",
                "timestamp":          1510909200,  # 2017-11-17 9:00
                "task_id":            1,
                "deadline":           1510915047  # 2017-11-17 10:37
            }
        }
        message_timestamp   = datetime.datetime.now(timezone.utc)
        new_message         = Message(
            type        = self.force_data['type'],
            timestamp   = message_timestamp,
            data        = json.dumps(self.force_data).encode('utf-8'),
            task_id     = self.force_data['message_task_to_compute']['task_id']
        )
        new_message.save()
        new_message_status = MessageStatus(
            message = new_message,
            timestamp   = message_timestamp,
            delivered = False
        )
        new_message_status.save()

    @freeze_time("2017-11-17 11:40:00")
    def test_view_receive_out_of_band_should_accept_valid_message(self):
        response = self.client.post(reverse('core:receive_out_of_band'), content_type = 'application/json', HTTP_CONCENT_CLIENT_PUBLIC_KEY = self.public_key)

        self.assertEqual(response.status_code, 200)  # pylint: disable=no-member

    @freeze_time("2017-11-17 11:20:00")
    def test_view_receive_out_of_band_return_http_204_if_no_messages_in_database(self):
        response = self.client.post(reverse('core:receive_out_of_band'), content_type = 'application/json', HTTP_CONCENT_CLIENT_PUBLIC_KEY = self.public_key)

        self.assertEqual(response.status_code, 204)  # pylint: disable=no-member
        self.assertEqual(response.content.decode(), '')
