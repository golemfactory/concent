from typing import Any
from typing import Union
import base64
import datetime

from django.conf import settings
from django.core.validators import ValidationError
from django.db.models import BinaryField
from django.db.models import BooleanField
from django.db.models import CharField
from django.db.models import DateTimeField
from django.db.models import DecimalField
from django.db.models import ExpressionWrapper
from django.db.models import F
from django.db.models import ForeignKey
from django.db.models import Func
from django.db.models import IntegerField
from django.db.models import Manager
from django.db.models import Model
from django.db.models import OneToOneField
from django.db.models import PositiveSmallIntegerField
from django.db.models import QuerySet
from django.db.models import Value

from constance import config
from golem_messages import message

from common.constants import ConcentUseCase
from common.exceptions import ConcentInSoftShutdownMode
from common.fields import Base64Field
from common.fields import ChoiceEnum
from common.helpers import deserialize_database_message
from common.helpers import deserialize_message
from common.helpers import parse_datetime_to_timestamp

from .constants import TASK_OWNER_KEY_LENGTH
from .constants import ETHEREUM_ADDRESS_LENGTH
from .constants import GOLEM_PUBLIC_KEY_LENGTH
from .constants import MESSAGE_TASK_ID_MAX_LENGTH
from .validation import validate_database_report_computed_task
from .validation import validate_database_task_to_compute


class SubtaskWithTimingColumnsManager(Manager):
    """Creates maximum_download time, subtask_verification_time and download_deadline columns
    maximum_download_time = DOWNLOAD_LEADIN_TIME + ceil((result_package_size / MINIMUM_UPLOAD_RATE << 10))
    subtask_verification_time = (4 * CONCENT_MESSAGING_TIME) + (3 * maximum_download_time) + (0.5 * (computation_deadline - task_to_compute_timestamp))
    download_deadline = computation_deadline + maximum_download_time
    """

    @classmethod
    def with_maximum_download_time(cls, query_set: QuerySet) -> QuerySet:
        bytes_per_sec = settings.MINIMUM_UPLOAD_RATE << 10
        download_time = Func(F('result_package_size') / float(bytes_per_sec), function='CEIL')
        return query_set.annotate(
            maximum_download_time=Value(settings.DOWNLOAD_LEADIN_TIME) + download_time
        )

    @classmethod
    def with_subtask_verification_time(cls, query_set: QuerySet) -> QuerySet:
        task_to_compute_timestamp = Func(Value('epoch'), F('task_to_compute__timestamp'), function='DATE_PART')
        subtask_timeout = Func(Value('epoch'), F('computation_deadline'), function='DATE_PART') - task_to_compute_timestamp
        subtask_verification_time = (
            4 * settings.CONCENT_MESSAGING_TIME) + (
            3 * F('maximum_download_time')) + (
            0.5 * subtask_timeout
        )
        return query_set.annotate(subtask_verification_time=ExpressionWrapper(
            subtask_verification_time, output_field=IntegerField())
        )

    @classmethod
    def with_download_deadline(cls, query_set: QuerySet) -> QuerySet:
        return query_set.annotate(download_deadline=ExpressionWrapper(
            Func(Value('epoch'), F('computation_deadline'), function='DATE_PART') +
            F('subtask_verification_time'),
            output_field=IntegerField())
        )

    @classmethod
    def with_timing_columns(cls, query_set: QuerySet) -> QuerySet:
        query_set_with_maximum_download_time = cls.with_maximum_download_time(query_set)
        query_set_with_subtask_verification_time = cls.with_subtask_verification_time(query_set_with_maximum_download_time)
        query_set_with_download_deadline = cls.with_download_deadline(query_set_with_subtask_verification_time)
        return query_set_with_download_deadline

    def get_queryset(self) -> QuerySet:
        return self.with_timing_columns(super().get_queryset())


class StoredMessage(Model):
    type = PositiveSmallIntegerField()
    timestamp = DateTimeField()
    data = BinaryField()
    task_id = CharField(max_length=MESSAGE_TASK_ID_MAX_LENGTH)
    subtask_id = CharField(max_length=MESSAGE_TASK_ID_MAX_LENGTH)
    created_at = DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return 'StoredMessage #{}, type:{}, {}'.format(self.id, self.type, self.timestamp)


