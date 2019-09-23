from logging import getLogger
from typing import Any
from typing import Dict
from typing import Optional
from typing import List
from typing import Union

from uuid import UUID

from django.conf import settings
from django.core.exceptions import ValidationError

from golem_messages import message
from golem_messages.exceptions import MessageError
from golem_messages.message.concents import SubtaskResultsVerify
from golem_messages.message.tasks import RejectReportComputedTask
from golem_messages.message.tasks import ReportComputedTask
from golem_messages.message.tasks import SubtaskResultsAccepted
from golem_messages.message.tasks import SubtaskResultsRejected

from common.constants import ErrorCode
from common.exceptions import ConcentValidationError
from common.exceptions import NonPositivePriceTaskToComputeError
from common.helpers import get_current_utc_timestamp
from common.logging import log
from common.logging import LoggingLevel
from common.logging import log_payment_time_exceeded
from common.validations import validate_secure_hash_algorithm
from conductor.models import BlenderSubtaskDefinition
from core.constants import VALID_SCENE_FILE_PREFIXES
from core.constants import ETHEREUM_ADDRESS_LENGTH
from core.constants import GOLEM_PUBLIC_KEY_HEX_LENGTH
from core.constants import GOLEM_PUBLIC_KEY_LENGTH
from core.constants import MESSAGE_TASK_ID_MAX_LENGTH
from core.constants import SCENE_FILE_EXTENSION
from core.exceptions import BanksterTimestampError
from core.exceptions import FrameNumberValidationError
from core.exceptions import Http400
from core.exceptions import GolemMessageValidationError
from core.utils import adjust_format_name
from core.utils import hex_to_bytes_convert

logger = getLogger(__name__)


def validate_value_is_int_convertible_and_non_negative(value: int) -> None:
    """
    Checks if value is an integer. If not, tries to cast it to an integer.
    Then checks if value is non-negative.
    """
    if not isinstance(value, int):
        validate_value_is_int_convertible(value)
    validate_non_negative_integer_value(int(value))


def validate_value_is_int_convertible_and_positive(value: int) -> None:
    """
    Checks if value is an integer. If not, tries to cast it to an integer.
    Then checks if value is positive.
    """
    if not isinstance(value, int):
        validate_value_is_int_convertible(value)
    validate_positive_integer_value(int(value))


def validate_hex_public_key(value: str, field_name: str) -> None:
    validate_key_with_desired_parameters(field_name, value, str, GOLEM_PUBLIC_KEY_HEX_LENGTH)


def validate_bytes_public_key(value: bytes, field_name: str) -> None:
    validate_key_with_desired_parameters(field_name, value, bytes, GOLEM_PUBLIC_KEY_LENGTH)


def validate_key_with_desired_parameters(
    key_name: str,
    key_value: Union[bytes, str],
    expected_type: Any,
    expected_length: int
) -> None:
    validate_expected_value_type(key_value, key_name, expected_type)

    if len(key_value) != expected_length:
        raise ConcentValidationError(
            "The length of {} must be exactly {} characters.".format(key_name, expected_length),
            error_code=ErrorCode.MESSAGE_VALUE_WRONG_LENGTH,
        )


def validate_task_to_compute(task_to_compute: message.TaskToCompute) -> None:
    if not isinstance(task_to_compute, message.TaskToCompute):
        raise ConcentValidationError(
            f"Expected TaskToCompute instead of {type(task_to_compute).__name__}.",
            error_code=ErrorCode.MESSAGE_INVALID,
        )

    if any(map(lambda x: x is None, [getattr(task_to_compute, attribute) for attribute in [
        'compute_task_def',
        'provider_public_key',
        'requestor_public_key'
    ]])):
        raise ConcentValidationError(
            "Invalid TaskToCompute",
            error_code=ErrorCode.MESSAGE_WRONG_FIELDS,
        )
    if not task_to_compute.verify_all_promissory_notes(deposit_contract_address=settings.GNT_DEPOSIT_CONTRACT_ADDRESS):
        raise ConcentValidationError(
            "The signature of the PromissiryNote for the Provider, which should be signed by Requestor is incorrect",
            error_code=ErrorCode.MESSAGE_INVALID,
        )

    validate_compute_task_def(task_to_compute.compute_task_def)
    validate_hex_public_key(task_to_compute.provider_public_key, 'provider_public_key')
    validate_hex_public_key(task_to_compute.requestor_public_key, 'requestor_public_key')
    validate_secure_hash_algorithm(task_to_compute.package_hash)
    validate_positive_task_price(task_to_compute.price)


