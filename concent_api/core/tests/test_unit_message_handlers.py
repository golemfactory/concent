from unittest import TestCase

import mock
from golem_messages.message.tasks import SubtaskResultsAccepted
from core.message_handlers import are_ids_unique_in_subtask_results_accepted_list


def mocked_subtask_results_accepted_list(subtask_id_1, subtask_id_2, task_id_1, task_id_2):
    subtask_results_accepted_list = [
        mock.create_autospec(spec=SubtaskResultsAccepted, spec_set=True),
        mock.create_autospec(spec=SubtaskResultsAccepted, spec_set=True)
    ]
    subtask_results_accepted_list[0].subtask_id = subtask_id_1
    subtask_results_accepted_list[0].task_id = task_id_1
    subtask_results_accepted_list[1].subtask_id = subtask_id_2
    subtask_results_accepted_list[1].task_id = task_id_2
    return subtask_results_accepted_list


class TestMessageHandlers(TestCase):
    def test_that_function_returns_true_when_ids_are_diffrent(self):
        response = are_ids_unique_in_subtask_results_accepted_list(mocked_subtask_results_accepted_list(
            subtask_id_1 = '1',
            subtask_id_2 = '2',
            task_id_1 = '2',
            task_id_2 = '2',
        ))
        self.assertTrue(response)

        response_2 = are_ids_unique_in_subtask_results_accepted_list(mocked_subtask_results_accepted_list(
            subtask_id_1 = '1',
            subtask_id_2 = '1',
            task_id_1 = '1',
            task_id_2 = '2',
        ))
        self.assertTrue(response_2)

    def test_that_function_returns_false_when_ids_are_the_same(self):
        response = are_ids_unique_in_subtask_results_accepted_list(mocked_subtask_results_accepted_list(
            subtask_id_1 = '1',
            subtask_id_2 = '1',
            task_id_1 = '1',
            task_id_2 = '1',
        ))
        self.assertFalse(response)