class ClientManager(Manager):

    def get_or_create_full_clean(self, public_key: bytes) -> 'Client':
        """
        Returns Model instance.
        Does the same as get_or_create method, but also performs full_clean() on newly created instance.
        """
        try:
            instance = self.get(public_key = base64.b64encode(public_key))
        except self.model.DoesNotExist:
            instance = self.model(
                public_key_bytes = public_key
            )
            instance.full_clean()
            instance.save()
        return instance


class Client(Model):
    """
    Represents Concent client, identified by public key.
    """

    objects = ClientManager()

    public_key = Base64Field(max_length = GOLEM_PUBLIC_KEY_LENGTH, unique = True)

    created_at = DateTimeField(auto_now_add=True)


class Subtask(Model):
    """
    Represents subtask states.
    """
    objects = Manager()
    objects_with_timing_columns = SubtaskWithTimingColumnsManager()

    class SubtaskState(ChoiceEnum):
        FORCING_REPORT              = 'forcing_report'
        REPORTED                    = 'reported'
        FORCING_RESULT_TRANSFER     = 'forcing_result_transfer'
        RESULT_UPLOADED             = 'result_uploaded'
        FORCING_ACCEPTANCE          = 'forcing_acceptance'
        REJECTED                    = 'rejected'
        VERIFICATION_FILE_TRANSFER  = 'verification_file_transfer'
        ADDITIONAL_VERIFICATION     = 'additional_verification'
        ACCEPTED                    = 'accepted'
        FAILED                      = 'failed'

    # Defines Subtask model active states
    ACTIVE_STATES = {
        SubtaskState.FORCING_REPORT,
        SubtaskState.FORCING_RESULT_TRANSFER,
        SubtaskState.FORCING_ACCEPTANCE,
        SubtaskState.ADDITIONAL_VERIFICATION,
        SubtaskState.VERIFICATION_FILE_TRANSFER,
    }

    # Defines Subtask model passive states
    PASSIVE_STATES = {
        SubtaskState.REPORTED,
        SubtaskState.RESULT_UPLOADED,
        SubtaskState.REJECTED,
        SubtaskState.ACCEPTED,
        SubtaskState.FAILED,
    }

    assert set([s for s in SubtaskState]) == set(PASSIVE_STATES) | set(ACTIVE_STATES)
    assert set(PASSIVE_STATES) & set(ACTIVE_STATES) == set()

    # Defines possible state transitions, where keys are transitions to, and values are lists of transitions from.
    # None means transition from Unknown state.
    POSSIBLE_TRANSITIONS_TO = {
        SubtaskState.FORCING_REPORT: {
            None,
        },
        SubtaskState.REPORTED: {
            SubtaskState.FORCING_REPORT,
        },
        SubtaskState.FORCING_RESULT_TRANSFER: {
            None,
            SubtaskState.REPORTED,
        },
        SubtaskState.RESULT_UPLOADED: {
            SubtaskState.FORCING_RESULT_TRANSFER,
        },
        SubtaskState.FORCING_ACCEPTANCE: {
            None,
            SubtaskState.REPORTED,
            SubtaskState.RESULT_UPLOADED,
        },
        SubtaskState.REJECTED: {
            SubtaskState.FORCING_ACCEPTANCE,
        },
        SubtaskState.VERIFICATION_FILE_TRANSFER: {
            None,
            SubtaskState.REPORTED,
            SubtaskState.RESULT_UPLOADED,
            SubtaskState.FORCING_ACCEPTANCE,
            SubtaskState.REJECTED,
        },
        SubtaskState.ADDITIONAL_VERIFICATION: {
            SubtaskState.VERIFICATION_FILE_TRANSFER,
        },
        SubtaskState.ACCEPTED: {
            SubtaskState.FORCING_ACCEPTANCE,
            SubtaskState.ADDITIONAL_VERIFICATION,
        },
        SubtaskState.FAILED: {
            SubtaskState.FORCING_REPORT,
            SubtaskState.FORCING_RESULT_TRANSFER,
            SubtaskState.VERIFICATION_FILE_TRANSFER,
            SubtaskState.ADDITIONAL_VERIFICATION,
        },
    }

    assert set(POSSIBLE_TRANSITIONS_TO) == set(SubtaskState)
    assert set(SubtaskState) | {None} == {
        state
        for from_states in POSSIBLE_TRANSITIONS_TO.values()
        for state in from_states  # type: ignore
    } | {SubtaskState.FAILED, SubtaskState.ACCEPTED}, 'There are no transitions from some states'

    # Defines in which states given related message can't be None.
    REQUIRED_RELATED_MESSAGES_IN_STATES = {
        'task_to_compute': {
            SubtaskState.FORCING_REPORT,
            SubtaskState.REPORTED,
            SubtaskState.FORCING_RESULT_TRANSFER,
            SubtaskState.RESULT_UPLOADED,
            SubtaskState.FORCING_ACCEPTANCE,
            SubtaskState.REJECTED,
            SubtaskState.ACCEPTED,
            SubtaskState.FAILED,
        },
        'want_to_compute_task': {
            SubtaskState.FORCING_REPORT,
            SubtaskState.REPORTED,
            SubtaskState.FORCING_RESULT_TRANSFER,
            SubtaskState.RESULT_UPLOADED,
            SubtaskState.FORCING_ACCEPTANCE,
            SubtaskState.REJECTED,
            SubtaskState.ACCEPTED,
            SubtaskState.FAILED,
        },
        'report_computed_task': {
            SubtaskState.FORCING_REPORT,
            SubtaskState.REPORTED,
            SubtaskState.FORCING_RESULT_TRANSFER,
            SubtaskState.RESULT_UPLOADED,
            SubtaskState.FAILED,
        },
        'ack_report_computed_task': {},
        'reject_report_computed_task': {},
        'subtask_results_accepted': {},
        'subtask_results_rejected': {
            SubtaskState.REJECTED,
        },
        'force_get_task_result': {
            SubtaskState.FORCING_RESULT_TRANSFER,
            SubtaskState.RESULT_UPLOADED,
        }
    }

    # Defines in which states given related message must be None.
    UNSET_RELATED_MESSAGES_IN_STATES = {
        'task_to_compute': {},
        'want_to_compute_task': {},
        'report_computed_task': {},
        'ack_report_computed_task': {
            SubtaskState.FORCING_REPORT,
        },
        'reject_report_computed_task': {
            SubtaskState.FORCING_REPORT,
        },
        'subtask_results_accepted': {
            SubtaskState.FORCING_REPORT,
            SubtaskState.REPORTED,
            SubtaskState.FORCING_RESULT_TRANSFER,
            SubtaskState.RESULT_UPLOADED,
            SubtaskState.FORCING_ACCEPTANCE,
        },
        'subtask_results_rejected': {
            SubtaskState.FORCING_REPORT,
            SubtaskState.REPORTED,
            SubtaskState.FORCING_RESULT_TRANSFER,
            SubtaskState.RESULT_UPLOADED,
            SubtaskState.FORCING_ACCEPTANCE,
        },
        'force_get_task_result': {
            SubtaskState.FORCING_REPORT,
            SubtaskState.REPORTED,
        }
    }

    # Defines related golem message for related stored messages
    MESSAGE_FOR_FIELD = {
        'task_to_compute':              message.TaskToCompute,
        'want_to_compute_task':         message.WantToComputeTask,
        'report_computed_task':         message.ReportComputedTask,
        'ack_report_computed_task':     message.tasks.AckReportComputedTask,
        'reject_report_computed_task':  message.tasks.RejectReportComputedTask,
        'subtask_results_accepted':     message.tasks.SubtaskResultsAccepted,
        'subtask_results_rejected':     message.tasks.SubtaskResultsRejected,
        'force_get_task_result':        message.concents.ForceGetTaskResult,
    }

    assert set(MESSAGE_FOR_FIELD) == set(REQUIRED_RELATED_MESSAGES_IN_STATES)
    assert {
        state
        for states in REQUIRED_RELATED_MESSAGES_IN_STATES.values()
        for state in states
    }.issubset(set(SubtaskState))

    assert set(MESSAGE_FOR_FIELD) == set(UNSET_RELATED_MESSAGES_IN_STATES)
    assert {
        state
        for states in UNSET_RELATED_MESSAGES_IN_STATES.values()
        for state in states
    }.issubset(set(SubtaskState))

    # Defines in which states exist possibility to replace message nested in Subtask.
    MESSAGE_REPLACEMENT_FOR_STATE = {
        SubtaskState.FORCING_REPORT: {
            message.ReportComputedTask,
        },
        SubtaskState.REPORTED: {
            None,
        },
        SubtaskState.FORCING_RESULT_TRANSFER: {
            None,
        },
        SubtaskState.RESULT_UPLOADED: {
            None,
        },
        SubtaskState.FORCING_ACCEPTANCE: {
            None,
        },
        SubtaskState.REJECTED: {
            None,
        },
        SubtaskState.VERIFICATION_FILE_TRANSFER: {
            None,
        },
        SubtaskState.ADDITIONAL_VERIFICATION: {
            None,
        },
        SubtaskState.ACCEPTED: {
            None,
        },
        SubtaskState.FAILED: {
            None,
        },
    }

    assert set(MESSAGE_REPLACEMENT_FOR_STATE) == set(SubtaskState)

    class Meta:
        unique_together = (
            ('requestor', 'task_id'),
            ('requestor', 'subtask_id'),
        )

    task_id = CharField(max_length=MESSAGE_TASK_ID_MAX_LENGTH)

    computation_deadline = DateTimeField()

    result_package_size = IntegerField()

    # Golem clients are not guaranteed to use unique subtask_id because they are UUIDs,
    # but Concent at this moment does not support subtasks with non-unique IDs.
    # However, the combination of requestor's public key and subtask ID is guaranteed to be unique.
    subtask_id = CharField(max_length=MESSAGE_TASK_ID_MAX_LENGTH, unique=True, db_index=True)

    # Relation to concent client in requestor context.
    requestor = ForeignKey(Client, related_name='subtasks_as_requestor')

    # Relation to concent client in provider context.
    provider = ForeignKey(Client, related_name='subtasks_as_provider')

    state = CharField(max_length=32, choices=SubtaskState.choices())

    # If in an active state, it's the time at which Concent automatically transitions to a passive state if it does
    # not get the information it expects from the client (a timeout). Must be NULL in a passive state.
    next_deadline = DateTimeField(blank=True, null=True)

    created_at = DateTimeField(auto_now_add=True)
    modified_at = DateTimeField(auto_now=True)

    # Related messages
    task_to_compute = OneToOneField(StoredMessage, related_name='subtasks_for_task_to_compute')
    want_to_compute_task = OneToOneField(StoredMessage, related_name='subtasks_for_want_to_compute_task')
    report_computed_task = OneToOneField(StoredMessage, related_name='subtasks_for_report_computed_task')
    ack_report_computed_task = OneToOneField(StoredMessage, blank=True, null=True, related_name='subtasks_for_ack_report_computed_task')
    reject_report_computed_task = OneToOneField(StoredMessage, blank=True, null=True, related_name='subtasks_for_reject_report_computed_task')
    subtask_results_accepted = OneToOneField(StoredMessage, blank=True, null=True, related_name='subtasks_for_subtask_results_accepted')
    subtask_results_rejected = OneToOneField(StoredMessage, blank=True, null=True, related_name='subtasks_for_subtask_results_rejected')
    force_get_task_result = OneToOneField(StoredMessage, blank=True, null=True, related_name='subtasks_for_force_get_task_result')

    # Flag used to notify Concent Core that Storage Cluster has uploaded files related with this Subtask.
    result_upload_finished = BooleanField(default=False)

    def __init__(self, *args: list, **kwargs: Union[str, int, datetime.datetime, StoredMessage, None]) -> None:
        super().__init__(*args, **kwargs)
        self._current_state_name = None

    def __repr__(self) -> str:
        return f"Subtask: task_id={self.task_id}, subtask_id={self.subtask_id}, state={self.state_enum}"

    @classmethod
    def from_db(cls, db: str, field_names: list, values: tuple) -> 'Subtask':
        new = super().from_db(db, field_names, values)
        new._current_state_name = new.state  # pylint: disable=no-member
        return new

    def clean(self) -> None:
        super().clean()

        # Concent should not accept anything that cause a transition to an active state in soft shutdown mode.
        if config.SOFT_SHUTDOWN_MODE is True and self.state_enum in self.ACTIVE_STATES:
            raise ConcentInSoftShutdownMode

        # next_deadline must be datetime only for active states
        if (
            not self._state.adding and
            not isinstance(self.next_deadline, datetime.datetime) and
            self.state_enum in self.ACTIVE_STATES
        ):
            raise ValidationError({
                'next_deadline': 'next_deadline must be datetime for active state.'
            })

        # next_deadline must be None in passive states
        if not self._state.adding and self.next_deadline is not None and self.state_enum in self.PASSIVE_STATES:
            raise ValidationError({
                'next_deadline': 'next_deadline must be None for passive state.'
            })

        # State transition can happen only by defined rule
        # but not when we create new object
        # and not when state is not being changed
        if (
            not self._state.adding and
            self._current_state_enum != self.state_enum and
            self._current_state_enum not in self.POSSIBLE_TRANSITIONS_TO[self.state_enum]  # type: ignore
        ):
            raise ValidationError({
                'state': 'Subtask cannot change its state from {} to {}.'.format(
                    self._current_state_name,
                    self.state,
                )
            })
        else:
            self._current_state_name = self.state

        # Both ack_report_computed_task and reject_report_computed_task cannot set at the same time.
        if self.ack_report_computed_task is not None and self.reject_report_computed_task is not None:
            raise ValidationError(
                'Both ack_report_computed_task and reject_report_computed_task cannot be set at the same time.'
            )

        # Requestor and provider cannot be the same clients
        if self.requestor_id == self.provider_id:
            raise ValidationError('Requestor and provided are the same client.')

        # Check if all required related messages are not None in current state.
        for stored_message_name, states in Subtask.REQUIRED_RELATED_MESSAGES_IN_STATES.items():
            if self.state_enum in states and getattr(self, stored_message_name) is None:
                raise ValidationError({
                    stored_message_name: '{} cannot be None in state {}.'.format(
                        stored_message_name,
                        self.state,
                    )
                })

        # Check if all related messages which must be None are None in current state.
        for stored_message_name, states in Subtask.UNSET_RELATED_MESSAGES_IN_STATES.items():
            if self.state_enum in states and getattr(self, stored_message_name) is not None:
                raise ValidationError({
                    stored_message_name: '{} must be None in state {}.'.format(
                        stored_message_name,
                        self.state,
                    )
                })

        if isinstance(self.report_computed_task.data, bytes):
            deserialized_report_computed_task = deserialize_message(self.report_computed_task.data)
        else:
            deserialized_report_computed_task = deserialize_message(self.report_computed_task.data.tobytes())  # pylint: disable=no-member

        # If available, the report_computed_task nested in force_get_task_result must match report_computed_task.
        if (
            self.force_get_task_result is not None and
            deserialize_message(self.force_get_task_result.data).report_computed_task != deserialized_report_computed_task
        ):
            raise ValidationError({
                'force_get_task_result': "ReportComputedTask nested in ForceGetTaskResult must match Subtask's ReportComputedTask."
            })

        if not self.result_package_size == deserialized_report_computed_task.size:
            raise ValidationError({
                'result_package_size': "ReportComputedTask size mismatch"
            })

        if isinstance(self.task_to_compute.data, bytes):
            deserialized_task_to_compute = deserialize_message(self.task_to_compute.data)
        else:
            deserialized_task_to_compute = deserialize_message(self.task_to_compute.data.tobytes())  # pylint: disable=no-member

        if not parse_datetime_to_timestamp(self.computation_deadline) == deserialized_task_to_compute.compute_task_def['deadline']:
            raise ValidationError({
                'computation_deadline': "TaskToCompute deadline mismatch"
            })

        # Validation for every nested message which is stored in Control database
        # Every nested message must be the same as message stored separately.
        MESSAGES_TO_VALIDATE_TASK_TO_COMPUTE = [
            self.report_computed_task,
            self.subtask_results_accepted,
            self.reject_report_computed_task,
        ]
        MESSAGES_TO_VALIDATE_REPORT_COMPUTED_TASK = [
            self.ack_report_computed_task,
            self.subtask_results_rejected,
            self.force_get_task_result,
        ]

        for task_to_compute_to_validate in MESSAGES_TO_VALIDATE_TASK_TO_COMPUTE:
            if task_to_compute_to_validate is not None:
                validate_database_task_to_compute(
                    task_to_compute=deserialized_task_to_compute,
                    message_to_compare=deserialize_database_message(task_to_compute_to_validate),
                )

        for report_computed_task_to_validate in MESSAGES_TO_VALIDATE_REPORT_COMPUTED_TASK:
            if report_computed_task_to_validate is not None:
                validate_database_report_computed_task(
                    report_computed_task=deserialized_report_computed_task,
                    message_to_compare=deserialize_database_message(report_computed_task_to_validate),
                )

    @property
    def state_enum(self) -> 'SubtaskState':
        return Subtask.SubtaskState[self.state]

    @property
    def _current_state_enum(self) -> 'SubtaskState':
        return Subtask.SubtaskState[self._current_state_name]  # type: ignore


