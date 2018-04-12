import os
import sys
from base64 import b64decode
from unittest import TestCase, skip, expectedFailure

from golem_messages.message import ComputeTaskDef, TaskToCompute, ReportComputedTask
from golem_messages.message.concents import ForceGetTaskResult
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from command_line_tool.message_extractor import MessageExtractor, convert_message_name, split_uppercase
from assertpy import assert_that


class TestMessageExtractor(TestCase):

    def test_that_message_is_reconverted_when_source_format_is_given(self):
        input = 'ForceComputedTask'
        task = split_uppercase(input)
        assert_that(task).is_equal_to('force_computed_task')

    def test_that_exception_is_raised_when_wrong_dict_is_given(self):  # TODO: what exception?
        # assert_that()
        self.fail("not implemented yet")

    def test_that_force_get_task_result_message_is_created_when_appropriate_dict_is_given(self):
        task_id = "2"
        subtask_id = "12"
        deadline = 1510394400

        requestor_public_key = "mrdOXP6Owe3i48G29RHPVU6wewvuUNuNxFB+kPTDnmI21+p5ShttCSUAbHOVm8OIUF9hEluc1+lICJZGkFSSOA=="
        requestor_ethereum_public_key = "b'T8ER1hrI9hH0Zyu/m6u9H2K4rc1mC/dlCqK0PSzBSwvKBdHfysmrIIsQMyvecDU+TIkhDmq93Olfo5h2FSGRjw=='"
        provider_public_key = "PKn3TUiXdfeoHjoeu6PEDMD5JqrdmyeKlbG5rWUpgAs6qbKj7k9bm8vvkmhn40RkMykho6uAHsYVy72ZBYUelQ=="
        provider_ethereum_public_key = "b'A9LjJQJDc9ugt+kxA/r58chrekDr3VFZpfjU6Pv9dTP1gGLOvKEUxGwlB1ffDAbdWY8P0Pa37Mt6muFpJKC1mA=='=="

        address = "10.10.10.1"
        size = 1048576  # bytes
        # package_hash = "packagehash"
        input = {
            "name": "force_get_task_result",
            "body": {
                "report_computed_task": {
                    "subtask_id": subtask_id,
                    "address": address,
                    "size": size,
                    # "package_hash": package_hash,
                    "task_to_compute": {
                        "requestor_public_key": requestor_public_key,
                        "requestor_ethereum_public_key": requestor_ethereum_public_key,
                        "provider_public_key": provider_public_key,
                        "provider_ethereum_public_key": provider_ethereum_public_key,
                        "compute_task_def": {
                            "task_id": task_id,
                            "subtask_id": subtask_id,
                            "deadline": deadline,
                        }
                    }
                }
            }
        }

        message = MessageExtractor().extract_message(input)
        assert_that(message).is_instance_of(ForceGetTaskResult)
        report_computed_task = message.report_computed_task
        assert_that(report_computed_task).is_instance_of(ReportComputedTask)
        assert_that(report_computed_task.subtask_id).is_equal_to(subtask_id)
        assert_that(report_computed_task.address).is_equal_to(address)
        assert_that(report_computed_task.size).is_equal_to(size)
        # assert_that(message.report_computed_task.package_hash).is_equal_to(package_hash)

        task_to_compute = report_computed_task.task_to_compute
        assert_that(task_to_compute.requestor_public_key).is_equal_to(b64decode(requestor_public_key))
        assert_that(task_to_compute.requestor_ethereum_public_key).is_equal_to(b64decode(requestor_ethereum_public_key))
        assert_that(task_to_compute.provider_public_key).is_equal_to(b64decode(provider_public_key))
        assert_that(task_to_compute.provider_ethereum_public_key).is_equal_to(b64decode(provider_ethereum_public_key))
        assert_that(task_to_compute).is_instance_of(TaskToCompute)

        compute_task_def = task_to_compute.compute_task_def
        assert_that(compute_task_def).is_instance_of(ComputeTaskDef)
        assert_that(compute_task_def["task_id"]).is_equal_to(task_id)
        assert_that(compute_task_def["subtask_id"]).is_equal_to(subtask_id)
        assert_that(compute_task_def["deadline"]).is_equal_to(deadline)

    def test_that_report_computed_task_message_is_created_when_appropriate_dict_is_given(self):
        task_id = "2"
        subtask_id = "12"
        deadline = 1510394400

        requestor_public_key = "mrdOXP6Owe3i48G29RHPVU6wewvuUNuNxFB+kPTDnmI21+p5ShttCSUAbHOVm8OIUF9hEluc1+lICJZGkFSSOA=="
        requestor_ethereum_public_key = "b'T8ER1hrI9hH0Zyu/m6u9H2K4rc1mC/dlCqK0PSzBSwvKBdHfysmrIIsQMyvecDU+TIkhDmq93Olfo5h2FSGRjw=='"
        provider_public_key = "PKn3TUiXdfeoHjoeu6PEDMD5JqrdmyeKlbG5rWUpgAs6qbKj7k9bm8vvkmhn40RkMykho6uAHsYVy72ZBYUelQ=="
        provider_ethereum_public_key = "b'A9LjJQJDc9ugt+kxA/r58chrekDr3VFZpfjU6Pv9dTP1gGLOvKEUxGwlB1ffDAbdWY8P0Pa37Mt6muFpJKC1mA=='=="

        address = "10.10.10.1"
        size = 1048576  # bytes
        # package_hash = "packagehash"
        input = {
            "name": "report_computed_task",
            "body": {
                "subtask_id": subtask_id,
                "address": address,
                "size": size,
                # "package_hash": package_hash,
                "task_to_compute": {
                    "requestor_public_key": requestor_public_key,
                    "requestor_ethereum_public_key": requestor_ethereum_public_key,
                    "provider_public_key": provider_public_key,
                    "provider_ethereum_public_key": provider_ethereum_public_key,
                    "compute_task_def": {
                        "task_id": task_id,
                        "subtask_id": subtask_id,
                        "deadline": deadline,
                    }
                }
            }
        }

        task = MessageExtractor().extract_message(input)
        assert_that(task).is_instance_of(ReportComputedTask)
        assert_that(task.subtask_id).is_equal_to(subtask_id)
        assert_that(task.address).is_equal_to(address)
        assert_that(task.size).is_equal_to(size)
        # assert_that(task.package_hash).is_equal_to(package_hash)

        assert_that(task.task_to_compute.requestor_public_key).is_equal_to(b64decode(requestor_public_key))
        assert_that(task.task_to_compute.requestor_ethereum_public_key).is_equal_to(
            b64decode(requestor_ethereum_public_key))
        assert_that(task.task_to_compute.provider_public_key).is_equal_to(b64decode(provider_public_key))
        assert_that(task.task_to_compute.provider_ethereum_public_key).is_equal_to(
            b64decode(provider_ethereum_public_key))
        assert_that(task.task_to_compute).is_instance_of(TaskToCompute)

        assert_that(task.task_to_compute.compute_task_def).is_instance_of(ComputeTaskDef)
        assert_that(task.task_to_compute.compute_task_def["task_id"]).is_equal_to(task_id)
        assert_that(task.task_to_compute.compute_task_def["subtask_id"]).is_equal_to(subtask_id)
        assert_that(task.task_to_compute.compute_task_def["deadline"]).is_equal_to(deadline)

    def test_that_task_to_compute_message_is_created_when_appropriate_dict_is_given(self):
        task_id = "2"
        subtask_id = "12"
        deadline = 1510394400

        requestor_public_key = "mrdOXP6Owe3i48G29RHPVU6wewvuUNuNxFB+kPTDnmI21+p5ShttCSUAbHOVm8OIUF9hEluc1+lICJZGkFSSOA=="
        requestor_ethereum_public_key = "b'T8ER1hrI9hH0Zyu/m6u9H2K4rc1mC/dlCqK0PSzBSwvKBdHfysmrIIsQMyvecDU+TIkhDmq93Olfo5h2FSGRjw=='"
        provider_public_key = "PKn3TUiXdfeoHjoeu6PEDMD5JqrdmyeKlbG5rWUpgAs6qbKj7k9bm8vvkmhn40RkMykho6uAHsYVy72ZBYUelQ=="
        provider_ethereum_public_key = "b'A9LjJQJDc9ugt+kxA/r58chrekDr3VFZpfjU6Pv9dTP1gGLOvKEUxGwlB1ffDAbdWY8P0Pa37Mt6muFpJKC1mA=='=="

        input = {
            "name": "task_to_compute",
            "body": {
                "requestor_public_key": requestor_public_key,
                "requestor_ethereum_public_key": requestor_ethereum_public_key,
                "provider_public_key": provider_public_key,
                "provider_ethereum_public_key": provider_ethereum_public_key,
                "compute_task_def": {
                    "task_id": task_id,
                    "subtask_id": subtask_id,
                    "deadline": deadline,
                }
            }
        }

        task = MessageExtractor().extract_message(input)
        assert_that(task).is_instance_of(TaskToCompute)
        assert_that(task.requestor_public_key).is_equal_to(b64decode(requestor_public_key))
        assert_that(task.requestor_ethereum_public_key).is_equal_to(b64decode(requestor_ethereum_public_key))
        assert_that(task.provider_public_key).is_equal_to(b64decode(provider_public_key))
        assert_that(task.provider_ethereum_public_key).is_equal_to(b64decode(provider_ethereum_public_key))
        assert_that(task.compute_task_def).is_instance_of(ComputeTaskDef)
        assert_that(task.compute_task_def["task_id"]).is_equal_to(task_id)
        assert_that(task.compute_task_def["subtask_id"]).is_equal_to(subtask_id)
        assert_that(task.compute_task_def["deadline"]).is_equal_to(deadline)

    def test_that_compute_task_def_is_created_when_appropriate_dict_is_given(self):
        task_id = "2"
        subtask_id = "12"
        deadline = 1510394400
        input = {
            "name": "compute_task_def",
            "body": {
                "task_id": task_id,
                "subtask_id": subtask_id,
                "deadline": deadline,
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
