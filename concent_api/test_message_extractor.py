from unittest import TestCase

from golem_messages.message import ComputeTaskDef
from message_extractor import MessageExtractor, convert_message_name

from assertpy import assert_that


class TestMessageExtractor(TestCase):
    def test_that_force_get_task_result_message_is_created_when_appropriate_dict_is_given(self):
        self.fail("not implemented yet")

    def test_that_exception_is_raised_when_wrong_dict_is_given(self):  # TODO: what exception?
        self.fail("not implemented yet")

    def test_that_compute_task_def_is_created_when_appropriate_dict_is_given(self):
        task_id = "2"
        subtask_id = "12"
        deadline = 1510394400
        input = {
            "name": "compute_task_def",
            "body": {
                "task_id": task_id,
                "subtask_id": subtask_id,
                "deadline": deadline
            }
        }

        task = MessageExtractor().extract_message(input)
        assert_that(task).is_instance_of(ComputeTaskDef)
        assert_that(task["task_id"]).is_equal_to(task_id)
        assert_that(task["subtask_id"]).is_equal_to(subtask_id)
        assert_that(task["deadline"]).is_equal_to(deadline)


class TestMessageConverter(TestCase):
    def test_that_message_is_converted_when_source_format_is_given(self):
        input = "report_computed_task"
        task = convert_message_name(input)
        assert_that(task).is_equal_to('ReportComputedTask')

    def test_that_message_is_converted_when_source_format_is_given_and_one_letter_is_uppercase(self):
        input = "report_Computed_task"
        task = convert_message_name(input)
        assert_that(task).is_equal_to('ReportComputedTask')

    def test_that_message_is_not_converted_when_target_format_is_given(self):
        input = "ReportComputedTask"
        task = convert_message_name(input)
        assert_that(task).is_equal_to('ReportComputedTask')

    def test_that_empty_string_is_returned_when_empty_message_is_given(self):
        input = ""
        task = convert_message_name(input)
        assert_that(task).is_equal_to('')
