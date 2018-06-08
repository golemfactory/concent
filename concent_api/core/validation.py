from typing import List
from typing import Union
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator

from golem_messages                 import message
from golem_messages.exceptions      import MessageError
from golem_messages.message import FileTransferToken

from core.constants                 import ETHEREUM_ADDRESS_LENGTH
from core.constants                 import GOLEM_PUBLIC_KEY_LENGTH
from core.constants                 import GOLEM_PUBLIC_KEY_HEX_LENGTH
from core.constants                 import MESSAGE_TASK_ID_MAX_LENGTH
from core.constants import VALID_ID_REGEX
from core.constants import VALID_SHA1_HASH_REGEX
from core.exceptions import FileTransferTokenError
from core.exceptions import Http400
from core.utils import hex_to_bytes_convert
from gatekeeper.enums import HashingAlgorithm
from utils.helpers import join_messages
from utils.constants                import ErrorCode


def validate_int_value(value):
    """
    Checks if value is an integer. If not, tries to cast it to an integer.
    Then checks if value is non-negative.

    """
    if not isinstance(value, int):
        try:
            value = int(value)
        except (ValueError, TypeError):
            raise Http400(
                "Wrong type, expected a value that can be converted to an integer.",
                error_code=ErrorCode.MESSAGE_VALUE_NOT_INTEGER,
            )
    if value < 0:
        raise Http400(
            "Wrong type, expected non-negative integer but negative integer provided.",
            error_code=ErrorCode.MESSAGE_VALUE_WRONG_TYPE,
        )
    return value


def validate_id_value(value, field_name):
    if not isinstance(value, str):
        raise Http400(
            "{} must be string.".format(field_name),
            error_code=ErrorCode.MESSAGE_VALUE_WRONG_TYPE,
        )

    if value == '':
        raise Http400(
            "{} cannot be blank.".format(field_name),
            error_code=ErrorCode.MESSAGE_VALUE_BLANK,
        )

    if len(value) > MESSAGE_TASK_ID_MAX_LENGTH:
        raise Http400(
            "{} cannot be longer than {} chars.".format(field_name, MESSAGE_TASK_ID_MAX_LENGTH),
            error_code=ErrorCode.MESSAGE_VALUE_WRONG_LENGTH,
        )

    if VALID_ID_REGEX.fullmatch(value) is None:
        raise Http400(
            f'{field_name} must contain only alphanumeric chars.',
            error_code=ErrorCode.MESSAGE_VALUE_NOT_ALLOWED,
        )


def validate_hex_public_key(value, field_name):
    validate_key_with_desired_parameters(field_name, value, str, GOLEM_PUBLIC_KEY_HEX_LENGTH)


def validate_bytes_public_key(value, field_name):
    validate_key_with_desired_parameters(field_name, value, bytes, GOLEM_PUBLIC_KEY_LENGTH)


def validate_key_with_desired_parameters(
        key_name: str,
        key_value: Union[bytes, str],
        expected_type,
        expected_length: int
):

    if not isinstance(key_value, expected_type):
        raise Http400(
            "{} must be {}.".format(key_name, str(expected_type)),
            error_code=ErrorCode.MESSAGE_VALUE_WRONG_TYPE,
        )

    if len(key_value) != expected_length:
        raise Http400(
            "The length of {} must be exactly {} characters.".format(key_name, expected_length),
            error_code=ErrorCode.MESSAGE_VALUE_WRONG_LENGTH,
        )


def validate_task_to_compute(task_to_compute: message.TaskToCompute):
    if not isinstance(task_to_compute, message.TaskToCompute):
        raise Http400(
            f"Expected TaskToCompute instead of {type(task_to_compute).__name__}.",
            error_code=ErrorCode.MESSAGE_INVALID,
        )

    if any(map(lambda x: x is None, [getattr(task_to_compute, attribute) for attribute in [
        'compute_task_def',
        'provider_public_key',
        'requestor_public_key'
    ]])):
        raise Http400(
            "Invalid TaskToCompute",
            error_code=ErrorCode.MESSAGE_WRONG_FIELDS,
        )
    task_to_compute.compute_task_def['deadline'] = validate_int_value(task_to_compute.compute_task_def['deadline'])

    validate_id_value(task_to_compute.compute_task_def['task_id'], 'task_id')
    validate_id_value(task_to_compute.compute_task_def['subtask_id'], 'subtask_id')

    validate_hex_public_key(task_to_compute.provider_public_key, 'provider_public_key')
    validate_hex_public_key(task_to_compute.requestor_public_key, 'requestor_public_key')
    validate_subtask_price_task_to_compute(task_to_compute)