class PendingResponse(Model):
    """
    Stores information about messages to be returned from the `receive` or `receive-out-of-band` endpoint.
    """

    class ResponseType(ChoiceEnum):
        ForceReportComputedTask         = 'ForceReportComputedTask'
        ForceReportComputedTaskResponse = 'ForceReportComputedTaskResponse'
        VerdictReportComputedTask       = 'VerdictReportComputedTask'
        ForceGetTaskResultFailed        = 'ForceGetTaskResultFailed'
        ForceGetTaskResultUpload        = 'ForceGetTaskResultUpload'
        ForceGetTaskResultDownload      = 'ForceGetTaskResultDownload'
        ForceSubtaskResults             = 'ForceSubtaskResults'
        SubtaskResultsSettled           = 'SubtaskResultsSettled'
        ForceSubtaskResultsResponse     = 'ForceSubtaskResultsResponse'
        SubtaskResultsRejected          = 'SubtaskResultsRejected'
        ForcePaymentCommitted           = 'ForcePaymentCommitted'

    class Queue(ChoiceEnum):
        Receive             = 'receive'
        ReceiveOutOfBand    = 'receive_out_of_band'

    @property
    def response_type_enum(self) -> 'ResponseType':
        return PendingResponse.ResponseType[self.response_type]

    response_type        = CharField(max_length = 32, choices = ResponseType.choices())
    client               = ForeignKey(Client)
    queue                = CharField(max_length = 32, choices = Queue.choices())

    # TRUE if the client has already fetched the message.
    delivered            = BooleanField(default = False)

    subtask              = ForeignKey(Subtask, blank = True, null = True)

    created_at = DateTimeField(auto_now_add=True)
    modified_at = DateTimeField(auto_now=True)

    def clean(self) -> None:
        # payment_message can be included only if current state is ForcePaymentCommitted
        if self.response_type != PendingResponse.ResponseType.ForcePaymentCommitted.name and self.payments.filter(pending_response__pk = self.pk).exists():  # pylint: disable=no-member
            raise ValidationError({
                'payments_message': "Only 'ForcePaymentCommitted' responses can have a 'PaymentInfo' instance associated with it"
            })

        # subtask must be None if current state is ForcePaymentCommitted
        if self.response_type == PendingResponse.ResponseType.ForcePaymentCommitted.name and not hasattr(self, 'subtask'):  # pylint: disable=no-member
            raise ValidationError({
                'subtask': 'Payment message in queue cannot be associated with a subtask'
            })


