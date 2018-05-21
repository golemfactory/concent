import binascii
from base64                         import b64decode
from base64                         import b64encode
import re
from typing                         import Union

from django.conf                    import settings
from django.http                    import JsonResponse
from django.core.handlers.wsgi      import WSGIRequest
from django.core.validators         import URLValidator
from django.core.exceptions         import ValidationError
from django.urls                    import reverse
from django.views.decorators.csrf   import csrf_exempt
from django.views.decorators.http   import require_POST
from django.views.decorators.http   import require_safe

from golem_messages.exceptions      import MessageError
from golem_messages.message         import FileTransferToken
from golem_messages.message         import Message
from golem_messages.shortcuts       import load

from gatekeeper.enums               import HashingAlgorithm
from gatekeeper.utils               import gatekeeper_access_denied_response
from utils                          import logging
from utils.constants                import ErrorCode
from utils.helpers                  import get_current_utc_timestamp


VALID_SHA1_HASH_REGEX = re.compile(r"^[a-fA-F\d]{40}$")


@csrf_exempt
@require_POST
def upload(request):
    logging.log_request_received(
        request.META['PATH_INFO'] if 'PATH_INFO' in request.META.keys() else '-path to file UNAVAILABLE-',
        FileTransferToken.Operation.upload
    )

    if request.content_type in ['multipart/form-data', '', None] or request.content_type.isspace():
        return gatekeeper_access_denied_response(
            'Unsupported content type.',
            FileTransferToken.Operation.upload,
            ErrorCode.HEADER_CONTENT_TYPE_NOT_SUPPORTED,
            request.META['PATH_INFO'] if 'PATH_INFO' in request.META.keys() else 'UNAVAILABLE'
        )

    path_to_file = request.get_full_path().partition(reverse('gatekeeper:upload'))[2]
    response_or_file_info = parse_headers(request, path_to_file, FileTransferToken.Operation.upload)

    if not isinstance(response_or_file_info, FileTransferToken.FileInfo):
        assert isinstance(response_or_file_info, JsonResponse)
        return response_or_file_info

    response                           = JsonResponse({"message": "Request passed all upload validations."}, status = 200)
    response["Concent-File-Size"]      = response_or_file_info["size"]
    response["Concent-File-Checksum"]  = response_or_file_info["checksum"]

    return response


@csrf_exempt
@require_safe
def download(request):
    logging.log_request_received(
        request.META['PATH_INFO'] if 'PATH_INFO' in request.META.keys() else '-path to file UNAVAILABLE-',
        FileTransferToken.Operation.download
    )
    # The client should not sent Content-Type header with GET requests.
    # FIXME: When running on `manage.py runserver` in development, empty or missing Concent-Type gets replaced
    # with text/plain. gunicorn does not do this. Looks like a bug to me. We'll let it pass for now sice we ignore
    # the body anyway and the check is mostly to inform the client about its mistake.
    if request.content_type != 'text/plain' and request.content_type != '':
        return gatekeeper_access_denied_response(
            'Download request cannot have data in the body.',
            FileTransferToken.Operation.download,
            ErrorCode.REQUEST_BODY_NOT_EMPTY,
        )

    path_to_file = request.get_full_path().partition(reverse('gatekeeper:download'))[2]
    response_or_file_info = parse_headers(request, path_to_file, FileTransferToken.Operation.download)
    if not isinstance(response_or_file_info, FileTransferToken.FileInfo):
        assert isinstance(response_or_file_info, JsonResponse)
        return response_or_file_info
    return JsonResponse({"message": "Request passed all download validations."}, status = 200)