def validate_report_computed_task_time_window(report_computed_task):
    assert isinstance(report_computed_task, message.ReportComputedTask)

    if report_computed_task.timestamp < report_computed_task.task_to_compute.timestamp:
        raise Http400(
            "ReportComputedTask timestamp is older then nested TaskToCompute.",
            error_code=ErrorCode.MESSAGE_TIMESTAMP_TOO_OLD,
        )


def validate_golem_message_client_authorization(golem_message: message.concents.ClientAuthorization):
    if not isinstance(golem_message, message.concents.ClientAuthorization):
        raise Http400(
            'Expected ClientAuthorization.',
            error_code=ErrorCode.AUTH_CLIENT_AUTH_MESSAGE_MISSING,
        )

    validate_bytes_public_key(golem_message.client_public_key, 'client_public_key')


def validate_all_messages_identical(golem_messages_list: List[message.Message]):
    assert isinstance(golem_messages_list, list)
    assert len(golem_messages_list) >= 1
    assert all(isinstance(golem_message, message.Message) for golem_message in golem_messages_list)
    assert len(set(type(golem_message) for golem_message in golem_messages_list)) == 1

    base_golem_message = golem_messages_list[0]

    for i, golem_message in enumerate(golem_messages_list[1:], start=1):
        for slot in base_golem_message.__slots__:
            if getattr(base_golem_message, slot) != getattr(golem_message, slot):
                raise Http400(
                    '{} messages are not identical. '
                    'There is a difference between messages with index 0 on passed list and with index {}'
                    'The difference is on field {}: {} is not equal {}'.format(
                        type(base_golem_message).__name__,
                        i,
                        slot,
                        getattr(base_golem_message, slot),
                        getattr(golem_message, slot),
                    ),
                    error_code=ErrorCode.MESSAGES_NOT_IDENTICAL,
                )


def validate_golem_message_signed_with_key(
    golem_message: message.base.Message,
    public_key: bytes,
):
    assert isinstance(golem_message, message.base.Message)

    validate_bytes_public_key(public_key, 'public_key')

    try:
        golem_message.verify_signature(public_key)
    except MessageError as exception:
        error_message = join_messages(
            'There was an exception when validating if golem_message {} is signed with public key {}.'.format(
                golem_message.TYPE,
                public_key,
            ),
            str(exception)
        )
        raise Http400(
            error_message,
            error_code=ErrorCode.MESSAGE_SIGNATURE_WRONG,
        )


def validate_golem_message_subtask_results_rejected(subtask_results_rejected: message.tasks.SubtaskResultsRejected):
    if not isinstance(subtask_results_rejected,  message.tasks.SubtaskResultsRejected):
        raise Http400(
            "subtask_results_rejected should be of type:  SubtaskResultsRejected",
            error_code=ErrorCode.MESSAGE_INVALID,
        )
    validate_task_to_compute(subtask_results_rejected.report_computed_task.task_to_compute)


def validate_subtask_price_task_to_compute(task_to_compute: message.tasks.TaskToCompute):
    if not isinstance(task_to_compute.price, int):
        raise Http400(
            "Price must be a integer",
            error_code=ErrorCode.MESSAGE_VALUE_NOT_INTEGER,
        )
    if task_to_compute.price < 0:
        raise Http400(
            "Price cannot be a negative value",
            error_code=ErrorCode.MESSAGE_VALUE_NEGATIVE,
        )