class PaymentInfo(Model):
    """
    Stores the information needed to construt a PaymentCommitted message
    """

    class RecipientType(ChoiceEnum):
        Provider    = 'provider'
        Requestor   = 'requestor'

    payment_ts              = DateTimeField()
    task_owner_key          = BinaryField()
    provider_eth_account    = CharField(max_length = ETHEREUM_ADDRESS_LENGTH)
    amount_paid             = IntegerField()
    recipient_type          = CharField(max_length = 32, choices = RecipientType.choices())
    amount_pending          = IntegerField()
    pending_response        = ForeignKey(PendingResponse, related_name = 'payments')

    def clean(self) -> None:
        if self.task_owner_key == self.provider_eth_account:
            raise ValidationError({
                'provider_eth_account': 'Provider ethereum account address must be diffrent than task owner key'
            })

        if not isinstance(self.amount_pending, int) or self.amount_pending < 0:
            raise ValidationError({
                'amount_pending': 'Amount pending must be an integer and bigger than 0'
            })

        if not isinstance(self.amount_paid, int) or self.amount_paid < 0:
            raise ValidationError({
                'amount_paid': 'Amount paid must be an integer and bigger than or equal 0'
            })

        if not isinstance(self.task_owner_key, bytes) or not len(self.task_owner_key) == TASK_OWNER_KEY_LENGTH:
            raise ValidationError({
                'task_owner_key': f'Task owner key must be a bytes string with {TASK_OWNER_KEY_LENGTH} characters'
            })

        if not isinstance(self.provider_eth_account, str) or not len(self.provider_eth_account) == ETHEREUM_ADDRESS_LENGTH:
            raise ValidationError({
                'provider_eth_account': f'Provider ethereum account address must be a string with {ETHEREUM_ADDRESS_LENGTH} characters'
            })

        if not isinstance(self.pending_response, PendingResponse):
            raise ValidationError({
                'pending_response': 'PaymentInfo should be related with Pending Response'
            })