def parse_headers(request: WSGIRequest, path_to_file: str, operation: FileTransferToken.Operation) -> Union[FileTransferToken.FileInfo, JsonResponse]:
    # Decode and check if request header contains a golem message:
    if 'HTTP_AUTHORIZATION' not in request.META:
        return gatekeeper_access_denied_response(
            "Missing 'Authorization' header.",
            operation,
            ErrorCode.HEADER_AUTHORIZATION_MISSING,
            path_to_file,
        )

    authorization_scheme_and_token = request.META['HTTP_AUTHORIZATION'].split(" ", 1)
    assert len(authorization_scheme_and_token) in [1, 2]

    if len(authorization_scheme_and_token) == 1:
        return gatekeeper_access_denied_response(
            "Missing token in the 'Authorization' header.",
            operation,
            ErrorCode.HEADER_AUTHORIZATION_MISSING_TOKEN,
            path_to_file,
        )

    (scheme, token) = authorization_scheme_and_token

    if scheme != 'Golem':
        return gatekeeper_access_denied_response(
            "Unrecognized scheme in the 'Authorization' header.",
            operation,
            ErrorCode.HEADER_AUTHORIZATION_UNRECOGNIZED_SCHEME,
            path_to_file,
        )

    try:
        decoded_auth_header_content = b64decode(token, validate = True)
    except binascii.Error:
        return gatekeeper_access_denied_response(
            "Unable to decode token in the 'Authorization' header.",
            operation,
            ErrorCode.HEADER_AUTHORIZATION_NOT_BASE64_ENCODED_VALUE,
            path_to_file,
        )

    try:
        loaded_golem_message = load(decoded_auth_header_content, settings.CONCENT_PRIVATE_KEY, settings.CONCENT_PUBLIC_KEY, check_time = False)
    except MessageError:
        return gatekeeper_access_denied_response(
            "Token in the 'Authorization' header is not a valid Golem message.",
            operation,
            ErrorCode.HEADER_AUTHORIZATION_TOKEN_INVALID_MESSAGE,
            path_to_file,
        )

    assert isinstance(loaded_golem_message, Message)

    # Check if request header contains Concent-Auth:
    if 'HTTP_CONCENT_AUTH' not in request.META:
        return gatekeeper_access_denied_response(
            'Missing Concent-Auth header.',
            operation,
            ErrorCode.AUTH_CLIENT_AUTH_MESSAGE_MISSING,
            path_to_file,
            loaded_golem_message.subtask_id
        )

    # Try to load in ClientAuthorization message from Concent-Auth header
    try:
        client_authorization = load(
            b64decode(request.META['HTTP_CONCENT_AUTH'], validate=True),
            settings.CONCENT_PRIVATE_KEY,
            loaded_golem_message.authorized_client_public_key,
        )
        concent_client_public_key = b64encode(client_authorization.client_public_key).decode('ascii')
    except (MessageError, binascii.Error):
        return gatekeeper_access_denied_response(
            'Cannot load ClientAuthorization message from Concent-Auth header.',
            operation,
            ErrorCode.AUTH_CLIENT_AUTH_MESSAGE_INVALID,
            path_to_file,
            loaded_golem_message.subtask_id
        )

    logging.log_message_under_validation(
            loaded_golem_message.operation,
            loaded_golem_message.__class__.__name__,
            path_to_file,
            loaded_golem_message.subtask_id,
            concent_client_public_key
    )

    # Check ConcentFileTransferToken each field:
    # -SIGNATURE
    if not isinstance(loaded_golem_message.sig, bytes):
        return gatekeeper_access_denied_response(
            'Empty signature field in FileTransferToken message.',
            operation,
            ErrorCode.MESSAGE_SIGNATURE_MISSING,
            path_to_file,
            loaded_golem_message.subtask_id,
            concent_client_public_key
        )
    # -DEADLINE
    if not isinstance(loaded_golem_message.token_expiration_deadline, int):
        return gatekeeper_access_denied_response(
            'Wrong type of token_expiration_deadline field value.',
            operation,
            ErrorCode.MESSAGE_TOKEN_EXPIRATION_DEADLINE_WRONG_TYPE,
            path_to_file,
            loaded_golem_message.subtask_id,
            concent_client_public_key
        )
    current_time = get_current_utc_timestamp()

    if current_time > loaded_golem_message.token_expiration_deadline:
        return gatekeeper_access_denied_response(
            'token_expiration_deadline has passed.',
            operation,
            ErrorCode.MESSAGE_TOKEN_EXPIRATION_DEADLINE_PASSED,
            path_to_file,
            loaded_golem_message.subtask_id,
            concent_client_public_key
        )

    # -STORAGE_CLUSTER_ADDRESS
    if not isinstance(loaded_golem_message.storage_cluster_address, str):
        return gatekeeper_access_denied_response(
            'Wrong type of storage_cluster_address field value.',
            operation,
            ErrorCode.MESSAGE_STORAGE_CLUSTER_WRONG_TYPE,
            path_to_file,
            loaded_golem_message.subtask_id,
            concent_client_public_key
        )
    url_validator = URLValidator()
    try:
        url_validator(loaded_golem_message.storage_cluster_address)
    except ValidationError:
        return gatekeeper_access_denied_response(
            'storage_cluster_address is not a valid URL.',
            operation,
            ErrorCode.MESSAGE_STORAGE_CLUSTER_INVALID_URL,
            path_to_file,
            loaded_golem_message.subtask_id,
            concent_client_public_key
        )
    if loaded_golem_message.storage_cluster_address != settings.STORAGE_CLUSTER_ADDRESS:
        return gatekeeper_access_denied_response(
            'This token does not allow file transfers to/from the cluster you are trying to access.',
            operation,
            ErrorCode.MESSAGE_STORAGE_CLUSTER_WRONG_CLUSTER,
            path_to_file,
            loaded_golem_message.subtask_id,
            concent_client_public_key
        )

    # -CLIENT_PUBLIC_KEY
    if not isinstance(loaded_golem_message.authorized_client_public_key, bytes):
        return gatekeeper_access_denied_response(
            'Wrong type of authorized_client_public_key field value.',
            operation,
            ErrorCode.MESSAGE_AUTHORIZED_CLIENT_PUBLIC_KEY_WRONG_TYPE,
            path_to_file,
            loaded_golem_message.subtask_id,
            concent_client_public_key
        )
    authorized_client_public_key_base64 = (b64encode(loaded_golem_message.authorized_client_public_key)).decode('ascii')
    if concent_client_public_key != authorized_client_public_key_base64:
        return gatekeeper_access_denied_response(
            'You are not authorized to use this token.',
            operation,
            ErrorCode.MESSAGE_AUTHORIZED_CLIENT_PUBLIC_KEY_UNAUTHORIZED_CLIENT,
            path_to_file,
            loaded_golem_message.subtask_id,
            concent_client_public_key
        )

    # -OPERATION
    if request.method == 'POST' and loaded_golem_message.operation != FileTransferToken.Operation.upload:
        return gatekeeper_access_denied_response(
            'Upload requests must use POST method.',
            operation,
            ErrorCode.MESSAGE_OPERATION_INVALID,
            path_to_file,
            loaded_golem_message.subtask_id,
            concent_client_public_key
        )
    if request.method in ['GET', 'HEAD'] and loaded_golem_message.operation != FileTransferToken.Operation.download:
        return gatekeeper_access_denied_response(
            'Download requests must use GET or HEAD method.',
            operation,
            ErrorCode.MESSAGE_OPERATION_INVALID,
            path_to_file,
            loaded_golem_message.subtask_id,
            concent_client_public_key
        )

    # -FILES
    if not all(isinstance(file, dict) for file in loaded_golem_message.files):
        return gatekeeper_access_denied_response(
            'Wrong type of files field value.',
            operation,
            ErrorCode.MESSAGE_FILES_WRONG_TYPE,
            path_to_file,
            loaded_golem_message.subtask_id,
            concent_client_public_key
        )
    transfer_token_paths_to_files = [file["path"] for file in loaded_golem_message.files]
    if len(transfer_token_paths_to_files) != len(set(transfer_token_paths_to_files)):
        return gatekeeper_access_denied_response(
            'File paths in the token must be unique',
            operation,
            ErrorCode.MESSAGE_FILES_PATHS_NOT_UNIQUE,
            path_to_file,
            loaded_golem_message.subtask_id,
            concent_client_public_key
        )

    if not all(isinstance(file["checksum"], str) for file in loaded_golem_message.files):
        return gatekeeper_access_denied_response(
            "'checksum' must be a string.",
            operation,
            ErrorCode.MESSAGE_FILES_CHECKSUM_WRONG_TYPE,
            path_to_file,
            loaded_golem_message.subtask_id,
            concent_client_public_key
        )
    if any((len(file["checksum"]) == 0 or file["checksum"].isspace()) for file in loaded_golem_message.files):
        return gatekeeper_access_denied_response(
            "'checksum' cannot be blank or contain only whitespace.",
            operation,
            ErrorCode.MESSAGE_FILES_CHECKSUM_EMPTY,
            path_to_file,
            loaded_golem_message.subtask_id,
            concent_client_public_key
        )
    if not all(":" in file["checksum"] for file in loaded_golem_message.files):
        return gatekeeper_access_denied_response(
            "'checksum' must consist of two parts separated with a semicolon.",
            operation,
            ErrorCode.MESSAGE_FILES_CHECKSUM_WRONG_FORMAT,
            path_to_file,
            loaded_golem_message.subtask_id,
            concent_client_public_key
        )
    file_checksums = [tuple(file["checksum"].split(":")) for file in loaded_golem_message.files]
    if not set(checksum_type for checksum_type, checksum in file_checksums).issubset(set(HashingAlgorithm._value2member_map_)):  # type: ignore
        return gatekeeper_access_denied_response(
            "One of the checksums is from an unsupported hashing algorithm.",
            operation,
            ErrorCode.MESSAGE_FILES_CHECKSUM_INVALID_ALGORITHM,
            path_to_file,
            loaded_golem_message.subtask_id,
            concent_client_public_key
        )

    assert set(HashingAlgorithm) == {HashingAlgorithm.SHA1}, "If you add a new hashing algorithms, you need to add validations below."
    if any(VALID_SHA1_HASH_REGEX.fullmatch(file_checksum[1]) is None for file_checksum in file_checksums):
        return gatekeeper_access_denied_response(
            "Invalid SHA1 hash.",
            operation,
            ErrorCode.MESSAGE_FILES_CHECKSUM_INVALID_SHA1_HASH,
            path_to_file,
            loaded_golem_message.subtask_id,
            concent_client_public_key
        )

    file_sizes = [file["size"] for file in loaded_golem_message.files]
    if any((file_size is None) for file_size in file_sizes):
        return gatekeeper_access_denied_response(
            "'size' must be an integer.",
            operation,
            ErrorCode.MESSAGE_FILES_SIZE_EMPTY,
            path_to_file,
            loaded_golem_message.subtask_id,
            concent_client_public_key
        )
    for file_size in file_sizes:
        try:
            int(file_size)
        except (ValueError, TypeError):
            return gatekeeper_access_denied_response(
                "'size' must be an integer.",
                operation,
                ErrorCode.MESSAGE_FILES_SIZE_WRONG_TYPE,
                path_to_file,
                loaded_golem_message.subtask_id,
                concent_client_public_key
            )

    if any(int(file["size"]) < 0 for file in loaded_golem_message.files):
        return gatekeeper_access_denied_response(
            "'size' must not be negative.",
            operation,
            ErrorCode.MESSAGE_FILES_SIZE_NEGATIVE,
            path_to_file,
            loaded_golem_message.subtask_id,
            concent_client_public_key
        )

    matching_files = [file for file in loaded_golem_message.files if path_to_file == file['path']]

    if len(matching_files) == 1:
        logging.log_message_successfully_validated(
            loaded_golem_message.operation,
            loaded_golem_message.__class__.__name__,
            path_to_file,
            loaded_golem_message.subtask_id,
            concent_client_public_key
        )
        return matching_files[0]
    else:
        assert len(matching_files) == 0
        return gatekeeper_access_denied_response(
            'Your token does not authorize you to transfer the requested file.',
            operation,
            ErrorCode.MESSAGE_FILES_PATH_NOT_LISTED_IN_FILES,
            path_to_file,
            loaded_golem_message.subtask_id,
            concent_client_public_key
        )
