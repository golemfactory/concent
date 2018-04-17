from unittest import TestCase

from golem_messages.message.tasks import ReportComputedTask
from golem_messages.message.tasks import SubtaskResultsRejected
from golem_messages.message.tasks import TaskToCompute

from core.exceptions import Http400
from core.validation import validate_golem_message_subtask_results_rejected


class TestValidateGolemMessageSubtaskResultsRejected(TestCase):
    def test_that_exception_is_raised_when_subtask_results_rejected_is_of_wrong_type(self):
        with self.assertRaises(Http400):
            validate_golem_message_subtask_results_rejected(None)

    def test_that_exception_is_raised_when_subtask_results_rejected_contains_invalid_task_to_compute(self):
        report_computed_task = ReportComputedTask(task_to_compute=TaskToCompute())
        subtask_results_rejected = SubtaskResultsRejected(report_computed_task=report_computed_task)
        with self.assertRaises(Http400):
            validate_golem_message_subtask_results_rejected(subtask_results_rejected)
