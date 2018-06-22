import logging
import os
import sys
import traceback

from django.conf    import settings
from django.db import transaction
from django.http import HttpResponse
from django.http import JsonResponse
from django.views.debug import technical_500_response
from django.views.defaults import server_error
from mimeparse import best_match

from golem_messages import __version__
from concent_api.constants import DEFAULT_ERROR_MESSAGE
from common.constants import ErrorCode


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


def determine_return_type(request_meta):
    try:
        # The list of preferred mime-types should be sorted in order of increasing desirability,
        # in case of a situation where there is a tie.
        preferred_types = ['text/html', 'application/json']
        if "HTTP_ACCEPT" in request_meta:
            return best_match(preferred_types, request_meta['HTTP_ACCEPT'])
        return "application/json"
    except Exception:  # pylint: disable=broad-except
        # This is a bit of a hack - as there is no specific exception that `best_match` function raises in case of
        # invalid/broken accept header, we just catch every possible exception that comes from it and treat such
        # a situation as a broken header
        return ""


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
        request_logger = logging.getLogger('django.request')
        request_logger.error(
            'Internal Server Error: %s', request.path,
            exc_info=sys.exc_info(),
            extra={'status_code': 500, 'request': request},
        )
        debug_info_enabled = getattr(settings, 'DEBUG_INFO_IN_ERROR_RESPONSES', settings.DEBUG)
        return_type = determine_return_type(request.META)
        if return_type == "application/json":
            return self._build_json_response(exception, debug_info_enabled)
        elif return_type == "text/html":
            return self._build_html_response(request, debug_info_enabled)
        else:
            return HttpResponse(status=406)

    @staticmethod
    def _build_html_response(request, debug_info_enabled):
        if debug_info_enabled:
            return technical_500_response(request, *sys.exc_info())
        return server_error(request)

    @staticmethod
    def _build_json_response(exception, debug_info_enabled):
        message = {
            "error_message": str(exception) or DEFAULT_ERROR_MESSAGE,
            "error_code": getattr(exception, "error_code", ErrorCode.CONCENT_APPLICATION_CRASH).value,
        }
        if debug_info_enabled:
            message["stack_trace"] = traceback.format_exc()
        return JsonResponse(message, status=500)
