from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator

from golem_messages import message
from golem_messages.message import FileTransferToken

from common.constants import ErrorCode
from core.constants import VALID_SHA1_HASH_REGEX
from core.enums import HashingAlgorithm
from core.exceptions import FileTransferTokenError
from core.exceptions import HashingAlgorithmError


def validate_file_transfer_token(file_transfer_token: message.concents.FileTransferToken):
    """
    Function for check FileTransferToken each field, returns None when message is correct. In case of an error
    raise tuple with custom error message and error code
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
        try:
            validate_secure_hash_algorithm(file_checksum)
        except HashingAlgorithmError as exception:
            raise FileTransferTokenError(exception.error_message, exception.error_code)

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


def validate_secure_hash_algorithm(checksum: str):
    if not isinstance(checksum, str):
        raise HashingAlgorithmError(
            "'checksum' must be a string.",
            ErrorCode.MESSAGE_FILES_CHECKSUM_WRONG_TYPE
        )

    if len(checksum) == 0 or checksum.isspace():
        raise HashingAlgorithmError(
            "'checksum' cannot be blank or contain only whitespace.",
            ErrorCode.MESSAGE_FILES_CHECKSUM_EMPTY
        )

    if ":" not in checksum:
        raise HashingAlgorithmError(
            "checksum must be in format of: '<ALGORITHM>:<HASH>'.",
            ErrorCode.MESSAGE_FILES_CHECKSUM_WRONG_FORMAT
        )

    if not checksum.split(":")[0] in HashingAlgorithm.values():
        raise HashingAlgorithmError(
            f"Checksum {checksum} comes from an unsupported hashing algorithm.",
            ErrorCode.MESSAGE_FILES_CHECKSUM_INVALID_ALGORITHM
        )

    assert set(HashingAlgorithm) == {HashingAlgorithm.SHA1}, "If you add a new hashing algorithms, you need to add validations below."
    if VALID_SHA1_HASH_REGEX.fullmatch(checksum.split(":")[1]) is None:
        raise HashingAlgorithmError(
            "Invalid SHA1 hash.",
            ErrorCode.MESSAGE_FILES_CHECKSUM_INVALID_SHA1_HASH
        )