def validate_subtask_results_verify(msg: SubtaskResultsVerify, deposit_contract_address: str) -> None:
    if not msg.verify_concent_promissory_note(deposit_contract_address):
        raise ConcentValidationError(
            "The signature of the PromissiryNote for Concent is incorrect",
            error_code=ErrorCode.MESSAGE_INVALID,
        )


def validate_report_computed_task_time_window(report_computed_task: message.ReportComputedTask) -> None:
    assert isinstance(report_computed_task, message.ReportComputedTask)

    if report_computed_task.timestamp < report_computed_task.task_to_compute.timestamp:
        raise ConcentValidationError(
            "ReportComputedTask timestamp is older then nested TaskToCompute.",
            error_code=ErrorCode.MESSAGE_TIMESTAMP_TOO_OLD,
        )


def validate_all_messages_identical(golem_messages_list: List[message.Message]) -> None:
    assert isinstance(golem_messages_list, list)
    assert len(golem_messages_list) >= 1
    assert all(isinstance(golem_message, message.Message) for golem_message in golem_messages_list)
    assert len(set(type(golem_message) for golem_message in golem_messages_list)) == 1

    base_golem_message = golem_messages_list[0]

    for golem_message in golem_messages_list[1:]:
        if base_golem_message != golem_message:
            raise ConcentValidationError(
                f'Messages {base_golem_message.__class__.__name__} are not identical',
                error_code=ErrorCode.MESSAGES_NOT_IDENTICAL,
            )


def is_golem_message_signed_with_key(
    public_key: bytes,
    golem_message: message.base.Message,
) -> bool:
    """
    Validates if given Golem message is signed with given public key.

    :param golem_message: Instance of golem_messages.base.Message object.
    :param public_key: Client public key in bytes.
    :return: True if given Golem message is signed with given public key, otherwise False.
    """
    assert isinstance(golem_message, message.base.Message)

    validate_bytes_public_key(public_key, 'public_key')

    try:
        is_valid = golem_message.verify_signature(public_key)
    except MessageError as exception:
        is_valid = False
        log(
            logger,
            f'There was an exception when validating if golem_message {golem_message.__class__.__name__} is signed '
            f'with public key. Exception: {exception}.',
            client_public_key=public_key,
            logging_level=LoggingLevel.INFO
        )

    return is_valid


def validate_golem_message_subtask_results_rejected(
    subtask_results_rejected: message.tasks.SubtaskResultsRejected
) -> None:
    if not isinstance(subtask_results_rejected,  message.tasks.SubtaskResultsRejected):
        raise ConcentValidationError(
            "subtask_results_rejected should be of type:  SubtaskResultsRejected",
            error_code=ErrorCode.MESSAGE_INVALID,
        )
    validate_task_to_compute(subtask_results_rejected.report_computed_task.task_to_compute)


def validate_ethereum_addresses(requestor_ethereum_address: str, provider_ethereum_address: str) -> None:
    validate_key_with_desired_parameters(
        'requestor_ethereum_address',
        requestor_ethereum_address,
        str,
        ETHEREUM_ADDRESS_LENGTH
    )
    validate_key_with_desired_parameters(
        'provider_ethereum_address',
        provider_ethereum_address,
        str,
        ETHEREUM_ADDRESS_LENGTH
    )