def validate_ethereum_addresses(requestor_ethereum_address, provider_ethereum_address):
    if not isinstance(requestor_ethereum_address, str):
        raise Http400(
            "Requestor's ethereum address must be a string",
            error_code=ErrorCode.MESSAGE_VALUE_NOT_STRING,
        )

    if not isinstance(provider_ethereum_address, str):
        raise Http400(
            "Provider's ethereum address must be a string",
            error_code=ErrorCode.MESSAGE_VALUE_NOT_STRING,
        )

    if not len(requestor_ethereum_address) == ETHEREUM_ADDRESS_LENGTH:
        raise Http400(
            f"Requestor's ethereum address must contains exactly {ETHEREUM_ADDRESS_LENGTH} characters ",
            error_code=ErrorCode.MESSAGE_VALUE_WRONG_LENGTH,
        )

    if not len(provider_ethereum_address) == ETHEREUM_ADDRESS_LENGTH:
        raise Http400(
            f"Provider's ethereum address must contains exactly {ETHEREUM_ADDRESS_LENGTH} characters ",
            error_code=ErrorCode.MESSAGE_VALUE_WRONG_LENGTH,
        )


def validate_list_task_to_compute_ids(subtask_results_accepted_list):
    subtask_ids = []
    for task_to_compute in subtask_results_accepted_list:
        subtask_ids.append(task_to_compute.subtask_id + ':' + task_to_compute.task_id)
    return len(subtask_ids) == len(set(subtask_ids))


def get_validated_client_public_key_from_client_message(golem_message: message.base.Message):
    if isinstance(golem_message, message.concents.ForcePayment):
        if (
            isinstance(golem_message.subtask_results_accepted_list, list) and
            len(golem_message.subtask_results_accepted_list) > 0
        ):
            task_to_compute = golem_message.subtask_results_accepted_list[0].task_to_compute
        else:
            raise Http400(
                "subtask_results_accepted_list must be a list type and contains at least one message",
                error_code=ErrorCode.MESSAGE_VALUE_WRONG_LENGTH,
            )

    elif isinstance(golem_message, message.tasks.TaskMessage):
        task_to_compute = golem_message.task_to_compute
    else:
        raise Http400(
            "Unknown message type",
            error_code=ErrorCode.MESSAGE_UNKNOWN,
        )

    if task_to_compute is not None:
        if isinstance(golem_message, (
            message.ForceReportComputedTask,
            message.concents.ForceSubtaskResults,
            message.concents.ForcePayment,
            message.concents.SubtaskResultsVerify,
        )):
            client_public_key = task_to_compute.provider_public_key
            validate_hex_public_key(client_public_key, 'provider_public_key')
        elif isinstance(golem_message, (
            message.AckReportComputedTask,
            message.RejectReportComputedTask,
            message.concents.ForceGetTaskResult,
            message.concents.ForceSubtaskResultsResponse,
        )):
            client_public_key = task_to_compute.requestor_public_key
            validate_hex_public_key(client_public_key, 'requestor_public_key')
        else:
            raise Http400(
                "Unknown message type",
                error_code=ErrorCode.MESSAGE_UNKNOWN,
            )

        return hex_to_bytes_convert(client_public_key)

    return None


