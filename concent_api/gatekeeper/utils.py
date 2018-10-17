from logging import getLogger

from django.http import JsonResponse
from golem_messages.message.concents import FileTransferToken

from common import logging
from common.constants import ErrorCode

logger = getLogger(__name__)


def gatekeeper_access_denied_response(
    message: str,
    operation: FileTransferToken.Operation,
    error_code: ErrorCode,
    path: str=None,
    subtask_id: str=None,
    client_key: str=None
) -> JsonResponse:
    data = {
        'message': message,
        'error_code': error_code.value,
        'path_to_file': path,
        'subtask_id': subtask_id,
        'client_key': client_key,
    }
    logging.log_string_message(
        logger,
        f"{operation.capitalize()} validation failed. Message: {message} Error code: '{error_code.value}'. File '{path}'",
        subtask_id=subtask_id,
        client_public_key=client_key
    )

    # The status code here must be always 401 because auth_request module in nginx can only handle HTTP 401.
    response = JsonResponse(data, status=401)
    response["WWW-Authenticate"] = 'Golem realm="Concent Storage"'
    return response
