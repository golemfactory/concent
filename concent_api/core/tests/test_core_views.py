import json

from freezegun      import freeze_time
from django.test    import TestCase, Client
from django.urls    import reverse
from django.http    import JsonResponse, HttpResponse

from core.models import Message, MessageStatus


class CoreViewSendTest(TestCase):

    @freeze_time("2017-11-17 10:00:00")
    def setUp(self):
        self.client = Client()
        self.message_timestamp = int(datetime.datetime.now().timestamp())  # 1510912800
        self.correct_data = {
            "type":      "MessageForceReportComputedTask",
            "timestamp": self.message_timestamp,
            "message_task_to_compute": {
                "type":               "MessageTaskToCompute",
                "timestamp":          self.message_timestamp,
                "task_id":            8,
                "deadline":           self.message_timestamp + 3600
            }
        }
        self.public_key = '85cZzVjahnRpUBwm0zlNnqTdYom1LF1P1WNShLg17cmhN2UssnPrCjHKTi5susO3wrr/q07eswumbL82b4HgOw=='

    @freeze_time("2017-11-17 10:00:00")
    def test_send_should_accept_valid_message(self):
        assert Message.objects.count()       == 0
        assert MessageStatus.objects.count() == 0

        response = self.client.post(reverse('core:send'), data = json.dumps(self.correct_data), content_type = 'application/json', HTTP_CONCENT_CLIENT_PUBLIC_KEY = self.public_key)

        self.assertEqual(response.status_code, 202)  # pylint: disable=no-member
        self.assertEqual(len(Message.objects.all()),       1)
        self.assertEqual(Message.objects.last().type,      "MessageForceReportComputedTask")
        self.assertEqual(len(MessageStatus.objects.all()), 1)
        self.assertEqual(Message.objects.last().id,        MessageStatus.objects.last().message_id)

    @freeze_time("2017-11-17 10:00:00")
    def test_send_should_return_http_200_if_message_timeout(self):
        self.assertEqual(len(Message.objects.all()), 0)
        self.assertEqual(len(MessageStatus.objects.all()), 0)

        self.correct_data['message_task_to_compute']['deadline'] = self.message_timestamp - 1
        response = self.client.post(reverse('core:send'), data = json.dumps(self.correct_data), content_type = 'application/json', HTTP_CONCENT_CLIENT_PUBLIC_KEY = self.public_key)

        self.assertEqual(response.status_code, 200)  # pylint: disable=no-member
        self.assertEqual(response.json()['type'], 'MessageRejectReportComputedTask')  # pylint: disable=no-member

    @freeze_time("2017-11-17 10:00:00")
    def test_send_should_return_http_400_if_data_is_incorrect(self):
        data = {
            "type":      "MessageForceReportComputedTask",
            "timestamp": 1510911047,
            "message_task_to_compute":      {
                "type": "MessageTaskToCompute"
            }
        }

        response = self.client.post(reverse('core:send'), data = json.dumps(data), content_type = 'application/json', HTTP_CONCENT_CLIENT_PUBLIC_KEY = self.public_key)

        self.assertEqual(response.status_code, 400)  # pylint: disable=no-member
        self.assertIn('error', response.json().keys())

        self.correct_data['message_task_to_compute']['deadline'] = "1510909200"
        response = self.client.post(reverse('core:send'), data = json.dumps(self.correct_data), content_type = 'application/json', HTTP_CONCENT_CLIENT_PUBLIC_KEY = self.public_key)

        self.assertEqual(response.status_code, 400)  # pylint: disable=no-member
        self.assertIn('error', response.json().keys())

    @freeze_time("2017-11-17 10:00:00")
    def test_send_should_return_http_400_if_task_id_already_use(self):
        response_202 = self.client.post(reverse('core:send'), data = json.dumps(self.correct_data), content_type = 'application/json', HTTP_CONCENT_CLIENT_PUBLIC_KEY = self.public_key)

        self.assertIsInstance(response_202, HttpResponse)
        self.assertEqual(response_202.status_code, 202)

        response_400 = self.client.post(reverse('core:send'), data = json.dumps(self.correct_data), content_type = 'application/json', HTTP_CONCENT_CLIENT_PUBLIC_KEY = self.public_key)

        self.assertIsInstance(response_400, JsonResponse)
        self.assertEqual(response_400.status_code, 400)  # pylint: disable=no-member
        self.assertIn('error', response_400.json().keys())
