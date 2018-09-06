from django.conf import settings

from core.message_handlers import store_subtask
from core.models import Subtask
from core.subtask_helpers import get_one_or_none_subtasks_from_database
from core.tests.utils import ConcentIntegrationTestCase


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

    def test_that_if_only_subtask_id_given_and_subtask_exist_function_returns_subtask(self) -> None:
        subtask = get_one_or_none_subtasks_from_database(self.task_to_compute.compute_task_def['subtask_id'])
        self.assertEqual(self.subtask, subtask)

    def test_that_if_subtask_id_and_optional_dict_given_and_subtask_exist_function_returns_subtask(self) -> None:
        subtask = get_one_or_none_subtasks_from_database(
            subtask_id=self.task_to_compute.compute_task_def['subtask_id'],
            optional_condition_dict={'state': Subtask.SubtaskState.FORCING_REPORT.name},  # pylint: disable=no-member
        )
        self.assertEqual(self.subtask, subtask)

    def test_that_if_subtask_id_and_optional_dict_given_and_subtask_does_not_exist_function_returns_none(self) -> None:
        subtask = get_one_or_none_subtasks_from_database(
            subtask_id=self.task_to_compute.compute_task_def['subtask_id'],
            optional_condition_dict={'state': Subtask.SubtaskState.REPORTED.name},  # pylint: disable=no-member
        )
        self.assertIsNone(subtask)