def validate_file_transfer_token(file_transfer_token: message.concents.FileTransferToken):
    """
    Function for check FileTransferToken each field, returns None when message is correct. In case of an error
    returns tuple with custom error message and error code
    """
    # -SIGNATURE
    if not isinstance(file_transfer_token.sig, bytes):
        raise FileTransferTokenError('Empty signature field in FileTransferToken message.', ErrorCode.MESSAGE_SIGNATURE_MISSING)

    # -DEADLINE
    if not isinstance(file_transfer_token.token_expiration_deadline, int):
        raise FileTransferTokenError('Wrong type of token_expiration_deadline field value.', ErrorCode.MESSAGE_TOKEN_EXPIRATION_DEADLINE_WRONG_TYPE)

    # -STORAGE_CLUSTER_ADDRESS
    if not isinstance(file_transfer_token.storage_cluster_address, str):
        raise FileTransferTokenError('Wrong type of storage_cluster_address field value.', ErrorCode.MESSAGE_STORAGE_CLUSTER_WRONG_TYPE)

    url_validator = URLValidator()
    try:
        url_validator(file_transfer_token.storage_cluster_address)
    except ValidationError:
        raise FileTransferTokenError('storage_cluster_address is not a valid URL.', ErrorCode.MESSAGE_STORAGE_CLUSTER_INVALID_URL)

    if file_transfer_token.storage_cluster_address != settings.STORAGE_CLUSTER_ADDRESS:
        raise FileTransferTokenError('This token does not allow file transfers to/from the cluster you are trying to access.', ErrorCode.MESSAGE_STORAGE_CLUSTER_WRONG_CLUSTER)

    # -CLIENT_PUBLIC_KEY
    if not isinstance(file_transfer_token.authorized_client_public_key, bytes):
        raise FileTransferTokenError('Wrong type of authorized_client_public_key field value.', ErrorCode.MESSAGE_AUTHORIZED_CLIENT_PUBLIC_KEY_WRONG_TYPE)

    # -FILES
    if not all(isinstance(file, dict) for file in file_transfer_token.files):
        raise FileTransferTokenError('Wrong type of files field value.', ErrorCode.MESSAGE_FILES_WRONG_TYPE)

    transfer_token_paths_to_files = [file["path"] for file in file_transfer_token.files]
    if len(transfer_token_paths_to_files) != len(set(transfer_token_paths_to_files)):
        raise FileTransferTokenError('File paths in the token must be unique', ErrorCode.MESSAGE_FILES_PATHS_NOT_UNIQUE)

    file_checksums = [file["checksum"] for file in file_transfer_token.files]
    for file_checksum in file_checksums:
        if not isinstance(file_checksum, str):
            raise FileTransferTokenError("'checksum' must be a string.", ErrorCode.MESSAGE_FILES_CHECKSUM_WRONG_TYPE)

        if len(file_checksum) == 0 or file_checksum.isspace():
            raise FileTransferTokenError("'checksum' cannot be blank or contain only whitespace.", ErrorCode.MESSAGE_FILES_CHECKSUM_EMPTY)

        if ":" not in file_checksum:
            raise FileTransferTokenError("'checksum' must consist of two parts separated with a semicolon.", ErrorCode.MESSAGE_FILES_CHECKSUM_WRONG_FORMAT)

        if not file_checksum.split(":")[0] == set(HashingAlgorithm._value2member_map_).pop():  # type: ignore
            raise FileTransferTokenError("One of the checksums is from an unsupported hashing algorithm.", ErrorCode.MESSAGE_FILES_CHECKSUM_INVALID_ALGORITHM)

        assert set(HashingAlgorithm) == {HashingAlgorithm.SHA1}, "If you add a new hashing algorithms, you need to add validations below."
        if VALID_SHA1_HASH_REGEX.fullmatch(file_checksum.split(":")[1]) is None:
            raise FileTransferTokenError("Invalid SHA1 hash.", ErrorCode.MESSAGE_FILES_CHECKSUM_INVALID_SHA1_HASH)

    file_sizes = [file["size"] for file in file_transfer_token.files]
    for file_size in file_sizes:
        if file_size is None:
            raise FileTransferTokenError("'size' must be an integer.", ErrorCode.MESSAGE_FILES_SIZE_EMPTY)

        try:
            int(file_size)
        except (ValueError, TypeError):
            raise FileTransferTokenError("'size' must be an integer.", ErrorCode.MESSAGE_FILES_SIZE_WRONG_TYPE)

        if int(file_size) < 0:
            raise FileTransferTokenError("'size' must not be negative.", ErrorCode.MESSAGE_FILES_SIZE_NEGATIVE)

    # Validate category in FileInfo
    assert all('category' in file for file in file_transfer_token.files)
    assert all(isinstance(file['category'], FileTransferToken.FileInfo.Category) for file in file_transfer_token.files)

    categories = [file_info['category'] for file_info in file_transfer_token.files]
    if len(set(categories)) != len(categories):
        raise FileTransferTokenError("'category' field must be unique across FileInfo list.", ErrorCode.MESSAGE_FILES_CATEGORY_NOT_UNIQUE)
