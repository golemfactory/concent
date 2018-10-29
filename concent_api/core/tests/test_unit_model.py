import pytest
from django.core.exceptions import ValidationError

from golem_messages import factories
from golem_messages import message
from golem_messages.utils import encode_hex

from common.constants import ConcentUseCase
from core.constants import ETHEREUM_ADDRESS_LENGTH
from core.constants import ETHEREUM_TRANSACTION_HASH_LENGTH
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
        task_to_compute = self._get_deserialized_task_to_compute()
        self.payer_ethereum_address = task_to_compute.requestor_ethereum_address

        self.client = Client(public_key_bytes=self.REQUESTOR_PUBLIC_KEY)
        self.client.clean()
        self.client.save()

    def test_that_exception_is_raised_when_ethereum_address_has_wrong_length(self):
        with pytest.raises(ValidationError) as exception_info:
            deposit_account = DepositAccount(
                client=self.client,
                ethereum_address=self.payer_ethereum_address + '1'
            )
            deposit_account.clean()
        self.assertIn('ethereum_address', exception_info.value.error_dict)

    def test_that_exception_is_raised_when_ethereum_address_has_wrong_type(self):
        with pytest.raises(ValidationError) as exception_info:
            deposit_account = DepositAccount(
                client=self.client,
                ethereum_address=b'x' * ETHEREUM_ADDRESS_LENGTH
            )
            deposit_account.clean()
        self.assertIn('ethereum_address', exception_info.value.error_dict)

    def test_that_exception_is_not_raised_when_ethereum_address_has_valid_length(self):
        deposit_account = DepositAccount(
            client=self.client,
            ethereum_address=self.payer_ethereum_address
        )
        deposit_account.clean()
        deposit_account.save()


class TestDepositClaimValidation(ConcentIntegrationTestCase):
    def setUp(self):
        super().setUp()
        task_to_compute = self._get_deserialized_task_to_compute()
        self.payer_ethereum_address = task_to_compute.requestor_ethereum_address
        self.payee_ethereum_address = task_to_compute.provider_ethereum_address

        client = Client(public_key_bytes=self.REQUESTOR_PUBLIC_KEY)
        client.clean()
        client.save()

        self.payer_deposit_account = DepositAccount()
        self.payer_deposit_account.client = client
        self.payer_deposit_account.ethereum_address = task_to_compute.requestor_ethereum_address
        self.payer_deposit_account.clean()
        self.payer_deposit_account.save()

        self.deposit_claim = DepositClaim()
        self.deposit_claim.payer_deposit_account = self.payer_deposit_account
        self.deposit_claim.subtask = store_report_computed_task_as_subtask()
        self.deposit_claim.payee_ethereum_address = self.payee_ethereum_address
        self.deposit_claim.concent_use_case = ConcentUseCase.FORCED_TASK_RESULT.value
        self.deposit_claim.amount = 1
        self.deposit_claim.tx_hash = encode_hex(MOCK_TRANSACTION.hash)

    def test_that_exception_is_raised_when_subtask_is_null_and_concent_use_case_is_not_forced_payment(self):
        self.deposit_claim.subtask = None
        with pytest.raises(ValidationError) as exception_info:
            self.deposit_claim.clean()
        self.assertIn('subtask', exception_info.value.error_dict)

    def test_that_exception_is_not_raised_when_subtask_is_null_and_concent_use_case_is_forced_payment(self):
        self.deposit_claim.subtask = None
        self.deposit_claim.concent_use_case = ConcentUseCase.FORCED_PAYMENT.value
        self.deposit_claim.clean()

    def test_that_exception_is_raised_when_payee_ethereum_address_is_the_same_as_payer_deposit_account_ethereum_address(self):
        self.deposit_claim.payee_ethereum_address = self.deposit_claim.payer_deposit_account.ethereum_address

        with pytest.raises(ValidationError) as exception_info:
            self.deposit_claim.clean()
        self.assertIn('payer_deposit_account', exception_info.value.error_dict)

    def test_that_exception_is_raised_when_payee_ethereum_address_has_wrong_length(self):
        self.deposit_claim.payee_ethereum_address = self.payee_ethereum_address + '1'
        with pytest.raises(ValidationError) as exception_info:
            self.deposit_claim.clean()
        self.assertIn('payee_ethereum_address', exception_info.value.error_dict)

    def test_that_exception_is_raised_when_payee_ethereum_address_has_wrong_type(self):
        self.deposit_claim.payee_ethereum_address = b'x' * ETHEREUM_ADDRESS_LENGTH
        with pytest.raises(ValidationError) as exception_info:
            self.deposit_claim.clean()
        self.assertIn('payee_ethereum_address', exception_info.value.error_dict)

    def test_that_exception_is_raised_when_amount_is_equal_to_zero(self):
        self.deposit_claim.amount = 0
        with pytest.raises(ValidationError) as exception_info:
            self.deposit_claim.clean()
        self.assertIn('amount', exception_info.value.error_dict)

    def test_that_exception_is_raised_when_amount_is_less_then_zero(self):
        self.deposit_claim.amount = -1
        with pytest.raises(ValidationError) as exception_info:
            self.deposit_claim.clean()
        self.assertIn('amount', exception_info.value.error_dict)

    def test_that_exception_is_raised_when_amount_is_of_wrong_type(self):
        self.deposit_claim.amount = 5.0
        with pytest.raises(ValidationError):
            self.deposit_claim.clean()

    def test_that_exception_is_raised_when_tx_hash_is_not_none_and_not_string(self):
        self.deposit_claim.tx_hash = b'x' * ETHEREUM_TRANSACTION_HASH_LENGTH
        with pytest.raises(ValidationError) as exception_info:
            self.deposit_claim.clean()
        self.assertIn('tx_hash', exception_info.value.error_dict)

    def test_that_exception_is_raised_when_tx_hash_has_wrong_length(self):
        self.deposit_claim.tx_hash = encode_hex(MOCK_TRANSACTION.hash) + 'a'
        with pytest.raises(ValidationError) as exception_info:
            self.deposit_claim.clean()
        self.assertIn('tx_hash', exception_info.value.error_dict)

    def test_that_no_exception_is_raised_when_tx_hash_is_none(self):
        self.deposit_claim.tx_hash = None
        self.deposit_claim.clean()
        self.deposit_claim.save()

    def test_that_deposit_account_is_not_removed_when_deposit_claim_is_deleted(self):
        self.deposit_claim.clean()
        self.deposit_claim.save()

        DepositClaim.objects.filter(pk=self.deposit_claim.pk).delete()

        self.assertTrue(
            DepositAccount.objects.filter(pk=self.payer_deposit_account.pk).exists()
        )

    def test_that_no_exception_is_raised_when_deposit_claim_is_valid(self):
        self.deposit_claim.clean()
        self.deposit_claim.save()