class GlobalTransactionState(Model):
    """
    Represents state of whole transaction service by storing last `nonce` used.

    There should always be at most one object of this type with id = 0. If it does not exist, it should be created and
    nonce initialized with a value obtained from SCI (Client.get_transaction_count()).
    """

    nonce = DecimalField(max_digits=32, decimal_places=0, default=0, unique=True)

    def save(self, *args: Any, **kwargs: Any) -> None:  # pylint: disable=arguments-differ
        self.pk = 0
        super().save(*args, **kwargs)


class PendingEthereumTransaction(Model):
    """
    Represents pending Ethereum transaction state.
    """

    nonce = DecimalField(max_digits=78, decimal_places=0)

    gasprice = DecimalField(max_digits=78, decimal_places=0)
    startgas = DecimalField(max_digits=78, decimal_places=0)
    value = DecimalField(max_digits=78, decimal_places=0)

    to = BinaryField(max_length=20)
    data = BinaryField()

    v = IntegerField()
    r = DecimalField(max_digits=78, decimal_places=0)
    s = DecimalField(max_digits=78, decimal_places=0)

    created_at = DateTimeField(auto_now_add=True)


class DepositAccount(Model):
    client = ForeignKey(Client)
    ethereum_address = CharField(max_length=ETHEREUM_ADDRESS_LENGTH)
    created_at = DateTimeField(auto_now_add=True)

    def clean(self) -> None:
        super().clean()
        if not isinstance(self.ethereum_address, str) or len(self.ethereum_address) != ETHEREUM_ADDRESS_LENGTH:
            raise ValidationError({
                'ethereum_address': f'The length of ethereum_address must be exactly {ETHEREUM_ADDRESS_LENGTH} characters.'
            })


