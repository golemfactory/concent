import binascii
from base64                         import b64decode

from django.conf                    import settings
from django.http                    import HttpResponse
from django.views.decorators.csrf   import csrf_exempt
from django.views.decorators.http   import require_POST
from django.views.decorators.http   import require_safe

from gatekeeper.utils               import gatekeeper_access_denied_response

from golem_messages.message         import Message
from golem_messages.shortcuts       import load


@csrf_exempt
@require_POST
def upload(request):
    if request.content_type != 'application/x-www-form-urlencoded':
        return gatekeeper_access_denied_response('Unsupported content type.')

    response = parse_headers(request)
    if response is not None:
        return response

    return HttpResponse("", status = 200)


@csrf_exempt
@require_safe
def download(request):
    # The client should not sent Content-Type header with GET requests.
    # FIXME: When running on `manage.py runserver` in development, empty or missing Concent-Type gets replaced
    # with text/plain. gunicorn does not do this. Looks like a bug to me. We'll let it pass for now sice we ignore
    # the body anyway and the check is mostly to inform the client about its mistake.
    if request.content_type != 'text/plain' and request.content_type != '':
        return gatekeeper_access_denied_response('Download request cannot have data in the body.')

    response = parse_headers(request)
    if response is not None:
        return response

    return HttpResponse("", status = 200)


def parse_headers(request):
    # Decode and check if request header contains a golem message:
    if 'HTTP_AUTHORIZATION' not in request.META:
        return gatekeeper_access_denied_response("Missing 'Authorization' header.")

    authorization_scheme_and_token = request.META['HTTP_AUTHORIZATION'].split(" ", 1)
    assert len(authorization_scheme_and_token) in [1, 2]

    if len(authorization_scheme_and_token) == 1:
        return gatekeeper_access_denied_response("Missing token in the 'Authorization' header.")

    (scheme, token) = authorization_scheme_and_token

    if scheme != 'Golem':
        return gatekeeper_access_denied_response("Unrecognized scheme in the 'Authorization' header.")

    try:
        decoded_auth_header_content = b64decode(token, validate = True)
    except binascii.Error:
        return gatekeeper_access_denied_response("Unable to decode token in the 'Authorization' header.")

    try:
        loaded_golem_message = load(decoded_auth_header_content, settings.CONCENT_PRIVATE_KEY, settings.CONCENT_PUBLIC_KEY)
    # FIXME: We want to catch only exceptions caused by malformed messages but golem-messages does not have specialized
    # exception classes for that. It simply raises AttributeError.
    except AttributeError:
        return gatekeeper_access_denied_response("Token in the 'Authorization' header is not a valid Golem message.")

    if loaded_golem_message is None:
        return gatekeeper_access_denied_response('Undefined golem message.')
    assert isinstance(loaded_golem_message, Message)

    return None
