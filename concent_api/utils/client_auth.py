from functools                      import wraps

from django.http                    import JsonResponse

from golem_messages.exceptions      import FieldError
from golem_messages.exceptions      import MessageError
from golem_messages.exceptions      import MessageFromFutureError
from golem_messages.exceptions      import MessageTooOldError
from golem_messages.exceptions      import TimestampError

from core.validation                import validate_golem_message_signed_with_key
from core.exceptions                import Http400

from utils.shortcuts                import load_without_public_key


def client_auth(message_handler):
    @wraps(message_handler)
    def wrapper(request, *args, **kwargs):
        if request.content_type == '':
            return JsonResponse({'error': 'Content-Type is missing.'}, status = 400)
        elif request.content_type == 'application/octet-stream':
            try:
                message = load_without_public_key(request.body, _check_time = False)
                validate_golem_message_signed_with_key(message, message.client_public_key)
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

        return message_handler(request, message, *args, *kwargs)
    return wrapper
