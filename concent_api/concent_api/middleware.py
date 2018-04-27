import os
import traceback

from django.conf    import settings
from django.db import transaction
from django.http import JsonResponse

from golem_messages import __version__
from concent_api.constants import DEFAULT_ERROR_MESSAGE
from utils.constants import ErrorCode


class GolemMessagesVersionMiddleware(object):
    """
    Used to attach version of the golem_messages package currently used to HTTP response header.

    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response['Concent-Golem-Messages-Version'] = __version__
        return response


class ConcentVersionMiddleware(object):
    """
    Used to attach version of the Concent currently used to HTTP response header.

    """

    _concent_version = None

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if self._concent_version is None:
            with open(os.path.join(settings.BASE_DIR, '..', 'RELEASE-VERSION')) as f:
                self._concent_version = f.read()

        response = self.get_response(request)
        response['Concent-Version'] = self._concent_version
        return response


class HandleServerErrorMiddleware(object):
    """
    Used to catch all unhandled exceptions and return JSON response containing error information.
    """
    def __init__(self, get_response):
        self.get_response = get_response
        self.sid = None

    def __call__(self, request):
        self.sid = transaction.savepoint()
        response = self.get_response(request)
        transaction.savepoint_commit(self.sid)
        return response

    def process_exception(self, request, exception):  # pylint: disable=unused-argument
        transaction.savepoint_rollback(self.sid)
        return self._build_json_response(exception)

    @staticmethod
    def _build_json_response(exception):
        message = {
            "error_message": str(exception) or DEFAULT_ERROR_MESSAGE,
            "error_code": getattr(exception, "error_code", ErrorCode.CONCENT_APPLICATION_CRASH.value),
        }
        debug_info = getattr(settings, 'DEBUG_INFO_IN_ERROR_RESPONSES', settings.DEBUG)
        if debug_info:
            message["stack_trace"] = traceback.format_exc()
        return JsonResponse(message, status=500)
