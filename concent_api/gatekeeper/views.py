import binascii
from base64                         import b64decode
from base64                         import b64encode
from logging import getLogger
from typing                         import Union

from django.conf import settings
from django.http import JsonResponse
from django.http import HttpRequest
from django.core.handlers.wsgi import WSGIRequest
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.views.decorators.http import require_safe

from golem_messages.exceptions      import MessageError
from golem_messages.message.concents import FileTransferToken
from golem_messages.message         import Message
from golem_messages.shortcuts       import load

from core.exceptions import FileTransferTokenError
from gatekeeper.utils               import gatekeeper_access_denied_response
from common                          import logging
from common.constants                import ErrorCode
from common.decorators import provides_concent_feature
from common.helpers import get_current_utc_timestamp
from common.validations import validate_file_transfer_token


logger = getLogger(__name__)


@provides_concent_feature('gatekeeper')
@csrf_exempt
@require_POST
def upload(request: HttpRequest) -> JsonResponse:
    logging.log_request_received(
        logger,
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

    response = JsonResponse({"message": "Request passed all upload validations."}, status = 200)
    response["Concent-File-Size"] = response_or_file_info["size"]
    response["Concent-File-Checksum"] = response_or_file_info["checksum"]

    return response


@provides_concent_feature('gatekeeper')
@csrf_exempt
@require_safe
def download(request: HttpRequest) -> JsonResponse:
    logging.log_request_received(
        logger,
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


def parse_headers(
    request: WSGIRequest,
    path_to_file: str,
    operation: FileTransferToken.Operation,
) -> Union[FileTransferToken.FileInfo, JsonResponse]:
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
        loaded_golem_message = load(
            decoded_auth_header_content,
            settings.CONCENT_PRIVATE_KEY,
            settings.CONCENT_PUBLIC_KEY,
            check_time = False
        )
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
    logging.log_string_message(
        logger,
        f"{loaded_golem_message.operation.capitalize()} request will be validated. "
        f"Message type: '{loaded_golem_message.__class__.__name__}'. File: '{path_to_file}'",
        subtask_id=loaded_golem_message.subtask_id,
        client_public_key=concent_client_public_key,
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

    try:
        validate_file_transfer_token(loaded_golem_message)
    except FileTransferTokenError as exception:
        return gatekeeper_access_denied_response(
            exception.error_message,
            operation,
            exception.error_code,
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

    matching_files = [file for file in loaded_golem_message.files if path_to_file == file['path']]

    if len(matching_files) == 1:
        logging.log_string_message(
            logger,
            f"{loaded_golem_message.operation.capitalize()} request passed all validations. "
            f"Message type: '{loaded_golem_message.__class__.__name__}'. File: '{path_to_file}'",
            subtask_id=loaded_golem_message.subtask_id,
            client_public_key=concent_client_public_key
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
