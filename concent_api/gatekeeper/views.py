import binascii
import datetime
from base64                         import b64decode
from base64                         import b64encode
import logging

from django.conf                    import settings
from django.http                    import JsonResponse
from django.core.validators         import URLValidator
from django.core.exceptions         import ValidationError
from django.urls                    import reverse
from django.views.decorators.csrf   import csrf_exempt
from django.views.decorators.http   import require_POST
from django.views.decorators.http   import require_safe

from gatekeeper.utils               import gatekeeper_access_denied_response

from golem_messages.message         import Message
from golem_messages.shortcuts       import load


logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def upload(request):
    logger.debug("Upload request received.")
    if request.content_type != 'application/x-www-form-urlencoded':
        return gatekeeper_access_denied_response('Unsupported content type.')

    path_to_file = request.get_full_path().partition(reverse('gatekeeper:upload'))[2]
    response = parse_headers(request, path_to_file)
    if response is not None:
        logger.warning(response.content.decode())
        return response
    logger.info('Request passed all upload validations.')

    return JsonResponse({"message": "Request passed all upload validations."}, status = 200)


@csrf_exempt
@require_safe
def download(request):
    logger.debug("Download request received.")
    # The client should not sent Content-Type header with GET requests.
    # FIXME: When running on `manage.py runserver` in development, empty or missing Concent-Type gets replaced
    # with text/plain. gunicorn does not do this. Looks like a bug to me. We'll let it pass for now sice we ignore
    # the body anyway and the check is mostly to inform the client about its mistake.
    if request.content_type != 'text/plain' and request.content_type != '':
        return gatekeeper_access_denied_response('Download request cannot have data in the body.')

    path_to_file = request.get_full_path().partition(reverse('gatekeeper:download'))[2]
    response = parse_headers(request, path_to_file)
    if response is not None:
        logger.warning(response.content.decode())
        return response
    logger.info('Request passed all download validations.')

    return JsonResponse({"message": "Request passed all download validations."}, status = 200)


def parse_headers(request, path_to_file):
    # Decode and check if request header contains a golem message:
    if 'HTTP_AUTHORIZATION' not in request.META:
        return gatekeeper_access_denied_response("Missing 'Authorization' header.")

    authorization_scheme_and_token = request.META['HTTP_AUTHORIZATION'].split(" ", 1)
    assert len(authorization_scheme_and_token) in [1, 2]

    if len(authorization_scheme_and_token) == 1:
        return gatekeeper_access_denied_response("Missing token in the 'Authorization' header.")

    (scheme, token) = authorization_scheme_and_token

    if scheme != 'Golem':
        return gatekeeper_access_denied_response("Unrecognized scheme in the 'Authorization' header.")

    try:
        decoded_auth_header_content = b64decode(token, validate = True)
    except binascii.Error:
        return gatekeeper_access_denied_response("Unable to decode token in the 'Authorization' header.")

    try:
        loaded_golem_message = load(decoded_auth_header_content, settings.CONCENT_PRIVATE_KEY, settings.CONCENT_PUBLIC_KEY, check_time = False)
    # FIXME: We want to catch only exceptions caused by malformed messages but golem-messages does not have specialized
    # exception classes for that. It simply raises AttributeError.
    except AttributeError:
        return gatekeeper_access_denied_response("Token in the 'Authorization' header is not a valid Golem message.")

    if loaded_golem_message is None:
        return gatekeeper_access_denied_response('Undefined golem message.')
    assert isinstance(loaded_golem_message, Message)

    # Check if request header contains Concent-Client-Public-Key:
    if 'HTTP_CONCENT_CLIENT_PUBLIC_KEY' not in request.META:
        return gatekeeper_access_denied_response('Missing Concent-Client-Public-Key header.', path_to_file, loaded_golem_message.subtask_id)
    client_public_key = request.META['HTTP_CONCENT_CLIENT_PUBLIC_KEY']

    logger.debug(
        "Client wants to {} file '{}', with subtask_id '{}'. Client public key: '{}'.".format(
            loaded_golem_message.operation,
            path_to_file,
            loaded_golem_message.subtask_id,
            client_public_key
        )
    )

    # Check ConcentFileTransferToken each field:
    # -DEADLINE
    if not isinstance(loaded_golem_message.token_expiration_deadline, int):
        return gatekeeper_access_denied_response('Wrong type of token_expiration_deadline variable.')
    current_time = int(datetime.datetime.now().timestamp())

    if current_time > loaded_golem_message.token_expiration_deadline:
        return gatekeeper_access_denied_response('token_expiration_deadline has passed.')

    # -STORAGE_CLUSTER_ADDRESS
    if not isinstance(loaded_golem_message.storage_cluster_address, str):
        return gatekeeper_access_denied_response('Wrong type of storage_cluster_address variable.')
    url_validator = URLValidator()
    try:
        url_validator(loaded_golem_message.storage_cluster_address)
    except ValidationError:
        return gatekeeper_access_denied_response('storage_cluster_address is not a valid URL.')
    if loaded_golem_message.storage_cluster_address != settings.STORAGE_CLUSTER_ADDRESS:
        return gatekeeper_access_denied_response('Given storage_cluster_address is not defined in settings.')

    # -CLIENT_PUBLIC_KEY
    if not isinstance(loaded_golem_message.authorized_client_public_key, bytes):
        return gatekeeper_access_denied_response('Wrong type of authorized_client_public_key variable.')
    client_public_key_base64 = (b64encode(loaded_golem_message.authorized_client_public_key)).decode('ascii')
    if request.META['HTTP_CONCENT_CLIENT_PUBLIC_KEY'] != client_public_key_base64:
        return gatekeeper_access_denied_response('authorized_client_public_key is different then Concent-Client-Public-Key header.')

    # -OPERATION
    if request.method == 'POST' and loaded_golem_message.operation != 'upload':
        return gatekeeper_access_denied_response('Wrong operation variable for this request method.')
    if request.method == 'GET' and loaded_golem_message.operation != 'download':
        return gatekeeper_access_denied_response('Wrong operation variable for this request method.')

    # -FILES
    if not all(isinstance(file, dict) for file in loaded_golem_message.files):
        return gatekeeper_access_denied_response('Wrong type of files variable.')
    transfer_token_paths_to_files = []
    for file in loaded_golem_message.files:
        transfer_token_paths_to_files.append(file['path'])
    if path_to_file not in transfer_token_paths_to_files:
        return gatekeeper_access_denied_response('Path to specified file is not listed in files variable.')

    return None
