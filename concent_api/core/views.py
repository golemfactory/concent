from django.conf                    import settings
from django.http                    import JsonResponse
from django.views.decorators.csrf   import csrf_exempt
from django.views.decorators.http   import require_POST
from django.views.decorators.http   import require_GET

from core.message_handlers          import handle_message
from core.message_handlers          import handle_messages_from_database
from core.subtask_helpers           import update_timed_out_subtasks

from utils                          import logging
from utils.api_view                 import api_view
from utils.decorators               import require_golem_auth_message
from utils.decorators               import handle_errors_and_responses
from .models                        import PendingResponse


@api_view
@require_POST
def send(request, client_message, client_public_key):
    if client_public_key is not None:
        update_timed_out_subtasks(
            client_public_key = client_public_key,
        )

    if client_message is not None:
        logging.log_message_received(
            client_message,
            client_public_key if client_public_key is not None else 'UNAVAILABLE',
        )

    return handle_message(client_message, request)


@csrf_exempt
@require_golem_auth_message
@handle_errors_and_responses
@require_POST
def receive(_request, message):
    update_timed_out_subtasks(
        client_public_key = message.client_public_key,
    )
    return handle_messages_from_database(
        client_public_key  = message.client_public_key,
        response_type      = PendingResponse.Queue.Receive,
    )


@csrf_exempt
@require_golem_auth_message
@handle_errors_and_responses
@require_POST
def receive_out_of_band(_request, message):
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
            'concent_messaging_time':    settings.CONCENT_MESSAGING_TIME,
            'force_acceptance_time':     settings.FORCE_ACCEPTANCE_TIME,
            'maximum_download_time':     settings.MAXIMUM_DOWNLOAD_TIME,
            'subtask_verification_time': settings.SUBTASK_VERIFICATION_TIME,
            'payment_due_time':          settings.PAYMENT_DUE_TIME,
        }
    )
