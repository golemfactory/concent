from functools import wraps
from typing import Callable

from django.conf import settings
from django.http import HttpRequest
from django.http import JsonResponse
from golem_messages.message.concents import FileTransferToken

from common.constants import ErrorCode
from common.decorators import logger
from common.logging import log
from core.utils import is_given_golem_messages_version_supported_by_concent
from gatekeeper.utils import gatekeeper_access_denied_response


def validate_protocol_version_in_gatekeeper(view: Callable) -> Callable:
    @wraps(view)
    def wrapper(
        request: HttpRequest,
        *args: list,
        **kwargs: dict,
    ) -> JsonResponse:

        if not is_given_golem_messages_version_supported_by_concent(request=request):
            log(
                logger,
                f'Wrong version of golem messages. Clients version is {request.META["HTTP_X_Golem_Messages"]}, '
                f'Concent version is {settings.GOLEM_MESSAGES_VERSION}.',
            )
            return gatekeeper_access_denied_response(
                "Protocol version in request does not match protocol version in Concent",
                FileTransferToken.Operation.download,
                ErrorCode.HEADER_PROTOCOL_VERSION_UNSUPPORTED,
                request.META['PATH_INFO'] if 'PATH_INFO' in request.META.keys() else '-path to file UNAVAILABLE-',
            )
        return view(request, *args, *kwargs)
    return wrapper