def get_validated_client_public_key_from_client_message(golem_message: message.base.Message) -> Union[bytes, None]:
    if isinstance(golem_message, message.concents.ForcePayment):
        if (
            isinstance(golem_message.subtask_results_accepted_list, list) and
            len(golem_message.subtask_results_accepted_list) > 0
        ):
            task_to_compute = golem_message.subtask_results_accepted_list[0].task_to_compute
        else:
            raise ConcentValidationError(
                "subtask_results_accepted_list must be a list type and contains at least one message",
                error_code=ErrorCode.MESSAGE_VALUE_WRONG_LENGTH,
            )

    elif isinstance(golem_message, message.tasks.TaskMessage):
        if not golem_message.is_valid():
            raise GolemMessageValidationError(
                "Golem message invalid",
                error_code=ErrorCode.MESSAGE_INVALID
            )
        task_to_compute = golem_message.task_to_compute
    else:
        raise ConcentValidationError(
            "Unknown message type",
            error_code=ErrorCode.MESSAGE_UNKNOWN,
        )

    if task_to_compute is not None:
        if isinstance(golem_message, (
            message.concents.ForceReportComputedTask,
            message.concents.ForceSubtaskResults,
            message.concents.ForcePayment,
            message.concents.SubtaskResultsVerify,
        )):
            client_public_key = task_to_compute.provider_public_key
            validate_hex_public_key(client_public_key, 'provider_public_key')
        elif isinstance(golem_message, (
            message.tasks.AckReportComputedTask,
            message.tasks.RejectReportComputedTask,
            message.concents.ForceGetTaskResult,
            message.concents.ForceSubtaskResultsResponse,
        )):
            client_public_key = task_to_compute.requestor_public_key
            validate_hex_public_key(client_public_key, 'requestor_public_key')
        else:
            raise ConcentValidationError(
                "Unknown message type",
                error_code=ErrorCode.MESSAGE_UNKNOWN,
            )

        return hex_to_bytes_convert(client_public_key)

    return None


def validate_frames(frames_list: List[int]) -> None:
    if not isinstance(frames_list, list) or not len(frames_list) > 0:
        raise FrameNumberValidationError(
            'TaskToCompute must contain list of frames.',
            ErrorCode.MESSAGE_FRAME_WRONG_TYPE
        )

    for frame in frames_list:
        if not isinstance(frame, int):
            raise FrameNumberValidationError(
                'Frame must be integer',
                ErrorCode.MESSAGE_FRAME_VALUE_NOT_POSITIVE_INTEGER
            )

        if not frame > 0:
            raise FrameNumberValidationError(
                'Frame number must be grater than 0',
                ErrorCode.MESSAGE_FRAME_VALUE_NOT_POSITIVE_INTEGER
            )


def validate_expected_value_type(
    value: Any,
    value_name: str,
    expected_type: Any,
) -> None:
    if not isinstance(value, expected_type):
        raise ConcentValidationError(
            f"{value_name} must be {expected_type.__name__}.",
            error_code=ErrorCode.MESSAGE_VALUE_WRONG_TYPE,
        )


def validate_positive_integer_value(value: int) -> None:
    validate_expected_value_type(value, 'value', int)

    if value <= 0:
        raise ConcentValidationError(
            "Value cannot be a non-positive value",
            error_code=ErrorCode.MESSAGE_VALUE_NEGATIVE,
        )


def validate_non_negative_integer_value(value: int) -> None:
    validate_expected_value_type(value, 'value', int)

    if value < 0:
        raise ConcentValidationError(
            "Value cannot be a negative value",
            error_code=ErrorCode.MESSAGE_VALUE_NEGATIVE,
        )


def validate_value_is_int_convertible(value: int) -> None:
    try:
        int(value)
    except (ValueError, TypeError):
        raise ConcentValidationError(
            "Wrong type, expected a value that can be converted to an integer.",
            error_code=ErrorCode.MESSAGE_VALUE_NOT_INTEGER,
        )


