from logging import getLogger
from typing import Union

from django.conf import settings
from django.db import transaction
from django.http import HttpRequest
from django.http import HttpResponse
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.views.decorators.http import require_GET
from golem_messages.message import Message

from core.message_handlers import handle_message
from core.message_handlers import handle_messages_from_database
from core.subtask_helpers import update_all_timed_out_subtasks_of_a_client
from core.subtask_helpers import check_protocol_versions_and_update_subtasks_from_incoming_message_if_timed_out
from common import logging
from common.decorators import handle_errors_and_responses
from common.decorators import log_communication
from common.decorators import provides_concent_feature
from common.decorators import require_golem_auth_message
from common.decorators import require_golem_message
from common.decorators import validate_protocol_version_in_core

logger = getLogger(__name__)


@provides_concent_feature('concent-api')
@csrf_exempt
@require_POST
@require_golem_message
@validate_protocol_version_in_core
@handle_errors_and_responses(database_name='control')
@log_communication
@transaction.non_atomic_requests(using='control')
def send(_request: HttpRequest, client_message: Message, client_public_key: bytes) -> Union[Message, HttpResponse]:
    assert isinstance(client_public_key, bytes) or client_public_key is None
    if client_public_key is not None:
        check_protocol_versions_and_update_subtasks_from_incoming_message_if_timed_out(client_message, client_public_key)
    logging.log_message_received(
        logger,
        client_message,
        client_public_key,
    )

    return handle_message(client_message)


@provides_concent_feature('concent-api')
@csrf_exempt
@require_POST
@require_golem_auth_message
@validate_protocol_version_in_core
@handle_errors_and_responses(database_name='control')
@transaction.non_atomic_requests(using='control')
def receive(_request: HttpRequest, _message: Message, _client_public_key: bytes) -> Union[Message, HttpResponse]:
    assert isinstance(_message.client_public_key, bytes)
    update_all_timed_out_subtasks_of_a_client(
        client_public_key=_message.client_public_key,
    )
    return handle_messages_from_database(client_public_key=_message.client_public_key)


@require_GET
def protocol_constants(_request: HttpRequest) -> JsonResponse:
    """ Endpoint which returns Concent time settings. """
    return JsonResponse(
        data = {
            'concent_messaging_time': settings.CONCENT_MESSAGING_TIME,
            'force_acceptance_time': settings.FORCE_ACCEPTANCE_TIME,
            'minimum_upload_rate': settings.MINIMUM_UPLOAD_RATE,
            'download_leadin_time': settings.DOWNLOAD_LEADIN_TIME,
            'payment_due_time': settings.PAYMENT_DUE_TIME,
        }
    )
