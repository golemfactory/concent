import binascii
from functools                      import wraps
from base64                         import b64decode

from django.http                    import JsonResponse
from django.http                    import HttpResponse
from django.conf                    import settings
from django.views.decorators.csrf   import csrf_exempt

from golem_messages.exceptions      import FieldError
from golem_messages.exceptions      import InvalidSignature
from golem_messages.exceptions      import MessageError
from golem_messages.exceptions      import MessageFromFutureError
from golem_messages.exceptions      import MessageTooOldError
from golem_messages.exceptions      import TimestampError
from golem_messages.message         import Message
from golem_messages                 import dump
from golem_messages                 import load

from utils                          import logging


class Http400(Exception):
    pass


def api_view(view):
    @wraps(view)
    @csrf_exempt
    def wrapper(request, *args, **kwargs):
        if 'HTTP_CONCENT_CLIENT_PUBLIC_KEY' not in request.META or request.META['HTTP_CONCENT_CLIENT_PUBLIC_KEY'] == '':
            return JsonResponse({'error': 'Concent-Client-Public-Key HTTP header is missing on the request.'}, status = 400)
        try:
            client_public_key = b64decode(request.META['HTTP_CONCENT_CLIENT_PUBLIC_KEY'].encode('ascii'), validate=True)
        except binascii.Error:
            return JsonResponse({'error': 'The value in the Concent-Client-Public-Key HTTP is not a valid base64-encoded value.'}, status = 400)

        if len(client_public_key) != 64:
            return JsonResponse(
                {'error': 'The length in the Concent-Client-Public-Key HTTP is wrong.'},
                status = 400
            )

        if request.content_type not in ['application/octet-stream', '']:
            return JsonResponse({'error': 'Concent supports only application/octet-stream.'}, status = 415)

        if len(request.body) == 0:
            message = None
        else:
            if request.content_type == '':
                return JsonResponse({'error': 'Content-Type is missing.'}, status = 400)
            elif request.content_type == 'application/octet-stream':
                try:
                    message = load(
                        request.body,
                        settings.CONCENT_PRIVATE_KEY,
                        client_public_key,
                    )
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
        try:
            response_from_view = view(request, message, *args, **kwargs)
        except Http400 as exception:
            logging.log_400_error(
                view.__name__,
                message,
                request.META['HTTP_CONCENT_CLIENT_PUBLIC_KEY'],
            )
            return JsonResponse({'error': str(exception)}, status = 400)
        if isinstance(response_from_view, Message):
            logging.log_message_returned(
                response_from_view,
                request.META['HTTP_CONCENT_CLIENT_PUBLIC_KEY'],
            )
            serialized_message = dump(
                response_from_view,
                settings.CONCENT_PRIVATE_KEY,
                client_public_key,
            )

            return HttpResponse(serialized_message, content_type = 'application/octet-stream')
        elif isinstance(response_from_view, dict):
            return JsonResponse(response_from_view, safe = False)
        elif isinstance(response_from_view, HttpResponse):
            logging.log_message_accepted(
                message,
                request.META['HTTP_CONCENT_CLIENT_PUBLIC_KEY'],
            )
            return response_from_view
        elif response_from_view is None:
            logging.log_empty_queue(
                view.__name__,
                request.META['HTTP_CONCENT_CLIENT_PUBLIC_KEY'],
            )
            return HttpResponse("", status = 204)
        elif isinstance(response_from_view, bytes):
            return HttpResponse(response_from_view)

        assert False, "Invalid response type"
        raise Exception("Invalid response type")

    return wrapper
