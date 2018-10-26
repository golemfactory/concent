import uuid

from django.conf import settings
from django.test import override_settings
from golem_messages import message

from common.helpers import parse_timestamp_to_utc_datetime
from core.message_handlers import store_message
from core.message_handlers import store_subtask
from core.models import Client
from core.models import StoredMessage
from core.models import Subtask
from core.subtask_helpers import are_all_stored_messages_compatible_with_protocol_version
from core.subtask_helpers import get_one_or_none
from core.tests.utils import ConcentIntegrationTestCase
from core.utils import hex_to_bytes_convert


class TestGetOneOrNoneSubtaskFromDatabase(ConcentIntegrationTestCase):

    def setUp(self) -> None:
        super().setUp()

        self.compute_task_def = self._get_deserialized_compute_task_def()

        self.task_to_compute = self._get_deserialized_task_to_compute(
            compute_task_def=self.compute_task_def,
        )
        self.report_computed_task = self._get_deserialized_report_computed_task(
            task_to_compute=self.task_to_compute,
        )

        self.subtask = store_subtask(
            task_id=self.task_to_compute.compute_task_def['task_id'],
            subtask_id=self.task_to_compute.compute_task_def['subtask_id'],
            provider_public_key=self.PROVIDER_PUBLIC_KEY,
            requestor_public_key=self.REQUESTOR_PUBLIC_KEY,
            state=Subtask.SubtaskState.FORCING_REPORT,
            next_deadline=int(self.task_to_compute.compute_task_def['deadline']) + settings.CONCENT_MESSAGING_TIME,
            task_to_compute=self.task_to_compute,
            report_computed_task=self.report_computed_task,
        )

    def test_that_if_only_object_id_given_and_object_exist_function_returns_expected_object(self) -> None:
        subtask = get_one_or_none(Subtask, subtask_id=self.task_to_compute.compute_task_def['subtask_id'])
        self.assertEqual(self.subtask, subtask)

    def test_that_if_more_conditions_given_and_object_exist_function_returns_expected_object(self) -> None:
        subtask = get_one_or_none(
            Subtask,
            subtask_id=self.task_to_compute.compute_task_def['subtask_id'],
            state=Subtask.SubtaskState.FORCING_REPORT.name,  # pylint: disable=no-member
        )
        self.assertEqual(self.subtask, subtask)

    def test_that_if_more_conditions_given_and_object_does_not_exist_function_returns_none(self) -> None:
        subtask = get_one_or_none(
            Subtask,
            subtask_id=str(uuid.uuid4()),
            state=Subtask.SubtaskState.FORCING_REPORT.name,  # pylint: disable=no-member
        )
        self.assertIsNone(subtask)

    def test_that_if_only_object_id_given_and_queryset_exist_function_returns_expected_object(self) -> None:
        subtask = get_one_or_none(Subtask.objects.select_for_update(), subtask_id=self.task_to_compute.compute_task_def['subtask_id'])
        self.assertEqual(self.subtask, subtask)

    def test_that_if_more_conditions_given_and_queryset_exist_function_returns_expected_object(self) -> None:
        subtask = get_one_or_none(
            Subtask.objects.select_for_update(),
            subtask_id=self.task_to_compute.compute_task_def['subtask_id'],
            state=Subtask.SubtaskState.FORCING_REPORT.name,  # pylint: disable=no-member
        )
        self.assertEqual(self.subtask, subtask)

    def test_that_if_more_conditions_given_and_queryset_does_not_exist_function_returns_none(self) -> None:
        subtask = get_one_or_none(
            Subtask.objects.select_for_update(),
            subtask_id=str(uuid.uuid4()),
            state=Subtask.SubtaskState.FORCING_REPORT.name,  # pylint: disable=no-member
        )
        self.assertIsNone(subtask)


class TestAreAllStoredMessagesCompatibleWithProtocolVersion(ConcentIntegrationTestCase):

    @staticmethod
    def _store_message_with_custom_protocol_version(
            golem_message: message.base.Message,
            task_id: str,
            subtask_id: str,
            protocol_version: str,
    ) -> StoredMessage:
        with override_settings(GOLEM_MESSAGES_VERSION=protocol_version):
            return store_message(
                golem_message,
                task_id,
                subtask_id,
            )

    def setUp(self) -> None:
        super().setUp()

        self.compute_task_def = self._get_deserialized_compute_task_def()

        self.task_to_compute = self._get_deserialized_task_to_compute(
            compute_task_def=self.compute_task_def,
        )
        self.report_computed_task = self._get_deserialized_report_computed_task(
            task_to_compute=self.task_to_compute,
        )
        self.provider_public_key = hex_to_bytes_convert(self.task_to_compute.provider_public_key)
        self.requestor_public_key = hex_to_bytes_convert(self.task_to_compute.requestor_public_key)

        self.provider = Client.objects.get_or_create_full_clean(self.provider_public_key)
        self.requestor = Client.objects.get_or_create_full_clean(self.requestor_public_key)
        self.size = 58

        self.task_id = self.task_to_compute.compute_task_def['task_id']
        self.subtask_id = self.task_to_compute.compute_task_def['subtask_id']

    def test_that_if_all_stored_messages_compatible_with_protocol_version_function_should_return_true(self):
        subtask = Subtask(
            task_id=self.task_to_compute.compute_task_def['task_id'],
            subtask_id=self.task_to_compute.compute_task_def['subtask_id'],
            provider=self.provider,
            requestor=self.requestor,
            result_package_size=self.size,
            state=Subtask.SubtaskState.REPORTED.name,  # pylint: disable=no-member
            next_deadline=None,
            computation_deadline=parse_timestamp_to_utc_datetime(self.compute_task_def['deadline']),
            task_to_compute=store_message(self.task_to_compute, self.task_id, self.subtask_id),
            want_to_compute_task=store_message(self.task_to_compute.want_to_compute_task, self.task_id, self.subtask_id),
            report_computed_task=store_message(self.report_computed_task, self.task_id, self.subtask_id),
        )
        subtask.save()

        self.assertTrue(
            are_all_stored_messages_compatible_with_protocol_version(
                self.report_computed_task,
                self.provider_public_key,
            )
        )

    def test_that_if_one_stored_messages_has_incompatible_protocol_version_function_should_return_false(self):
        subtask = Subtask(
            task_id=self.task_to_compute.compute_task_def['task_id'],
            subtask_id=self.task_to_compute.compute_task_def['subtask_id'],
            provider=self.provider,
            requestor=self.requestor,
            result_package_size=self.size,
            state=Subtask.SubtaskState.REPORTED.name,  # pylint: disable=no-member
            next_deadline=None,
            computation_deadline=parse_timestamp_to_utc_datetime(self.compute_task_def['deadline']),
            task_to_compute=self._store_message_with_custom_protocol_version(
                self.task_to_compute,
                self.task_id,
                self.subtask_id,
                '1.11.1',
            ),
            want_to_compute_task=store_message(self.task_to_compute.want_to_compute_task, self.task_id, self.subtask_id),
            report_computed_task=store_message(self.report_computed_task, self.task_id, self.subtask_id),
        )
        subtask.save()

        self.assertFalse(
            are_all_stored_messages_compatible_with_protocol_version(
                self.report_computed_task,
                self.provider_public_key,
            )
        )
