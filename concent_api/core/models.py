import base64

from django.contrib.postgres.fields import JSONField
from django.core.validators import validate_ipv4_address
from django.core.validators import ValidationError
from django.db.models       import BinaryField
from django.db.models       import BooleanField
from django.db.models       import CharField
from django.db.models       import DateTimeField
from django.db.models       import DecimalField
from django.db.models       import IntegerField
from django.db.models       import ForeignKey
from django.db.models       import Model
from django.db.models       import OneToOneField
from django.db.models       import PositiveSmallIntegerField
from django.db.models       import PositiveIntegerField
from django.db.models       import TextField
from django.db.models       import Manager
from django.utils           import timezone

from constance              import config
from golem_messages         import message

from core.exceptions        import ConcentInSoftShutdownMode
from utils.fields           import Base64Field
from utils.fields           import ChoiceEnum
from .model_validators import validate_amount_paid

from .constants             import TASK_OWNER_KEY_LENGTH
from .constants             import ETHEREUM_ADDRESS_LENGTH
from .constants             import GOLEM_PUBLIC_KEY_LENGTH
from .constants             import HASH_FUNCTION
from .constants             import HASH_LENGTH
from .constants             import MESSAGE_TASK_ID_MAX_LENGTH
from .constants             import NUMBER_OF_ALL_PORTS


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
    task_to_compute = OneToOneField(StoredMessage, related_name='subtasks_for_task_to_compute')
    report_computed_task = OneToOneField(StoredMessage, related_name='subtasks_for_report_computed_task')
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

        # Concent should not accept anything that cause a transition to an active state in soft shutdown mode.
        if config.SOFT_SHUTDOWN_MODE is True and self.state_enum in self.ACTIVE_STATES:
            raise ConcentInSoftShutdownMode

        # next_deadline must be int only for active states
        if not self._state.adding and not isinstance(self.next_deadline, int) and self.state_enum in self.ACTIVE_STATES:
            raise ValidationError({
                'next_deadline': 'next_deadline must be int for active state.'
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
    task_owner_key          = BinaryField()
    provider_eth_account    = CharField(max_length = ETHEREUM_ADDRESS_LENGTH)
    amount_paid             = IntegerField(validators = [validate_amount_paid])
    recipient_type          = CharField(max_length = 32, choices = RecipientType.choices())
    amount_pending          = IntegerField()
    pending_response        = ForeignKey(PendingResponse, related_name = 'payments')

    def clean(self):
        if self.task_owner_key == self.provider_eth_account:
            raise ValidationError({
                'provider_eth_account': 'Provider ethereum account address must be diffrent than task owner key'
            })

        if not isinstance(self.amount_pending, int) or self.amount_pending <= 0:
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


class AbstractMessageModel(Model):

    sig = BinaryField()
    timestamp = IntegerField()
    encrypted = BooleanField(default = False)

    class Meta:
        abstract = True


class StoredComputeTaskDef(AbstractMessageModel):

    # Defines items list from ComputeTaskDef
    ITEMS = [
        'task_id',
        'subtask_id',
        'deadline',
        'src_code',
        'extra_data',
        'short_description',
        'working_directory',
        'performance',
        'docker_images',
    ]

    task_id = CharField(max_length=MESSAGE_TASK_ID_MAX_LENGTH)
    subtask_id = CharField(max_length=MESSAGE_TASK_ID_MAX_LENGTH)
    deadline = DateTimeField(blank = True, null = True)
    src_code = TextField()
    extra_data = JSONField()
    short_description = TextField()
    working_directory = TextField()
    performance = DecimalField(decimal_places=2, max_digits=3)
    docker_images = JSONField()

    if not len(ITEMS) == len(message.tasks.ComputeTaskDef.ITEMS.keys()):
        raise ValidationError({
            'ComputeTaskDef': 'StoredComputeTaskDef model has not same fields as golem_messages.message.tasks.ComputeTaskDef()'
        })

    for model_item, golem_message_item in zip(ITEMS, message.tasks.ComputeTaskDef.ITEMS.keys()):
        if not model_item == golem_message_item:
            raise ValidationError({
                'ComputeTaskDef': 'StoredComputeTaskDef model has not same fields as golem_messages.message.tasks.ComputeTaskDef()'
            })
    '''
    VALIDATION FOR task_id
    VALIDATION FOR subtask_id
    VALIDATION FOR deadline
    VALIDATION FOR src_code
    VALIDATION FOR extra_data
    VALIDATION FOR short_description
    VALIDATION FOR working_directory
    VALIDATION FOR performance
    VALIDATION FOR docker_images
    '''


class StoredTaskToCompute(AbstractMessageModel):

    ITEMS = [
        'requestor_id',
        'requestor_public_key',
        'requestor_ethereum_public_key',
        'provider_id',
        'provider_public_key',
        'provider_ethereum_public_key',
        'compute_task_def',
        'package_hash',
        'concent_enabled',
        'price',
        'header',
        'sig',
    ]

    requestor_id = BinaryField()
    requestor_public_key = BinaryField()
    requestor_ethereum_public_key = BinaryField()
    provider_id = BinaryField()
    provider_public_key = BinaryField()
    provider_ethereum_public_key = BinaryField()
    compute_task_def = ForeignKey(StoredComputeTaskDef)
    package_hash = CharField(max_length=HASH_LENGTH)
    concent_enabled = BooleanField(default=False)
    price = PositiveIntegerField()

    if not len(ITEMS) == len(message.tasks.TaskToCompute.__slots__):
        raise ValidationError({
            'StoredTaskToCompute': 'StoredTaskToCompute model has not same fields as golem_messages.message.tasks.TaskToCompute()'
        })

    for model_item, golem_message_item in zip(ITEMS, message.tasks.TaskToCompute.__slots__):
        if not model_item == golem_message_item:
            raise ValidationError({
                'StoredTaskToCompute': 'StoredTaskToCompute model has not same fields as golem_messages.message.tasks.TaskToCompute()'
            })

    def clean(self):
        fields = {
            'requestor_id': self.requestor_id,
            'requestor_public_key': self.requestor_public_key,
            'requestor_ethereum_public_key': self.requestor_ethereum_public_key,
            'provider_id': self.provider_id,
            'provider_public_key': self.provider_public_key,
            'provider_ethereum_public_key': self.provider_ethereum_public_key
        }
        for field in fields:
            if not len(fields[field]) == GOLEM_PUBLIC_KEY_LENGTH or not isinstance(fields[field], bytes):
                raise ValidationError({
                    f'{field}': f'{field} must be bytes instance and must have length equal to {GOLEM_PUBLIC_KEY_LENGTH}'   
                })

        if not self.package_hash[:4] == HASH_FUNCTION:
            raise ValidationError({
                'package_hash': f'package_hash should be hashed with {HASH_FUNCTION} function'
            })

        if not len(self.package_hash) == HASH_LENGTH:
            raise ValidationError({
                'package_hash': f'package_hash should has length equal to {HASH_LENGTH}'
            })

        if not isinstance(self.concent_enabled, bool):
            raise ValidationError({
                'concent_enabled': 'concent_enabled should be instance of boolean'
            })

        if not isinstance(self.price, int) or not self.price >= 0:
            raise ValidationError({
                'price': 'Price must be an integer and bigger than or equal 0'
            })


class StoredTaskFailure(AbstractMessageModel):

    ITEMS = [
        'task_to_compute',
        'err',
        'header',
        'sig',
    ]

    if not len(ITEMS) == len(message.tasks.TaskFailure.__slots__):
        raise ValidationError({
            'StoredTaskFailure': 'StoredTaskFailure model has not same fields as golem_messages.message.tasks.TaskFailure()'
        })

    for model_item, golem_message_item in zip(ITEMS, message.tasks.TaskFailure.__slots__):
        if not model_item == golem_message_item:
            raise ValidationError({
                'StoredTaskFailure': 'StoredTaskFailure model has not same fields as golem_messages.message.tasks.TaskFailure()'
            })

    task_to_compute = ForeignKey(StoredTaskToCompute)
    err = TextField()

    '''
    VALIDATION FOR err
    '''


class StoredCannotComputeTask(AbstractMessageModel):

    ITEMS = [
        'task_to_compute',
        'reason',
        'header',
        'sig',
    ]

    if not len(ITEMS) == len(message.tasks.CannotComputeTask.__slots__):
        raise ValidationError({
            'StoredCannotComputeTask': 'StoredCannotComputeTask model has not same fields as golem_messages.message.tasks.CannotComputeTask()'
        })

    for model_item, golem_message_item in zip(ITEMS, message.tasks.CannotComputeTask.__slots__):
        if not model_item == golem_message_item:
            raise ValidationError({
                'StoredCannotComputeTask': 'StoredCannotComputeTask model has not same fields as golem_messages.message.tasks.CannotComputeTask()'
            })

    class CannotComputeTaskReason(ChoiceEnum):
        WrongCTD = 'WrongCTD'
        WrongKey = 'WrongKey'
        WrongAddress = 'WrongAddress'
        WrongEnvironment = 'WrongEnvironment'
        NoSourceCode = 'NoSourceCode'
        WrongDockerImages = 'WrongDockerImages'
        ConcentRequired = 'ConcentRequired'
        ConcentDisabled = 'ConcentDisabled'

    if not len(CannotComputeTaskReason.__members__) == len(message.tasks.CannotComputeTask.REASON.__members__):
        raise ValidationError({
            'CannotComputeTaskReason': 'CannotComputeTaskReason Enum has not same fields as golem_messages.message.tasks.CannotComputeTask.REASON'
        })

    for model_item, golem_message_item in zip(CannotComputeTaskReason.__members__, message.tasks.CannotComputeTask.REASON.__members__):
        if not model_item == golem_message_item:
            raise ValidationError({
                'CannotComputeTaskReason': 'CannotComputeTaskReason Enum has not same fields as golem_messages.message.tasks.CannotComputeTask.REASON'
            })

    task_to_compute = ForeignKey(StoredTaskToCompute)
    reason = CharField(max_length=32, choices=CannotComputeTaskReason.choices())


class StoredReportComputedTask(AbstractMessageModel):

    ITEMS = [
        'result_type',
        'node_name',
        'address',
        'node_info',
        'port',
        'key_id',
        'extra_data',
        'eth_account',
        'task_to_compute',
        'size',
        'package_hash',
        'multihash',
        'secret',
        'options',
        'header',
        'sig',
    ]

    if not len(ITEMS) == len(message.tasks.ReportComputedTask.__slots__):
        raise ValidationError({
            'StoredReportComputedTask': 'StoredReportComputedTask model has not same fields as golem_messages.message.tasks.ReportComputedTask()'
        })

    for model_item, golem_message_item in zip(ITEMS, message.tasks.ReportComputedTask.__slots__):
        if not model_item == golem_message_item:
            raise ValidationError({
                'StoredReportComputedTask': 'StoredReportComputedTask model has not same fields as golem_messages.message.tasks.ReportComputedTask()'
            })

    result_type = PositiveSmallIntegerField()
    node_name = CharField(max_length=32)
    address = CharField(max_length=15)
    node_info = JSONField()
    port = PositiveIntegerField()
    key_id = BinaryField()
    extra_data = JSONField()
    eth_account = CharField(max_length=32)
    task_to_compute = ForeignKey(StoredTaskToCompute)
    size = PositiveIntegerField()
    package_hash = CharField(max_length=HASH_LENGTH)
    multihash = CharField(max_length=HASH_LENGTH)
    secret = TextField()
    options = TextField()

    def clean(self):
        '''
        VALIDATION FOR result_type
        VALIDATION FOR node_name
        '''
        try:
            validate_ipv4_address(self.address)
        except ValidationError:
            return ValidationError({
                'address': 'Address field is not valid IPv4 address'
            })
        '''
        VALIDATION FOR node_info
        '''
        if not isinstance(self.port, int) or self.port > NUMBER_OF_ALL_PORTS:
            return ValidationError({
                'port': f'Port must be integer and must be beetwen 0 and {NUMBER_OF_ALL_PORTS}'
            })

        if not isinstance(self.key_id, bytes) or not len(self.key_id) == GOLEM_PUBLIC_KEY_LENGTH:
            return ValidationError({
                'key_id': f'key_id must be bytes instance and must have length equal to {GOLEM_PUBLIC_KEY_LENGTH}'
            })
        '''
        VALIDATION FOR extra_data
        '''
        if not isinstance(self.eth_account, str) or not len(self.eth_account) == ETHEREUM_ADDRESS_LENGTH:
            raise ValidationError({
                'eth_account': f'ethereum account address must be a string with {ETHEREUM_ADDRESS_LENGTH} characters'
            })
        '''
        VALIDATION FOR size
        '''
        if not self.package_hash[:4] == HASH_FUNCTION:
            raise ValidationError({
                'package_hash': f'package_hash should be hashed with {HASH_FUNCTION} function'
            })

        if not len(self.package_hash) == HASH_LENGTH:
            raise ValidationError({
                'package_hash': f'package_hash should has length equal to {HASH_LENGTH}'
            })

        if not self.multihash[:4] == HASH_FUNCTION:
            raise ValidationError({
                'multihash': f'multihash should be hashed with {HASH_FUNCTION} function'
            })

        if not len(self.multihash) == HASH_LENGTH:
            raise ValidationError({
                'multihash': f'multihash should has length equal to {HASH_LENGTH}'
            })
        '''
        VALIDATION FOR secret
        VALIDATION FOR options
        '''


class StoredAckReportComputedTask(AbstractMessageModel):

    ITEMS = [
        'report_computed_task',
        'header',
        'sig',
    ]

    if not len(ITEMS) == len(message.tasks.AckReportComputedTask.__slots__):
        raise ValidationError({
            'StoredAckReportComputedTask': 'StoredAckReportComputedTask model has not same fields as golem_messages.message.tasks.AckReportComputedTask()'
        })

    for model_item, golem_message_item in zip(ITEMS, message.tasks.AckReportComputedTask.__slots__):
        if not model_item == golem_message_item:
            raise ValidationError({
                'StoredAckReportComputedTask': 'StoredAckReportComputedTask model has not same fields as golem_messages.message.tasks.AckReportComputedTask()'
            })

    report_computed_task = ForeignKey(StoredReportComputedTask)


class StoredRejectReportComputedTask(AbstractMessageModel):

    ITEMS = [
        'attached_task_to_compute',
        'task_failure',
        'cannot_compute_task',
        'reason',
        'header',
        'sig',
    ]

    if not len(ITEMS) == len(message.tasks.RejectReportComputedTask.__slots__):
        raise ValidationError({
            'StoredRejectReportComputedTask': 'StoredRejectReportComputedTask model has not same fields as golem_messages.message.tasks.RejectReportComputedTask()'
        })

    for model_item, golem_message_item in zip(ITEMS, message.tasks.RejectReportComputedTask.__slots__):
        if not model_item == golem_message_item:
            raise ValidationError({
                'StoredRejectReportComputedTask': 'StoredRejectReportComputedTask model has not same fields as golem_messages.message.tasks.RejectReportComputedTask()'
            })

    class RejectReason(ChoiceEnum):
        SubtaskTimeLimitExceeded = 'SubtaskTimeLimitExceeded'
        GotMessageCannotComputeTask = 'GotMessageCannotComputeTask'
        GotMessageTaskFailure = 'GotMessageTaskFailure'

    if not len(RejectReason.__members__) == len(message.tasks.RejectReportComputedTask.REASON.__members__):
        raise ValidationError({
            'RejectReason': 'RejectReason Enum has not same fields as golem_messages.message.tasks.RejectReportComputedTask.REASON'
        })

    for model_item, golem_message_item in zip(RejectReason.__members__, message.tasks.RejectReportComputedTask.REASON.__members__):
        if not model_item == golem_message_item:
            raise ValidationError({
                'RejectReason': 'RejectReason Enum has not same fields as golem_messages.message.tasks.RejectReportComputedTask.REASON'
            })

    attached_task_to_compute = ForeignKey(StoredTaskToCompute)
    task_failure = ForeignKey(StoredTaskFailure)
    cannot_compute_task = ForeignKey(StoredCannotComputeTask)
    reason = CharField(max_length=32, choices=RejectReason.choices())

    def clean(self):
        if self.attached_task_to_compute and self.reason is not self.RejectReason.SubtaskTimeLimitExceeded:
            raise ValidationError({
                'attached_task_to_compute': "'SubtaskTimeLimitExceeded' is only right reason when TaskToCompute message is attached to RejectReportComputedTask"
            })

        if self.task_failure and self.reason is not self.RejectReason.GotMessageTaskFailure:
            raise ValidationError({
                'task_failure': "'GotMessageTaskFailure' is only right reason when TaskFailure message is attached to RejectReportComputedTask"
            })

        if self.cannot_compute_task and self.reason is not self.RejectReason.GotMessageCannotComputeTask:
            raise ValidationError({
                'cannot_compute_task': "'GotMessageCannotComputeTask' is only right reason when CannotComputeTask message is attached to RejectReportComputedTask"
            })


class StoredSubtaskResultsAccepted(AbstractMessageModel):

    ITEMS = [
        'payment_ts',
        'task_to_compute',
        'header',
        'sig',
    ]

    if not len(ITEMS) == len(message.tasks.SubtaskResultsAccepted.__slots__):
        raise ValidationError({
            'StoredSubtaskResultsAccepted': 'StoredSubtaskResultsAccepted model has not same fields as golem_messages.message.tasks.SubtaskResultsAccepted()'
        })

    for model_item, golem_message_item in zip(ITEMS, message.tasks.SubtaskResultsAccepted.__slots__):
        if not model_item == golem_message_item:
            raise ValidationError({
                'StoredSubtaskResultsAccepted': 'StoredSubtaskResultsAccepted model has not same fields as golem_messages.message.tasks.SubtaskResultsAccepted()'
            })

    payment_ts = IntegerField()
    task_to_compute = ForeignKey(StoredTaskToCompute)


class StoredSubtaskResultsRejected(AbstractMessageModel):

    ITEMS = [
        'report_computed_task',
        'reason',
        'header',
        'sig',
    ]

    if not len(ITEMS) == len(message.tasks.SubtaskResultsRejected.__slots__):
        raise ValidationError({
            'StoredSubtaskResultsRejected': 'StoredSubtaskResultsRejected model has not same fields as golem_messages.message.tasks.SubtaskResultsRejected()'
        })

    for model_item, golem_message_item in zip(ITEMS, message.tasks.SubtaskResultsRejected.__slots__):
        if not model_item == golem_message_item:
            raise ValidationError({
                'StoredSubtaskResultsRejected': 'StoredSubtaskResultsRejected model has not same fields as golem_messages.message.tasks.SubtaskResultsRejected()'
            })

    class SubtaskResultsRejectedReason(ChoiceEnum):
        VerificationNegative = 'VerificationNegative'
        ConcentResourcesFailure = 'ConcentResourcesFailure'
        ConcentVerificationNegative = 'ConcentVerificationNegative'
        ForcedResourcesFailure ='ForcedResourcesFailure'
        ResourcesFailure = 'ResourcesFailure'

    if not len(SubtaskResultsRejectedReason.__members__) == len(message.tasks.SubtaskResultsRejected.REASON.__members__):
        raise ValidationError({
            'SubtaskResultsRejectedReason': 'SubtaskResultsRejectedReason Enum has not same fields as golem_messages.message.tasks.SubtaskResultsRejected.REASON'
        })

    for model_item, golem_message_item in zip(SubtaskResultsRejectedReason.__members__, message.tasks.SubtaskResultsRejected.REASON.__members__):
        if not model_item == golem_message_item:
            raise ValidationError({
                'SubtaskResultsRejectedReason': 'SubtaskResultsRejectedReason Enum has not same fields as golem_messages.message.tasks.SubtaskResultsRejected.REASON'
            })

    report_computed_task = ForeignKey(StoredReportComputedTask)
    reason = CharField(max_length=32, choices=SubtaskResultsRejectedReason.choices())