def validate_scene_file(scene_file: str) -> None:
    if not scene_file.endswith(SCENE_FILE_EXTENSION):
        raise ConcentValidationError(
            f'{scene_file} must ends with {SCENE_FILE_EXTENSION} filename extension',
            ErrorCode.MESSAGE_INVALID
        )

    if not any(scene_file.startswith(file_path) for file_path in VALID_SCENE_FILE_PREFIXES):
        raise ConcentValidationError(
            f'{scene_file} path must starts with one of {VALID_SCENE_FILE_PREFIXES} paths',
            ErrorCode.MESSAGE_INVALID
        )


def validate_resolution(resolution: List[float]) -> None:
    if not isinstance(resolution, list):
        raise ConcentValidationError(
            'resolution is not a list',
            ErrorCode.MESSAGE_INVALID,
        )
    if len(resolution) != 2:
        raise ConcentValidationError(
            'resolution must contain exactly 2 values',
            ErrorCode.MESSAGE_INVALID,
        )
    for element in resolution:
        if not isinstance(element, int):
            raise ConcentValidationError(
                'resolution is not a list of integers',
                ErrorCode.MESSAGE_INVALID,
            )
        if element <= 0:
            raise ConcentValidationError(
                'resolution must contain positive integers',
                ErrorCode.MESSAGE_INVALID,
            )


def validate_use_compositing(use_compositing: bool) -> None:
    if not isinstance(use_compositing, bool):
        raise ConcentValidationError(
            'use_compositing must be a boolean',
            ErrorCode.MESSAGE_INVALID,
        )


def validate_samples(samples: int) -> None:
    if not isinstance(samples, int):
        raise ConcentValidationError(
            'samples must be integer',
            ErrorCode.MESSAGE_INVALID,
        )
    if samples < 0:
        raise ConcentValidationError(
            'samples must be bigger or equal zero',
            ErrorCode.MESSAGE_INVALID,
        )


def validate_crops(crops: List[Dict[str, List[float]]]) -> None:
    if not isinstance(crops, list):
        raise ConcentValidationError(
            "crops field in 'extra_data' must be a list",
            ErrorCode.MESSAGE_INVALID,
        )
    if len(crops) != 1:
        raise ConcentValidationError(
            "crops field must contain exactly one dict with borders details",
            ErrorCode.MESSAGE_INVALID,
        )
    crop_details = crops[0]
    mandatory_fields = ['borders_x', 'borders_y']
    for field in mandatory_fields:
        if field not in crop_details:
            raise ConcentValidationError(
                f'{field} does not exist in crop_details dict',
                ErrorCode.MESSAGE_INVALID,
            )
        if not isinstance(crop_details[field], list):
            raise ConcentValidationError(
                f'{field} is not a list',
                ErrorCode.MESSAGE_INVALID,
            )
        if len(crop_details[field]) != 2:
            raise ConcentValidationError(
                f'{field} must have exactly 2 fields',
                ErrorCode.MESSAGE_INVALID
            )
        for border in crop_details[field]:
            if not isinstance(border, float):
                raise ConcentValidationError(
                    f'{field} must contain float borders',
                    ErrorCode.MESSAGE_INVALID,
                )
            if border > 1.0 or border < 0.0:
                raise ConcentValidationError(
                    f'Border in {field} must has value between 0.0 and 1.0',
                    ErrorCode.MESSAGE_INVALID,
                )
        if crop_details[field][0] >= crop_details[field][1]:
            raise ConcentValidationError(
                f'Minimum of {field} can not be bigger or equal maximum',
                ErrorCode.MESSAGE_INVALID,
            )


def validate_blender_script_parameters(extra_data: Any) -> None:
    mandatory_fields = ['resolution', 'use_compositing', 'samples', 'crops']

    for field in mandatory_fields:
        if field not in extra_data:
            raise ConcentValidationError(
                f"{field} is missing in 'extra_data' in ComputeTaskDef",
                ErrorCode.MESSAGE_INVALID,
            )
    validate_resolution(extra_data['resolution'])
    validate_use_compositing(extra_data['use_compositing'])
    validate_samples(extra_data['samples'])
    validate_crops(extra_data['crops'])


