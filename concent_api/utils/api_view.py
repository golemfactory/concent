import binascii
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

        if 'HTTP_ADDITIONAL_CLIENT_PUBLIC_KEY' in request.META:
            try:
                b64decode(request.META['HTTP_ADDITIONAL_CLIENT_PUBLIC_KEY'].encode('ascii'))
            except ValueError:
                return JsonResponse({'error': 'The value in the Additional-Client-Public-Key HTTP is not a valid base64-encoded value.'}, status = 400)

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
                try:
                    message = load(
                        request.body,
                        settings.CONCENT_PRIVATE_KEY,
                        client_public_key,
                        check_time = False,
                    )
                except AttributeError:
                    # TODO: Make error handling more granular when golem-messages adds starts raising more specific exceptions
                    return JsonResponse(
                        {'error': "Failed to decode ForceReportComputedTask. Message and/or key are malformed or don't match."},
                        status = 400
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
