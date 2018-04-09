from functools                      import wraps

from django.db                      import transaction
from django.http                    import JsonResponse
from django.http                    import HttpResponse
from django.http                    import HttpResponseNotAllowed
from django.conf                    import settings
from django.views.decorators.csrf   import csrf_exempt

from golem_messages                 import dump
from golem_messages.exceptions      import FieldError
from golem_messages.exceptions      import InvalidSignature
from golem_messages.exceptions      import MessageError
from golem_messages.exceptions      import MessageFromFutureError
from golem_messages.exceptions      import MessageTooOldError
from golem_messages.exceptions      import TimestampError
from golem_messages.message         import Message

from core.exceptions                import Http400
from utils                          import logging
from utils.helpers                  import get_validated_client_public_key_from_client_message
from utils.shortcuts                import load_without_public_key


def api_view(view):
    @wraps(view)
    @csrf_exempt
    def wrapper(request, *args, **kwargs):
        if request.content_type not in ['application/octet-stream', '']:
            return JsonResponse({'error': 'Concent supports only application/octet-stream.'}, status = 415)

        if len(request.body) == 0:
            message = None
        else:
            if request.content_type == '':
                return JsonResponse({'error': 'Content-Type is missing.'}, status = 400)
            elif request.content_type == 'application/octet-stream':
                try:
                    message = load_without_public_key(request.body)
                    assert message is not None
                except InvalidSignature as exception:
                    return JsonResponse({'error': "Failed to decode a Golem Message. {}".format(exception)}, status = 400)
                except FieldError:
                    return JsonResponse({'error': "Golem Message contains wrong fields."}, status = 400)
                except MessageFromFutureError:
                    return JsonResponse({'error': 'Message timestamp too far in the future.'}, status = 400)
                except MessageTooOldError:
                    return JsonResponse({'error': 'Message is too old.'}, status = 400)
                except TimestampError as exception:
                    return JsonResponse({'error': '{}'.format(exception)}, status = 400)
                except MessageError as exception:
                    return JsonResponse({'error': "Error in Golem Message. {}".format(exception)}, status = 400)
            else:
                return JsonResponse({'error': "Concent supports only application/octet-stream."}, status = 400)
        client_public_key = None
        try:
            sid = transaction.savepoint()
            client_public_key = get_validated_client_public_key_from_client_message(message)
            response_from_view = view(request, message, client_public_key, *args, **kwargs)
            transaction.savepoint_commit(sid)
        except Http400 as exception:
            logging.log_400_error(
                view.__name__,
                message,
                client_public_key if client_public_key is not None else 'UNAVAILABLE',
            )
            transaction.savepoint_rollback(sid)
            return JsonResponse({'error': str(exception)}, status = 400)
        if isinstance(response_from_view, Message):
            assert response_from_view.sig is None
            logging.log_message_returned(
                response_from_view,
                client_public_key,
            )
            serialized_message = dump(
                response_from_view,
                settings.CONCENT_PRIVATE_KEY,
                client_public_key,
            )

            return HttpResponse(serialized_message, content_type = 'application/octet-stream')
        elif isinstance(response_from_view, dict):
            return JsonResponse(response_from_view, safe = False)
        elif isinstance(response_from_view, HttpResponseNotAllowed):
            logging.log_message_not_allowed(
                view.__name__,
                request.method,
                client_public_key,
            )
            return response_from_view
        elif isinstance(response_from_view, HttpResponse):
            logging.log_message_accepted(
                message,
                client_public_key,
            )
            return response_from_view
        elif response_from_view is None:
            logging.log_empty_queue(
                view.__name__,
                client_public_key,
            )
            return HttpResponse("", status = 204)
        elif isinstance(response_from_view, bytes):
            return HttpResponse(response_from_view)

        assert False, "Invalid response type"
        raise Exception("Invalid response type")

    return wrapper
