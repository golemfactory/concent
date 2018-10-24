from django.core.exceptions import ValidationError
from golem_messages.utils import encode_hex
import pytest

from golem_messages import factories
from golem_messages import message
from core.constants import MOCK_TRANSACTION
from core.message_handlers import store_subtask
from core.models import Client
from core.models import DepositAccount
from core.models import DepositClaim
from core.models import Subtask
from core.tests.utils import ConcentIntegrationTestCase
from core.utils import hex_to_bytes_convert


# This all data has to be prepared in separate function because pytest parametrize can't get variables from SetUp()
# Function allows to prepare 2 packs of data: correct and incorrect.
def _get_data_list(correct):
    task_to_compute = factories.tasks.TaskToComputeFactory()
    different_task_to_compute = factories.tasks.TaskToComputeFactory()
    report_computed_task = factories.tasks.ReportComputedTaskFactory(
        task_to_compute=task_to_compute
    )
    different_report_computed_task = factories.tasks.ReportComputedTaskFactory(
        task_to_compute=different_task_to_compute
    )
    ack_report_computed_task = factories.tasks.AckReportComputedTaskFactory(
        report_computed_task=report_computed_task
    )
    different_ack_report_computed_task = factories.tasks.AckReportComputedTaskFactory(
        report_computed_task=different_report_computed_task
    )
    reject_report_computed_task_with_task_to_compute = factories.tasks.RejectReportComputedTaskFactory(
        attached_task_to_compute=task_to_compute,
        reason=message.tasks.RejectReportComputedTask.REASON.SubtaskTimeLimitExceeded
    )
    different_reject_report_computed_task_with_task_to_compute = factories.tasks.RejectReportComputedTaskFactory(
        attached_task_to_compute=different_task_to_compute,
        reason=message.tasks.RejectReportComputedTask.REASON.SubtaskTimeLimitExceeded
    )
    reject_report_computed_task_with_task_failure = factories.tasks.RejectReportComputedTaskFactory(
        task_failure=factories.tasks.TaskFailureFactory(task_to_compute=task_to_compute),
        reason=message.tasks.RejectReportComputedTask.REASON.GotMessageTaskFailure,
    )
    different_reject_report_computed_task_with_task_failure = factories.tasks.RejectReportComputedTaskFactory(
        task_failure=factories.tasks.TaskFailureFactory(task_to_compute=different_task_to_compute),
        reason=message.tasks.RejectReportComputedTask.REASON.GotMessageTaskFailure,
    )
    reject_report_computed_task_with_cannot_compute_task = factories.tasks.RejectReportComputedTaskFactory(
        cannot_compute_task=factories.tasks.CannotComputeTaskFactory(task_to_compute=task_to_compute),
        reason=message.tasks.RejectReportComputedTask.REASON.GotMessageCannotComputeTask,
    )
    different_reject_report_computed_task_with_cannot_compute_task = factories.tasks.RejectReportComputedTaskFactory(
        cannot_compute_task=factories.tasks.CannotComputeTaskFactory(task_to_compute=different_task_to_compute),
        reason=message.tasks.RejectReportComputedTask.REASON.GotMessageCannotComputeTask,
    )
    reject_report_computed_task_without_reason_and_task_to_compute = message.tasks.RejectReportComputedTask()
    force_get_task_result = factories.concents.ForceGetTaskResultFactory(
        report_computed_task=report_computed_task
    )
    different_force_get_task_result = factories.concents.ForceGetTaskResultFactory(
        report_computed_task=different_report_computed_task
    )
    subtask_results_rejected = factories.tasks.SubtaskResultsRejectedFactory(
        report_computed_task=report_computed_task
    )
    different_subtask_results_rejected = factories.tasks.SubtaskResultsRejectedFactory(
        report_computed_task=different_report_computed_task
    )
    if correct:
        return [
            (task_to_compute, report_computed_task, None, None, None, None),
            (task_to_compute, report_computed_task, ack_report_computed_task, None, None, None),
            (task_to_compute, report_computed_task, None, reject_report_computed_task_with_task_to_compute, None, None),
            (task_to_compute, report_computed_task, None, reject_report_computed_task_with_task_failure, None, None),
            (task_to_compute, report_computed_task, None, reject_report_computed_task_with_cannot_compute_task, None, None),
            (task_to_compute, report_computed_task, None, None, force_get_task_result, None),
            (task_to_compute, report_computed_task, None, None, None, subtask_results_rejected),
        ]
    else:
        return [
            (task_to_compute, different_report_computed_task, None, None, None, None),
            (task_to_compute, report_computed_task, different_ack_report_computed_task, None, None, None),
            (task_to_compute, report_computed_task, None, different_reject_report_computed_task_with_task_to_compute, None, None),
            (task_to_compute, report_computed_task, None, different_reject_report_computed_task_with_task_failure, None, None),
            (task_to_compute, report_computed_task, None, different_reject_report_computed_task_with_cannot_compute_task, None, None),
            (task_to_compute, report_computed_task, None, reject_report_computed_task_without_reason_and_task_to_compute, None, None),
            (task_to_compute, report_computed_task, None, None, different_force_get_task_result, None),
            (task_to_compute, report_computed_task, None, None, None, different_subtask_results_rejected),
        ]


