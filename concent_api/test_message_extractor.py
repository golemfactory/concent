from unittest import TestCase

from golem_messages.message import ComputeTaskDef
from message_extractor import MessageExtractor

from assertpy import assert_that


class TestMessageExtractor(TestCase):
    def test_that_force_get_task_result_message_is_created_when_appropriate_dict_is_given(self):
        self.fail("not implemented yet")

    def test_that_exception_is_raised_when_wrong_dict_is_given(self):  # TODO: what exception?
        self.fail("not implemented yet")

    def test_that_compute_task_def_is_created_when_appropriate_dict_is_given(self):
        task_id = 2
        timestamp = 1510390800
        deadline = 1510394400
        input = {
            "name": "compute_task_def",
            "body": {
                "timestamp": str(timestamp),
                "task_id": str(task_id),
                "deadline": str(deadline)
            }
        }

        task = MessageExtractor().extract_message(input)

        assert_that(task).is_instance_of(ComputeTaskDef)
        assert_that(task.task_id).is_equal_to(task_id)
        assert_that(task.timestamp).is_equal_to(timestamp)
        assert_that(task.deadline).is_equal_to(deadline)
