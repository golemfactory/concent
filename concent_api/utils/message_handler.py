from functools                      import wraps

from django.db                      import transaction
from django.http                    import JsonResponse
from django.http                    import HttpResponse
from django.http                    import HttpResponseNotAllowed
from django.conf                    import settings

from golem_messages                 import dump
from golem_messages.message         import Message

from core.exceptions                import Http400

from utils                          import logging


def message_handler(view):
    @wraps(view)
    def wrapper(request, message, *args, **kwargs):
        try:
            sid = transaction.savepoint()
            response_from_view = view(request, message, *args, **kwargs)
            transaction.savepoint_commit(sid)
        except Http400 as exception:
            logging.log_400_error(
                view.__name__,
                message,
                message.client_public_key,
            )
            transaction.savepoint_rollback(sid)
            return JsonResponse({'error': str(exception)}, status = 400)
        if isinstance(response_from_view, Message):
            assert response_from_view.sig is None
            logging.log_message_returned(
                response_from_view,
                message.client_public_key,
            )
            serialized_message = dump(
                response_from_view,
                settings.CONCENT_PRIVATE_KEY,
                message.client_public_key,
            )

            return HttpResponse(serialized_message, content_type = 'application/octet-stream')
        elif isinstance(response_from_view, dict):
            return JsonResponse(response_from_view, safe = False)
        elif isinstance(response_from_view, HttpResponseNotAllowed):
            logging.log_message_not_allowed(
                view.__name__,
                request.method,
                message.client_public_key,
            )
            return response_from_view
        elif isinstance(response_from_view, HttpResponse):
            logging.log_message_accepted(
                message,
                message.client_public_key,
            )
            return response_from_view
        elif response_from_view is None:
            logging.log_empty_queue(
                view.__name__,
                message.client_public_key,
            )
            return HttpResponse("", status = 204)
        elif isinstance(response_from_view, bytes):
            return HttpResponse(response_from_view)

        assert False, "Invalid response type"
        raise Exception("Invalid response type")

    return wrapper