class TestSubtaskModelValidation():

    @pytest.mark.django_db
    @pytest.mark.parametrize((
        'task_to_compute',
        'report_computed_task',
        'ack_report_computed_task',
        'reject_report_computed_task',
        'force_get_task_result',
        'subtask_results_rejected',
    ),
        _get_data_list(correct=True)
    )  # pylint: disable=no-self-use
    def test_that_storing_subtask_with_task_to_compute_nested_in_another_messages_will_not_raise_exception_when_messages_are_equal(
        self,
        task_to_compute,
        report_computed_task,
        ack_report_computed_task,
        reject_report_computed_task,
        force_get_task_result,
        subtask_results_rejected,
    ):
        try:
            store_subtask(
                task_id=task_to_compute.task_id,
                subtask_id=task_to_compute.subtask_id,
                provider_public_key=hex_to_bytes_convert(task_to_compute.provider_public_key),
                requestor_public_key=hex_to_bytes_convert(task_to_compute.requestor_public_key),
                state=Subtask.SubtaskState.ACCEPTED,
                task_to_compute=task_to_compute,
                report_computed_task=report_computed_task,
                next_deadline=None,
                ack_report_computed_task=ack_report_computed_task,
                reject_report_computed_task=reject_report_computed_task,
                force_get_task_result=force_get_task_result,
                subtask_results_rejected=subtask_results_rejected,
            )
            Subtask.objects.get(subtask_id=task_to_compute.subtask_id).delete()
        except Exception:  # pylint: disable=broad-except
            pytest.fail()

    @pytest.mark.django_db
    @pytest.mark.parametrize((
        'task_to_compute',
        'report_computed_task',
        'ack_report_computed_task',
        'reject_report_computed_task',
        'force_get_task_result',
        'subtask_results_rejected',
    ),
        _get_data_list(correct=False)
    )  # pylint: disable=no-self-use
    def test_that_storing_subtask_with_task_to_compute_nested_in_another_messages_will_raise_exception_when_it_is_different_from_original_task_to_compute(
        self,
        task_to_compute,
        report_computed_task,
        ack_report_computed_task,
        reject_report_computed_task,
        force_get_task_result,
        subtask_results_rejected,
    ):
        with pytest.raises(ValidationError):
            store_subtask(
                task_id=task_to_compute.task_id,
                subtask_id=task_to_compute.subtask_id,
                provider_public_key=hex_to_bytes_convert(task_to_compute.provider_public_key),
                requestor_public_key=hex_to_bytes_convert(task_to_compute.requestor_public_key),
                state=Subtask.SubtaskState.ACCEPTED,
                task_to_compute=task_to_compute,
                report_computed_task=report_computed_task,
                next_deadline=None,
                ack_report_computed_task=ack_report_computed_task,
                reject_report_computed_task=reject_report_computed_task,
                force_get_task_result=force_get_task_result,
                subtask_results_rejected=subtask_results_rejected,
            )


def store_report_computed_task_as_subtask():
    task_to_compute = factories.tasks.TaskToComputeFactory()
    report_computed_task = factories.tasks.ReportComputedTaskFactory(task_to_compute=task_to_compute)
    ack_report_computed_task = factories.tasks.AckReportComputedTaskFactory(report_computed_task=report_computed_task)
    force_get_task_result = factories.concents.ForceGetTaskResultFactory(report_computed_task=report_computed_task)
    subtask_results_rejected = factories.tasks.SubtaskResultsRejectedFactory(report_computed_task=report_computed_task)

    subtask = store_subtask(
        task_id=task_to_compute.task_id,
        subtask_id=task_to_compute.subtask_id,
        provider_public_key=hex_to_bytes_convert(task_to_compute.provider_public_key),
        requestor_public_key=hex_to_bytes_convert(task_to_compute.requestor_public_key),
        state=Subtask.SubtaskState.ACCEPTED,
        task_to_compute=task_to_compute,
        report_computed_task=report_computed_task,
        next_deadline=None,
        ack_report_computed_task=ack_report_computed_task,
        reject_report_computed_task=None,
        force_get_task_result=force_get_task_result,
        subtask_results_rejected=subtask_results_rejected,
    )
    return subtask


