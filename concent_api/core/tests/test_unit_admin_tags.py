import datetime
import hashlib
from freezegun import freeze_time
from golem_messages.message.concents import ForceGetTaskResult
from golem_messages.factories.tasks import ReportComputedTaskFactory
from common.helpers import get_current_utc_timestamp
from core.message_handlers import store_subtask
from core.models import Subtask
from core.templatetags.admin_tags import get_longest_lasting_subtask_timestamp, get_time_until_concent_can_be_shut_down
from core.tests.utils import ConcentIntegrationTestCase
from core.utils import hex_to_bytes_convert
from api_testing_common import create_signed_task_to_compute
from api_testing_common import timestamp_to_isoformat


class TestAdminTagsQuerySet(ConcentIntegrationTestCase):
    def store_report_computed_task_as_subtask(self, current_time, task_id, deadline, next_deadline, subtask_state):  # pylint: disable=no-self-use
        subtask_id = task_id + '1'
        file_content = '1'
        file_size = len(file_content)
        file_check_sum = 'sha1:' + hashlib.sha1(file_content.encode()).hexdigest()
        task_to_compute = create_signed_task_to_compute(
            task_id=task_id,
            subtask_id=subtask_id,
            deadline=deadline,
            price=0,
            timestamp=timestamp_to_isoformat(current_time),
        )
        report_computed_task = ReportComputedTaskFactory(
            task_to_compute=task_to_compute,
            size=file_size,
            package_hash=file_check_sum,
            subtask_id=subtask_id,
        )
        force_get_task_result = ForceGetTaskResult(
            report_computed_task=report_computed_task,
        )
        store_subtask(
            task_id=report_computed_task.task_to_compute.task_id,
            subtask_id=report_computed_task.task_to_compute.subtask_id,
            provider_public_key=hex_to_bytes_convert(report_computed_task.task_to_compute.provider_public_key),
            requestor_public_key=hex_to_bytes_convert(report_computed_task.task_to_compute.requestor_public_key),
            state=subtask_state,
            next_deadline=next_deadline,
            task_to_compute=report_computed_task.task_to_compute,
            report_computed_task=report_computed_task,
            force_get_task_result=force_get_task_result,
        )

    def test_that_longest_lasting_subtask_timestamp_is_qiven_when_subtasks_with_download_deadline_or_next_deadline_exists_in_database(self):
        current_time = 1836595582
        self.store_report_computed_task_as_subtask(
            current_time=current_time,
            deadline=current_time + 60,
            next_deadline=None,
            task_id='longest',
            subtask_state=Subtask.SubtaskState.RESULT_UPLOADED,
        )
        longest_lasting_subtask_timestamp = get_longest_lasting_subtask_timestamp()

        self.store_report_computed_task_as_subtask(
            current_time=current_time,
            deadline=current_time + 16,
            next_deadline=None,
            task_id='shorter_1',
            subtask_state=Subtask.SubtaskState.RESULT_UPLOADED,
        )
        self.store_report_computed_task_as_subtask(
            current_time=current_time,
            deadline=current_time + 13,
            next_deadline=current_time + 14,
            task_id='shorter_2',
            subtask_state=Subtask.SubtaskState.FORCING_RESULT_TRANSFER,
        )
        self.store_report_computed_task_as_subtask(
            current_time=current_time,
            deadline=current_time + 9,
            next_deadline=current_time + 10,
            task_id='shorter_3',
            subtask_state=Subtask.SubtaskState.FORCING_RESULT_TRANSFER,
        )
        self.store_report_computed_task_as_subtask(
            current_time=current_time,
            deadline=current_time + 11,
            next_deadline=current_time + 12,
            task_id='shorter_4',
            subtask_state=Subtask.SubtaskState.FORCING_RESULT_TRANSFER,
        )
        self.store_report_computed_task_as_subtask(
            current_time=current_time,
            deadline=current_time + 15,
            next_deadline=None,
            task_id='shorter_5',
            subtask_state=Subtask.SubtaskState.RESULT_UPLOADED,
        )
        self.assertEqual(get_longest_lasting_subtask_timestamp(), longest_lasting_subtask_timestamp)

        self.store_report_computed_task_as_subtask(
            current_time=current_time,
            deadline=current_time + 11,
            next_deadline=longest_lasting_subtask_timestamp + 1,
            task_id='longest_2',
            subtask_state=Subtask.SubtaskState.FORCING_RESULT_TRANSFER,
        )
        self.assertNotEqual(get_longest_lasting_subtask_timestamp(), longest_lasting_subtask_timestamp)

    def test_that_longest_lasting_subtask_timestamp_method_returns_none_when_empty_database_is_given(self):
        self.assertEqual(get_longest_lasting_subtask_timestamp(), None)

    def test_that_get_time_until_concent_can_be_shut_down_method_returns_zero_when_empty_database_is_given(self):
        self.assertEqual(get_time_until_concent_can_be_shut_down(), datetime.timedelta(0))

    def test_that_get_time_until_concent_can_be_shut_down_method_returns_time_when_not_outdated_tasks_are_in_database(self):
        with freeze_time():
            current_time = get_current_utc_timestamp()

            self.store_report_computed_task_as_subtask(
                current_time,
                deadline=current_time + 16,
                next_deadline=None,
                task_id='subtask',
                subtask_state=Subtask.SubtaskState.RESULT_UPLOADED,
            )

            self.assertEqual(
                get_time_until_concent_can_be_shut_down(),
                datetime.timedelta(seconds=get_longest_lasting_subtask_timestamp() - current_time)
            )

    def test_that_get_time_until_concent_can_be_shut_down_method_returns_zero_when_only_outdated_tasks_are_in_database(self):
        with freeze_time():
            current_time = get_current_utc_timestamp()

            self.store_report_computed_task_as_subtask(
                current_time,
                deadline=current_time - 200,
                next_deadline=None,
                task_id='subtask',
                subtask_state=Subtask.SubtaskState.RESULT_UPLOADED,
            )

            self.assertEqual(get_time_until_concent_can_be_shut_down(), datetime.timedelta(0))
