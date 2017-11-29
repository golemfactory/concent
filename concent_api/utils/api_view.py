from functools                      import wraps
from base64                         import b64decode

import json
from django.http                    import JsonResponse
from django.http                    import HttpResponse
from django.conf                    import settings
from django.views.decorators.csrf   import csrf_exempt
from golem_messages.message         import Message
from golem_messages                 import dump
from golem_messages                 import load


class Http400(Exception):
    pass


def api_view(view):
    @wraps(view)
    @csrf_exempt
    def wrapper(request, *args, **kwargs):
        if 'HTTP_CONCENT_CLIENT_PUBLIC_KEY' not in request.META:
            return JsonResponse({'error': 'Concent-Client-Public-Key HTTP header is missing on the request.'}, status = 400)

        try:
            client_public_key = b64decode(request.META['HTTP_CONCENT_CLIENT_PUBLIC_KEY'].encode('ascii'))
        except TypeError:
            # From b64decode() docs:
            # A TypeError is raised if s is incorrectly padded.
            # Characters that are neither in the normal base-64 alphabet nor the alternative alphabet are discarded prior to the padding check.
            return JsonResponse({'error': 'The value in the Concent-Client-Public-Key HTTP is not a valid base64-encoded value.'}, status = 400)

        if request.content_type not in ['application/octet-stream', '', 'application/json']:
            return JsonResponse({'error': 'Concent supports only application/octet-stream and application/json.'}, status = 415)

        if len(request.body) == 0:
            message = None
        else:
            if request.content_type == '':
                raise Http400('Content-Type is missing.')
            if request.content_type == 'application/json':
                message = json.loads(request.body.decode('ascii'))
            if request.content_type == 'application/octet-stream':
                message = load(
                    request.body,
                    settings.CONCENT_PRIVATE_KEY,
                    client_public_key
                )

        try:
            response_from_view = view(request, message, *args, **kwargs)
        except Http400 as exception:
            return JsonResponse({'error': str(exception)}, status = 400)

        if isinstance(response_from_view, Message):
            serialized_message = dump(
                response_from_view,
                settings.CONCENT_PRIVATE_KEY,
                client_public_key
            )
            return HttpResponse(serialized_message, content_type = 'application/octet-stream')
        elif isinstance(response_from_view, dict):
            return JsonResponse(response_from_view, safe = False)
        elif isinstance(response_from_view, HttpResponse):
            return response_from_view
        elif response_from_view is None:
            return HttpResponse("", status = 204)
        elif isinstance(response_from_view, bytes):
            return HttpResponse(response_from_view)

        assert False, "Invalid response type"

    return wrapper