def validate_compute_task_def(compute_task_def: message.tasks.ComputeTaskDef) -> None:
    string_fields = ["output_format", "scene_file"]
    other_mandatory_fields = ["frames"]

    validate_value_is_int_convertible_and_non_negative(compute_task_def['deadline'])

    validate_uuid(compute_task_def['task_id'])
    validate_uuid(compute_task_def['subtask_id'])

    extra_data = compute_task_def.get("extra_data")
    if extra_data is None:
        raise ConcentValidationError(
            "'extra_data' is missing in ComputeTaskDef",
            ErrorCode.MESSAGE_INVALID
        )

    for mandatory_data in string_fields + other_mandatory_fields:
        if mandatory_data not in extra_data:
            raise ConcentValidationError(
                f"{mandatory_data} is missing in ComputeTaskDef",
                ErrorCode.MESSAGE_INVALID
            )

    for string_field in string_fields:
        if not isinstance(extra_data[string_field], str):
            raise ConcentValidationError(
                f"{string_field} should be string",
                ErrorCode.MESSAGE_VALUE_NOT_STRING
            )

    validate_frames(extra_data["frames"])
    validate_blender_output_format(extra_data["output_format"])
    validate_scene_file(extra_data['scene_file'])


def validate_that_golem_messages_are_signed_with_key(
    public_key: bytes,
    *golem_messages: message.base.Message,
) -> None:
    for golem_message in golem_messages:
        if not is_golem_message_signed_with_key(public_key, golem_message):
            raise Http400(
                f'There was an exception when validating if golem_message {golem_message.__class__.__name__} is signed with '
                f'public key {public_key}.',
                error_code=ErrorCode.MESSAGE_SIGNATURE_WRONG,
            )


def validate_reject_report_computed_task(client_message: RejectReportComputedTask) -> None:
    if (
        isinstance(client_message.cannot_compute_task, message.CannotComputeTask) and
        isinstance(client_message.task_failure, message.TaskFailure)
    ):
        raise GolemMessageValidationError(
            "RejectReportComputedTask cannot contain CannotComputeTask and TaskFailure at the same time.",
            error_code=ErrorCode.MESSAGE_INVALID,
        )

    if client_message.reason is None:
        raise GolemMessageValidationError(
            f'Error during handling RejectReportComputedTask. REASON is None, it should be message.tasks.RejectReportComputedTask.REASON instance',
            error_code=ErrorCode.MESSAGE_VALUE_WRONG_TYPE
        )

    if not isinstance(client_message.reason, RejectReportComputedTask.REASON):
        raise GolemMessageValidationError(
            f'Error during handling RejectReportComputedTask. REASON should be message.tasks.RejectReportComputedTask.REASON instance. '
            f'Currently it is {type(client_message.reason)} instance',
            error_code=ErrorCode.MESSAGE_VALUE_WRONG_TYPE
        )
    validate_task_to_compute(client_message.task_to_compute)

    validate_that_golem_messages_are_signed_with_key(
        hex_to_bytes_convert(client_message.task_to_compute.requestor_public_key),
        client_message.task_to_compute,
    )


def validate_uuid(id_: str) -> None:
    if not isinstance(id_, str):
        raise ConcentValidationError(
            f'ID must be string with maximum {MESSAGE_TASK_ID_MAX_LENGTH} characters length',
            error_code=ErrorCode.MESSAGE_WRONG_UUID_TYPE
        )
    try:
        UUID(id_, version=4)
    except ValueError:
        raise ConcentValidationError(
            'ID must be a UUID derivative.',
            error_code=ErrorCode.MESSAGE_WRONG_UUID_VALUE,
        )


def validate_database_task_to_compute(
        task_to_compute: message.tasks.TaskToCompute,
        message_to_compare: message.Message
) -> None:
    if message_to_compare.task_to_compute != task_to_compute:
        raise ValidationError({
            message_to_compare.__class__.__name__: (
                'Nested TaskToCompute message must be the same as TaskToCompute stored separately'
            )
        })


