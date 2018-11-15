from base64 import b64decode
from unittest import skip
from unittest import TestCase
from golem_messages.message import ComputeTaskDef
from golem_messages.message import ReportComputedTask
from golem_messages.message import TaskToCompute
from golem_messages.message.concents import ForceGetTaskResult
from assertpy import assert_that
from command_line_tool.message_extractor import convert_message_name
from command_line_tool.message_extractor import MessageExtractor
from command_line_tool.message_extractor import split_uppercase
from core.tests.utils import generate_uuid_for_tests


class TestSplitUppercase(TestCase):
    @staticmethod
    def test_that_message_is_reconverted_when_source_format_is_given():
        input_data = 'ForceComputedTask'
        message_name = split_uppercase(input_data)
        assert_that(message_name).is_equal_to('force_computed_task')


class TestMessageExtractor(TestCase):
    def setUp(self):
        self.size = 1048576
        self.address = "10.10.10.1"
        self.provider_ethereum_public_key = "b'A9LjJQJDc9ugt+kxA/r58chrekDr3VFZpfjU6Pv9dTP1gGLOvKEUxGwlB1ffDAbdWY8P0Pa37Mt6muFpJKC1mA=='=="
        self.provider_public_key = "PKn3TUiXdfeoHjoeu6PEDMD5JqrdmyeKlbG5rWUpgAs6qbKj7k9bm8vvkmhn40RkMykho6uAHsYVy72ZBYUelQ=="
        self.requestor_ethereum_public_key = "b'T8ER1hrI9hH0Zyu/m6u9H2K4rc1mC/dlCqK0PSzBSwvKBdHfysmrIIsQMyvecDU+TIkhDmq93Olfo5h2FSGRjw=='"
        self.requestor_public_key = "mrdOXP6Owe3i48G29RHPVU6wewvuUNuNxFB+kPTDnmI21+p5ShttCSUAbHOVm8OIUF9hEluc1+lICJZGkFSSOA=="
        self.deadline = 1510394400
        self.subtask_id = generate_uuid_for_tests()
        self.task_id = generate_uuid_for_tests()

    def test_that_exception_is_raised_when_wrong_dict_is_given(self):
        input_data = {
            "name": "report_computed_task",
            "body": {
                "address": self.address,
                "size": self.size,
                "task_to_compute": {
                    "requestor_public_key": self.requestor_public_key,
                    "requestor_ethereum_public_key": self.requestor_ethereum_public_key,
                    "provider_public_key": self.provider_public_key,
                    "provider_ethereum_public_key": self.provider_ethereum_public_key,
                    "compute_task_def": {
                        "task_id": self.task_id,
                        "subtask_id": self.subtask_id,
                        "deadline": self.deadline,
                    },
                    "task_to_compute": {
                        "requestor_public_key": self.requestor_public_key,
                        "requestor_ethereum_public_key": self.requestor_ethereum_public_key,
                        "provider_public_key": self.provider_public_key,
                        "provider_ethereum_public_key": self.provider_ethereum_public_key,
                        "compute_task_def": {
                            "task_id": self.task_id,
                            "subtask_id": self.subtask_id,
                            "deadline": self.deadline,
                        }
                    }
                }
            }
        }

        with self.assertRaises(Exception) as context:
            MessageExtractor(self.requestor_public_key, self.provider_public_key).extract_message(input_data)
        self.assertTrue("Invalid message definition" in str(context.exception))

    @skip("MessageExtractor need fixing")
    def test_that_force_get_task_result_message_is_created_when_appropriate_dict_is_given(self):
        input_data = {
            "name": "force_get_task_result",
            "body": {
                "report_computed_task": {
                    "address": self.address,
                    "size": self.size,
                    "task_to_compute": {
                        "requestor_public_key": self.requestor_public_key,
                        "requestor_ethereum_public_key": self.requestor_ethereum_public_key,
                        "provider_public_key": self.provider_public_key,
                        "provider_ethereum_public_key": self.provider_ethereum_public_key,
                        "compute_task_def": {
                            "task_id": self.task_id,
                            "subtask_id": self.subtask_id,
                            "deadline": self.deadline,
                        }
                    }
                }
            }
        }

        force_get_task_result = MessageExtractor(self.requestor_public_key, self.provider_public_key).extract_message(input_data)

        assert_that(force_get_task_result).is_instance_of(ForceGetTaskResult)
        report_computed_task = force_get_task_result.report_computed_task
        self._assert_correct_report_computed_task(report_computed_task)
        task_to_compute = report_computed_task.task_to_compute
        self._assert_correct_task_to_compute(task_to_compute)
        compute_task_def = task_to_compute.compute_task_def
        self._assert_correct_compute_task_def(compute_task_def)

    @skip("MessageExtractor need fixing")
    def test_that_report_computed_task_message_is_created_when_appropriate_dict_is_given(self):
        input_data = {
            "name": "report_computed_task",
            "body": {
                "address": self.address,
                "size": self.size,
                "task_to_compute": {
                    "requestor_public_key": self.requestor_public_key,
                    "requestor_ethereum_public_key": self.requestor_ethereum_public_key,
                    "provider_public_key": self.provider_public_key,
                    "provider_ethereum_public_key": self.provider_ethereum_public_key,
                    "compute_task_def": {
                        "task_id": self.task_id,
                        "subtask_id": self.subtask_id,
                        "deadline": self.deadline,
                    }
                }
            }
        }

        report_computed_task = MessageExtractor(self.requestor_public_key, self.provider_public_key).extract_message(input_data)

        self._assert_correct_report_computed_task(report_computed_task)
        self._assert_correct_task_to_compute(report_computed_task.task_to_compute)
        compute_task_def = report_computed_task.task_to_compute.compute_task_def
        self._assert_correct_compute_task_def(compute_task_def)

    @skip("MessageExtractor need fixing")
    def test_that_task_to_compute_message_is_created_when_appropriate_dict_is_given(self):
        input_data = {
            "name": "task_to_compute",
            "body": {
                "requestor_public_key": self.requestor_public_key,
                "requestor_ethereum_public_key": self.requestor_ethereum_public_key,
                "want_to_compute_task": {
                    "provider_public_key": self.provider_public_key,
                    "provider_ethereum_public_key": self.provider_ethereum_public_key,
                },
                "compute_task_def": {
                    "task_id": self.task_id,
                    "subtask_id": self.subtask_id,
                    "deadline": self.deadline,
                }

            }
        }

        task_to_compute = MessageExtractor(self.requestor_public_key, self.provider_public_key).extract_message(input_data)
        self._assert_correct_task_to_compute(task_to_compute)
        self._assert_correct_compute_task_def(task_to_compute.compute_task_def)

    def test_that_compute_task_def_is_created_when_appropriate_dict_is_given(self):
        input_data = {
            "name": "compute_task_def",
            "body": {
                "task_id": self.task_id,
                "subtask_id": self.subtask_id,
                "deadline": self.deadline,
            }
        }

        compute_task_def = MessageExtractor(self.requestor_public_key, self.provider_public_key).extract_message(input_data)
        self._assert_correct_compute_task_def(compute_task_def)

    def _assert_correct_report_computed_task(self, report_computed_task):
        assert_that(report_computed_task).is_instance_of(ReportComputedTask)
        assert_that(report_computed_task.subtask_id).is_equal_to(self.subtask_id)
        assert_that(report_computed_task.address).is_equal_to(self.address)
        assert_that(report_computed_task.size).is_equal_to(self.size)

    def _assert_correct_task_to_compute(self, task_to_compute):
        assert_that(task_to_compute).is_instance_of(TaskToCompute)
        assert_that(task_to_compute.requestor_public_key).is_equal_to(b64decode(self.requestor_public_key))
        assert_that(task_to_compute.requestor_ethereum_public_key).is_equal_to(
            b64decode(self.requestor_ethereum_public_key))
        assert_that(task_to_compute.provider_public_key).is_equal_to(b64decode(self.provider_public_key))
        assert_that(task_to_compute.provider_ethereum_public_key).is_equal_to(
            b64decode(self.provider_ethereum_public_key))

    def _assert_correct_compute_task_def(self, compute_task_def):
        assert_that(compute_task_def).is_instance_of(ComputeTaskDef)
        assert_that(compute_task_def["task_id"]).is_equal_to(self.task_id)
        assert_that(compute_task_def["subtask_id"]).is_equal_to(self.subtask_id)
        assert_that(compute_task_def["deadline"]).is_equal_to(self.deadline)


class TestMessageConverter(TestCase):
    @staticmethod
    def test_that_message_is_converted_when_source_format_is_given():
        input_data = "report_computed_task"
        message_name = convert_message_name(input_data)
        assert_that(message_name).is_equal_to('ReportComputedTask')

    @staticmethod
    def test_that_message_is_converted_when_source_format_is_given_and_one_letter_is_uppercase():
        input_data = "report_Computed_task"
        message_name = convert_message_name(input_data)
        assert_that(message_name).is_equal_to('ReportComputedTask')

    @staticmethod
    def test_that_message_is_not_converted_when_target_format_is_given():
        input_data = "ReportComputedTask"
        message_name = convert_message_name(input_data)
        assert_that(message_name).is_equal_to('ReportComputedTask')

    @staticmethod
    def test_that_empty_string_is_returned_when_empty_message_is_given():
        input_data = ""
        message_name = convert_message_name(input_data)
        assert_that(message_name).is_equal_to('')
