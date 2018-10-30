from functools import wraps
from logging import getLogger
from typing import Callable
from typing import Union

from django.conf import settings
from django.http import HttpRequest
from django.http import HttpResponse
from django.http import JsonResponse
from golem_messages import dump
from golem_messages import message

from common.logging import log
from core.utils import is_given_golem_messages_version_supported_by_concent

logger = getLogger(__name__)


def validate_protocol_version_in_core(view: Callable) -> Callable:
    @wraps(view)
    def wrapper(
        request: HttpRequest,
        client_message: message.Message,
        client_public_key: bytes,
        *args: list,
        **kwargs: dict,
    ) -> Union[HttpResponse, JsonResponse]:

        if not is_given_golem_messages_version_supported_by_concent(request=request):
            log(
                logger,
                f'Wrong version of golem messages. Clients version is {request.META["HTTP_CONCENT_GOLEM_MESSAGES_VERSION"]}, '
                f'Concent version is {settings.GOLEM_MESSAGES_VERSION}.',
                client_public_key=client_public_key,
            )
            serialized_message = dump(
                message.concents.ServiceRefused(
                    reason=message.concents.ServiceRefused.REASON.InvalidRequest,
                ),
                settings.CONCENT_PRIVATE_KEY,
                client_public_key,
            )
            return HttpResponse(serialized_message, content_type='application/octet-stream')
        return view(request, client_message, client_public_key, *args, *kwargs)
    return wrapper