def validate_database_report_computed_task(
        report_computed_task: message.tasks.ReportComputedTask,
        message_to_compare: message.Message
) -> None:
    if message_to_compare.report_computed_task != report_computed_task:
        raise ValidationError({
            message_to_compare.__class__.__name__: (
                'Nested ReportComputedTask message must be the same as ReportComputedTask stored separately'
            )
        })


def substitute_new_report_computed_task_if_needed(
        report_computed_task_from_acknowledgement: ReportComputedTask,
        stored_report_computed_task: ReportComputedTask
) -> Optional[ReportComputedTask]:
    """
    If stored ReportComputedTask (previously sent by Provider in ForceReportComputedTask message) is different than
    ReportComputedTask sent by Requestor (in AckReportComputedTask), it means that Provider had sent different
    ReportComputedTask to Requestor and the message stored in the DB must be replaced.
    """
    new_report_computed_task = None
    try:
        validate_all_messages_identical([
            report_computed_task_from_acknowledgement,
            stored_report_computed_task,
        ])
    except ConcentValidationError:
        new_report_computed_task = report_computed_task_from_acknowledgement

    return new_report_computed_task


def validate_list_of_transaction_timestamp(acceptances: List[SubtaskResultsAccepted]) -> None:
    """
    Validate if cut_off_time < youngest_payment_ts(T2) + PDT, unless requestor already made some payment.
    We compare only youngest payment_ts, because we want to use the highest value of timestamp. Other payment_ts might
    give false positives.
    """

    cut_off_time = get_current_utc_timestamp()
    youngest_payment_ts = max(subtask_results_accepted.payment_ts for subtask_results_accepted in acceptances)

    if youngest_payment_ts > cut_off_time - settings.PAYMENT_DUE_TIME:
        log_payment_time_exceeded(logger, acceptances)
        raise BanksterTimestampError


def validate_positive_task_price(price: int) -> None:
    try:
        validate_positive_integer_value(price)
    except ConcentValidationError:
        raise NonPositivePriceTaskToComputeError(
            "Value cannot be a non-positive value",
            error_code=ErrorCode.MESSAGE_VALUE_NEGATIVE
        )


def validate_blender_output_format(output_format: str) -> None:
    if adjust_format_name(output_format) not in BlenderSubtaskDefinition.OutputFormat.__members__.keys():
        raise ConcentValidationError(
            f'Unsupported Blender format!',
            error_code=ErrorCode.MESSAGE_VALUE_NOT_ALLOWED
        )


def validate_subtask_results_rejected_reason(
        client_message: SubtaskResultsRejected,
) -> None:
    if client_message.reason == SubtaskResultsRejected.REASON.VerificationNegative:
        pass
    elif client_message.reason == SubtaskResultsRejected.REASON.ForcedResourcesFailure:
        force_get_task_result_failed = client_message.force_get_task_result_failed
        if isinstance(force_get_task_result_failed, message.concents.ForceGetTaskResultFailed):
            if force_get_task_result_failed.subtask_id != client_message.subtask_id:
                raise GolemMessageValidationError(
                    f"ForceGetTaskResultsFailed subtask_id does not match with SubtaskResultsRejected TaskToCompute subtask_id.",
                    error_code=ErrorCode.MESSAGE_INVALID,
                )
        else:
            raise GolemMessageValidationError(
                f"SubtaskResultsRejected hasn't got instance of ForceGetTaskResultsFailed message",
                error_code=ErrorCode.MESSAGE_INVALID,
            )
    else:
        raise GolemMessageValidationError(
            f'Error during handling SubtaskResultsRejected. Only VerificationNegative or ForcedResourcesFailure reasons'
            f' are supported by Concent.',
            error_code=ErrorCode.MESSAGE_VALUE_WRONG_TYPE
        )
