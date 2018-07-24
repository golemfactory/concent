from logging import getLogger
from django.conf                    import settings
from django.http                    import JsonResponse
from django.views.decorators.csrf   import csrf_exempt
from django.views.decorators.http   import require_POST
from django.views.decorators.http   import require_GET

from core.message_handlers          import handle_message
from core.message_handlers          import handle_messages_from_database
from core.subtask_helpers           import update_timed_out_subtasks
from common                          import logging
from common.decorators import handle_errors_and_responses
from common.decorators import log_communication
from common.decorators import provides_concent_feature
from common.decorators               import require_golem_auth_message
from common.decorators               import require_golem_message
from .models                        import PendingResponse

logger = getLogger(__name__)


@provides_concent_feature('concent-api')
@csrf_exempt
@require_POST
@require_golem_message
@handle_errors_and_responses(database_name='control')
@log_communication
def send(_request, client_message, client_public_key):
    assert isinstance(client_public_key, bytes) or client_public_key is None
    if client_public_key is not None:
        update_timed_out_subtasks(
            client_public_key = client_public_key,
        )

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
@handle_errors_and_responses(database_name='control')
def receive(_request, message, _client_public_key):
    assert isinstance(message.client_public_key, bytes)
    update_timed_out_subtasks(
        client_public_key = message.client_public_key,
    )
    return handle_messages_from_database(
        client_public_key  = message.client_public_key,
        response_type      = PendingResponse.Queue.Receive,
    )


@provides_concent_feature('concent-api')
@csrf_exempt
@require_POST
@require_golem_auth_message
@handle_errors_and_responses(database_name='control')
def receive_out_of_band(_request, message, _client_public_key):
    assert isinstance(message.client_public_key, bytes)
    update_timed_out_subtasks(
        client_public_key = message.client_public_key,
    )
    return handle_messages_from_database(
        client_public_key  = message.client_public_key,
        response_type      = PendingResponse.Queue.ReceiveOutOfBand,
    )


@require_GET
def protocol_constants(_request):
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
