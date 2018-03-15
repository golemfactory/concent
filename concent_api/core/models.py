import base64

from django.core.validators import ValidationError
from django.db.models       import BinaryField
from django.db.models       import BooleanField
from django.db.models       import CharField
from django.db.models       import DateTimeField
from django.db.models       import DecimalField
from django.db.models       import ForeignKey
from django.db.models       import Model
from django.db.models       import OneToOneField
from django.db.models       import PositiveSmallIntegerField
from django.db.models       import Manager
from django.utils           import timezone

from golem_messages         import message

from utils.fields           import Base64Field
from utils.fields           import ChoiceEnum

from .constants             import GOLEM_PUBLIC_KEY_LENGTH
from .constants             import MESSAGE_TASK_ID_MAX_LENGTH


class StoredMessage(Model):
    type        = PositiveSmallIntegerField()
    timestamp   = DateTimeField()
    data        = BinaryField()
    task_id     = CharField(max_length = MESSAGE_TASK_ID_MAX_LENGTH, null = True, blank = True)
    subtask_id  = CharField(max_length = MESSAGE_TASK_ID_MAX_LENGTH, null = True, blank = True)

    def __str__(self):
        return 'StoredMessage #{}, type:{}, {}'.format(self.id, self.type, self.timestamp)


class ClientManager(Manager):

    def get_or_create_full_clean(self, public_key: bytes):
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


class Subtask(Model):
    """
    Represents subtask states.
    """

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
    }

    # Defines in which states given related message must be None.
    UNSET_RELATED_MESSAGES_IN_STATES = {
        'task_to_compute': {},
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
    }

    # Defines related golem message for related stored messages
    MESSAGE_FOR_FIELD = {
        'task_to_compute':              message.TaskToCompute,
        'report_computed_task':         message.ReportComputedTask,
        'ack_report_computed_task':     message.AckReportComputedTask,
        'reject_report_computed_task':  message.RejectReportComputedTask,
        'subtask_results_accepted':     message.tasks.SubtaskResultsAccepted,
        'subtask_results_rejected':     message.tasks.SubtaskResultsRejected,
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

    class Meta:
        unique_together = (
            ('requestor', 'task_id'),
            ('requestor', 'subtask_id'),
        )

    task_id                     = CharField(max_length = MESSAGE_TASK_ID_MAX_LENGTH)

    # Golem clients are not guaranteed to use unique subtask_id because they are UUIDs,
    # but Concent at this moment does not support subtasks with non-unique IDs.
    # However, the combination of requestor's public key and subtask ID is guaranteed to be unique.
    subtask_id                  = CharField(max_length = MESSAGE_TASK_ID_MAX_LENGTH, unique = True, db_index = True)

    # Relation to concent client in requestor context.
    requestor                   = ForeignKey(Client, related_name = 'subtasks_as_requestor')

    # Relation to concent client in provider context.
    provider                    = ForeignKey(Client, related_name = 'subtasks_as_provider')

    state                       = CharField(max_length = 32, choices = SubtaskState.choices())

    # If in an active state, it's the time at which Concent automatically transitions to a passive state if it does
    # not get the information it expects from the client (a timeout). Must be NULL in a passive state.
    next_deadline               = DateTimeField(blank = True, null = True)

    # Related messages
    task_to_compute             = OneToOneField(StoredMessage, blank = True, null = True, related_name = 'subtasks_for_task_to_compute')
    report_computed_task        = OneToOneField(StoredMessage, blank = True, null = True, related_name = 'subtasks_for_report_computed_task')
    ack_report_computed_task    = OneToOneField(StoredMessage, blank = True, null = True, related_name = 'subtasks_for_ack_report_computed_task')
    reject_report_computed_task = OneToOneField(StoredMessage, blank = True, null = True, related_name = 'subtasks_for_reject_report_computed_task')
    subtask_results_accepted    = OneToOneField(StoredMessage, blank = True, null = True, related_name = 'subtasks_for_subtask_results_accepted')
    subtask_results_rejected    = OneToOneField(StoredMessage, blank = True, null = True, related_name = 'subtasks_for_subtask_results_rejected')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._current_state_name = None

    @classmethod
    def from_db(cls, db, field_names, values):
        new = super().from_db(db, field_names, values)
        new._current_state_name = new.state  # pylint: disable=no-member
        return new

    def clean(self):
        super().clean()

        # next_deadline can be None only for passive states
        if not self._state.adding and self.next_deadline is None and self.state_enum not in self.PASSIVE_STATES:
            raise ValidationError({
                'next_deadline': 'next_deadline is None for active state.'
            })

        # next_deadline must be None in passive states
        if not self._state.adding and self.next_deadline is not None and self.state_enum in self.PASSIVE_STATES:
            raise ValidationError({
                'next_deadline': 'next_deadline is not None for passive state.'
            })

        # State transition can happen only by defined rule
        # but not when we create new object
        # and not when state is not being changed
        if (
            not self._state.adding and
            self._current_state_enum != self.state_enum and
            self._current_state_enum not in self.POSSIBLE_TRANSITIONS_TO[self.state_enum]
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

    @property
    def state_enum(self):
        return Subtask.SubtaskState[self.state]

    @property
    def _current_state_enum(self):
        return Subtask.SubtaskState[self._current_state_name]


class PendingResponse(Model):
    """
    Stores information about messages to be returned from the `receive` or `receive-out-of-band` endpoint.
    """

    class ResponseType(ChoiceEnum):
        ForceReportComputedTask         = 'ForceReportComputedTask'
        ForceReportComputedTaskResponse = 'ForceReportComputedTaskResponse'
        VerdictReportComputedTask       = 'VerdictReportComputedTask'
        ForceGetTaskResultRejected      = 'ForceGetTaskResultRejected'
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
    def response_type_enum(self):
        return PendingResponse.ResponseType[self.response_type]

    response_type        = CharField(max_length = 32, choices = ResponseType.choices())
    client               = ForeignKey(Client)
    queue                = CharField(max_length = 32, choices = Queue.choices())

    # TRUE if the client has already fetched the message.
    delivered            = BooleanField(default = False)

    subtask              = ForeignKey(Subtask, blank = True, null = True)
    created_at           = DateTimeField(default = timezone.now)

    def clean(self):
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
    task_owner_key          = Base64Field(max_length = 64)
    provider_eth_account    = Base64Field(max_length = 64)
    amount_paid             = DecimalField(max_digits = 10, decimal_places = 2)
    recipient_type          = CharField(max_length = 32, choices = RecipientType.choices())
    amount_pending          = DecimalField(max_digits = 10, decimal_places = 2)
    pending_response        = ForeignKey(PendingResponse, related_name = 'payments')