class DepositClaim(Model):
    subtask = ForeignKey(Subtask, blank=True, null=True)
    payer_deposit_account = ForeignKey(DepositAccount)
    payee_ethereum_address = CharField(max_length=ETHEREUM_ADDRESS_LENGTH)
    concent_use_case = IntegerField()
    amount = IntegerField()
    tx_hash = CharField(max_length=64, blank=True, null=True, unique=True)
    created_at = DateTimeField(auto_now_add=True)
    modified_at = DateTimeField(auto_now=True)

    def clean(self) -> None:
        super().clean()
        if self.subtask is None and self.concent_use_case != ConcentUseCase.FORCED_PAYMENT:
            raise ValidationError({
                'subtask: Can be NULL if and only if concent_use_case is ForcedPayment'
            })
        if self.payer_deposit_account.ethereum_address == self.payee_ethereum_address:
            raise ValidationError({
                'payer_deposit_account': 'payer_deposit_account.ethereum_address '
                                         'cannot be the same as payee_ethereum_address'
            })
        if not isinstance(self.payer_deposit_account, DepositAccount):
            raise ValidationError({
                'payer_deposit_account': 'payer_deposit_account.ethereum_address must be string'
            })
        if self.payee_ethereum_address == self.payer_deposit_account.ethereum_address:
            raise ValidationError({
                'payee_ethereum_address': 'Address of the Ethereum account belonging to the entity '
                                          '(requestor, provider or Concent) who is supposed to receive the claim. '
                                          'Cannot be the same as payer_deposit_account.ethereum_address'
            })
        if not isinstance(self.payee_ethereum_address, str) or len(self.payee_ethereum_address) != ETHEREUM_ADDRESS_LENGTH:
            raise ValidationError({
                'payee_ethereum_address': f'Address of the Ethereum account belonging to the entity '
                                          f'(requestor, provider or Concent) must be string and must be exactly '
                                          f'{ETHEREUM_ADDRESS_LENGTH} characters.'
            })
        if not isinstance(self.amount, int) or self.amount <= 0:
            raise ValidationError({
                'amount': 'Amount must be integer and be greater than 0'
            })
        if not (self.tx_hash is None or isinstance(self.tx_hash, str)) or len(self.tx_hash) != 64:
            raise ValidationError({
                'tx_hash': 'The hash of the Ethereum transaction must be a string and 64 characters long'
            })