class TestDepositAccountValidation(ConcentIntegrationTestCase):
    def setUp(self):
        super().setUp()
        self.task_to_compute = self._get_deserialized_task_to_compute()
        self.payer_ethereum_address = self.task_to_compute.requestor_ethereum_address
        self.payee_ethereum_address = self.task_to_compute.provider_ethereum_address

        self.client = Client(public_key_bytes=self.PROVIDER_PUBLIC_KEY)
        self.client.clean()
        self.client.save()

        self.deposit_account = DepositAccount()
        self.deposit_account.client = self.client
        self.deposit_account.ethereum_address = self.payer_ethereum_address

    def test_that_exception_is_raised_when_ethereum_address_has_wrong_length(self):
        self.deposit_account.ethereum_address = self.payer_ethereum_address + '1'

        with pytest.raises(ValidationError):
            self.deposit_account.clean()
            self.deposit_account.save()

    def test_that_exception_is_not_raised_when_ethereum_address_has_wrong_length(self):
        self.deposit_account.ethereum_address = self.payer_ethereum_address
        self.deposit_account.clean()
        self.deposit_account.save()


class TestDepositClaimValidation(ConcentIntegrationTestCase):
    def setUp(self):
        super().setUp()
        self.task_to_compute = self._get_deserialized_task_to_compute()
        self.payer_ethereum_address = self.task_to_compute.requestor_ethereum_address
        self.payee_ethereum_address = self.task_to_compute.provider_ethereum_address

        self.client = Client(public_key_bytes=self.PROVIDER_PUBLIC_KEY)
        self.client.clean()
        self.client.save()

        self.deposit_account = DepositAccount()
        self.deposit_account.client = self.client
        self.deposit_account.ethereum_address = self.task_to_compute.requestor_ethereum_address
        self.deposit_account.clean()
        self.deposit_account.save()

        self.deposit_claim = DepositClaim()
        self.deposit_claim.payer_deposit_account = self.deposit_account
        self.deposit_claim.subtask = store_report_computed_task_as_subtask()
        self.deposit_claim.payee_ethereum_address = self.task_to_compute.provider_ethereum_address
        self.deposit_claim.concent_use_case = 1
        self.deposit_claim.amount = 1
        self.deposit_claim.tx_hash = encode_hex(MOCK_TRANSACTION.hash)

    def test_that_exception_is_raised_when_subtask_is_null_and_concent_use_case_is_not_forced_payment(self):
        self.deposit_claim.subtask = None
        with pytest.raises(ValidationError):
            self.deposit_claim.clean()
            self.deposit_claim.save()

    def test_that_exception_is_not_raised_when_subtask_is_null_and_concent_use_case_is_forced_payment(self):
        self.deposit_claim.concent_use_case = 5
        self.deposit_claim.clean()
        self.deposit_claim.save()

    def test_that_exception_is_raised_when_payer_deposit_account_ethereum_address_is_the_same_as_payee_ethereum_address(self):
        self.deposit_claim.payee_ethereum_address = self.payer_ethereum_address

        with pytest.raises(ValidationError):
            self.deposit_claim.clean()
            self.deposit_claim.save()

    def test_that_exception_is_raised_when_payee_ethereum_address_is_the_same_as_payer_deposit_account_ethereum_address(self):
        self.deposit_account.ethereum_address = self.payee_ethereum_address
        self.deposit_account.clean()
        self.deposit_account.save()

        with pytest.raises(ValidationError):
            self.deposit_claim.clean()
            self.deposit_claim.save()

    def test_that_exception_is_raised_when_payee_ethereum_address_has_wrong_length(self):
        self.deposit_claim.payee_ethereum_address = self.payee_ethereum_address + '1'
        with pytest.raises(ValidationError):
            self.deposit_claim.clean()
            self.deposit_claim.save()

    def test_that_exception_is_raised_when_amount_is_equal_to_zero(self):
        self.deposit_claim.amount = 0
        with pytest.raises(ValidationError):
            self.deposit_claim.clean()
            self.deposit_claim.save()

    def test_that_exception_is_raised_when_amount_is_less_then_zero(self):
        self.deposit_claim.amount = -1
        with pytest.raises(ValidationError):
            self.deposit_claim.clean()
            self.deposit_claim.save()

    def test_that_exception_is_raised_when_tx_hash_is_not_none_and_not_string(self):
        self.deposit_claim.tx_hash = 1
        with pytest.raises(ValidationError):
            self.deposit_claim.clean()
            self.deposit_claim.save()

    def test_that_deposit_account_is_not_removed_when_deposit_claim_is_deleted(self):
        self.deposit_claim.clean()
        self.deposit_claim.save()

        DepositClaim.objects.filter(pk=self.deposit_claim.pk).delete()

        self.assertTrue(
            DepositAccount.objects.filter(pk=self.deposit_account.pk).exists()
        )
