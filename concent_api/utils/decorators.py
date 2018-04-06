from functools                      import wraps

from django.db                      import transaction
from django.http                    import JsonResponse
from django.http                    import HttpResponse
from django.http                    import HttpResponseNotAllowed
from django.conf                    import settings

from golem_messages                 import dump
from golem_messages                 import message
from golem_messages.exceptions      import FieldError
from golem_messages.exceptions      import MessageError
from golem_messages.exceptions      import MessageFromFutureError
from golem_messages.exceptions      import MessageTooOldError
from golem_messages.exceptions      import TimestampError

from core.validation                import validate_golem_message_signed_with_key
from core.exceptions                import Http400

from utils.shortcuts                import load_without_public_key

from utils                          import logging


def require_golem_auth_message(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
    """
    Decorator for authenticating golem clients
    Unpacks authorization message signed with the key it contains
    proof that the client indeed has the private part of that key
    """
        if request.content_type == '':
            return JsonResponse({'error': 'Content-Type is missing.'}, status = 400)
        elif request.content_type == 'application/octet-stream':
            try:
                auth_message = load_without_public_key(request.body)
                if isinstance(auth_message, message.concents.ClientAuthorization):
                    validate_golem_message_signed_with_key(auth_message, auth_message.client_public_key)
                else:
                    return JsonResponse({'error': 'Client Authentication message not included'})
            except Http400 as exception:
                return JsonResponse({'error': f'{exception}'}, status = 400)
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

        return view(request, auth_message, *args, *kwargs)
    return wrapper


def handle_errors_and_responses(view):
    @wraps(view)
    def wrapper(request, client_message, *args, **kwargs):
        """
        Decorator for handling responses from Concent
        for golem clients
        """
        try:
            sid = transaction.savepoint()
            response_from_view = view(request, client_message, *args, **kwargs)
            transaction.savepoint_commit(sid)
        except Http400 as exception:
            logging.log_400_error(
                view.__name__,
                client_message,
                client_message.client_public_key,
            )
            transaction.savepoint_rollback(sid)
            return JsonResponse({'error': str(exception)}, status = 400)
        if isinstance(response_from_view, message.Message):
            assert response_from_view.sig is None
            logging.log_message_returned(
                response_from_view,
                client_message.client_public_key,
            )
            serialized_message = dump(
                response_from_view,
                settings.CONCENT_PRIVATE_KEY,
                client_message.client_public_key,
            )

            return HttpResponse(serialized_message, content_type = 'application/octet-stream')
        elif isinstance(response_from_view, dict):
            return JsonResponse(response_from_view, safe = False)
        elif isinstance(response_from_view, HttpResponseNotAllowed):
            logging.log_message_not_allowed(
                view.__name__,
                request.method,
                client_message.client_public_key,
            )
            return response_from_view
        elif isinstance(response_from_view, HttpResponse):
            logging.log_message_accepted(
                client_message,
                client_message.client_public_key,
            )
            return response_from_view
        elif response_from_view is None:
            logging.log_empty_queue(
                view.__name__,
                client_message.client_public_key,
            )
            return HttpResponse("", status = 204)
        elif isinstance(response_from_view, bytes):
            return HttpResponse(response_from_view)

        assert False, "Invalid response type"
        raise Exception("Invalid response type")

    return wrapper
