from functools import wraps
from logging import getLogger
from typing import Any
from typing import Callable
from typing import Union
import traceback

from django.db import transaction
from django.http import JsonResponse
from django.http import HttpRequest
from django.http import HttpResponse
from django.http import HttpResponseNotAllowed
from django.conf import settings

from golem_messages                 import dump
from golem_messages                 import message
from golem_messages.exceptions      import FieldError
from golem_messages.exceptions      import MessageError
from golem_messages.exceptions      import MessageFromFutureError
from golem_messages.exceptions      import MessageTooOldError
from golem_messages.exceptions      import TimestampError

from common.constants import ErrorCode
from common.constants import ERROR_IN_GOLEM_MESSAGE
from common.exceptions import ConcentBaseException
from common.exceptions import ConcentFeatureIsNotAvailable
from common.exceptions import ConcentInSoftShutdownMode
from common.exceptions import ConcentValidationError
from common.helpers import join_messages
from common import logging
from common.logging import get_json_from_message_without_redundant_fields_for_logging
from common.logging import LoggingLevel
from common.logging import log_400_error
from common.logging import log_string_message
from common.shortcuts import load_without_public_key
from core.exceptions import NonPositivePriceTaskToComputeError
from core.exceptions import CreateModelIntegrityError
from core.validation import get_validated_client_public_key_from_client_message
from core.validation import is_golem_message_signed_with_key


logger = getLogger(__name__)
crash_logger = getLogger('concent.crash')


def require_golem_auth_message(view: Callable) -> Callable:
    """
    Decorator for authenticating golem clients
    Unpacks authorization message signed with the key it contains
    proof that the client indeed has the private part of that key
    """
    @wraps(view)
    def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> Union[HttpResponse, JsonResponse]:
        if request.content_type == '':
            log_string_message(logger, 'error: Content-Type is missing')
            return JsonResponse({'error': 'Content-Type is missing.'}, status = 400)
        elif request.content_type == 'application/octet-stream':
            try:
                auth_message = load_without_public_key(request.body)
                if isinstance(auth_message, message.concents.ClientAuthorization):
                    if is_golem_message_signed_with_key(
                        auth_message.client_public_key,
                        auth_message,
                    ):
                        log_string_message(
                            logger,
                            f'A message has been received in `{request.resolver_match.view_name if request.resolver_match is not None else "-not available"}`.'
                            f'Message type: {auth_message.__class__.__name__}.',
                            client_public_key=auth_message.client_public_key
                        )
                    else:
                        log_string_message(
                            logger,
                            f'ClientAuthorization message is not signed with public key {auth_message.client_public_key}.',
                            client_public_key=auth_message.client_public_key
                        )
                        return JsonResponse(
                            {
                                'error': f'ClientAuthorization message is not signed with public key {auth_message.client_public_key}.',
                                'error_code': ErrorCode.MESSAGE_SIGNATURE_WRONG.value,
                            },
                            status=400
                        )
                else:
                    log_string_message(logger, 'error: Client Authentication message not included')
                    return JsonResponse({'error': 'Client Authentication message not included'}, status = 400)
            except FieldError as exception:
                log_string_message(logger, 'Golem Message contains wrong fields.', exception.__class__.__name__)
                return JsonResponse({'error': join_messages('Golem Message contains wrong fields.', str(exception))}, status = 400)
            except MessageFromFutureError as exception:
                log_string_message(logger, 'Message timestamp too far in the future.', exception.__class__.__name__)
                return JsonResponse({'error': join_messages('Message timestamp too far in the future.', str(exception))}, status = 400)
            except MessageTooOldError as exception:
                log_string_message(logger, 'Message is too old.', exception.__class__.__name__)
                return JsonResponse({'error': join_messages('Message is too old.', str(exception))}, status = 400)
            except TimestampError as exception:
                log_string_message(logger, 'Error:', exception.__class__.__name__)
                return JsonResponse({'error': f'{exception}'}, status = 400)
            except MessageError as exception:
                log_string_message(logger, ERROR_IN_GOLEM_MESSAGE, exception.__class__.__name__)
                return JsonResponse({'error': join_messages(ERROR_IN_GOLEM_MESSAGE, str(exception))}, status = 400)
        else:
            log_string_message(logger, 'error: Concent supports only application/octet-stream.')
            return JsonResponse({'error': "Concent supports only application/octet-stream."}, status = 415)

        return view(request, auth_message, auth_message.client_public_key, *args, *kwargs)
    return wrapper


def require_golem_message(view: Callable) -> Callable:
    """
    Decorator for view accepting golem messages
    Unpacks golem message signed with the key it contains
    proof that the client indeed has the private part of that key
    """
    @wraps(view)
    def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> Union[HttpResponse, JsonResponse]:
        if request.content_type == '':
            log_string_message(logger, 'error: Content-Type is missing')
            return JsonResponse({'error': 'Content-Type is missing.'}, status = 400)
        elif request.content_type == 'application/octet-stream':
            try:
                golem_message = load_without_public_key(request.body)
                assert golem_message is not None
                client_public_key = get_validated_client_public_key_from_client_message(golem_message)
                log_string_message(
                    logger,
                    f'A message has been received in `{request.resolver_match.view_name if request.resolver_match is not None else "-not available"}`.'
                    f'Message type: {golem_message.__class__.__name__}.',
                    f'Content type: {request.META["CONTENT_TYPE"] if "CONTENT_TYPE" in request.META.keys() else "-not available"}'
                    f'TASK_ID: {golem_message.task_id if "task_id" in dir(golem_message) else "-not available"}',
                    subtask_id=golem_message.subtask_id if 'subtask_id' in dir(golem_message) else None,
                    client_public_key=client_public_key
                )
            except ConcentValidationError as exception:
                log_string_message(logger, f"error_code: {exception.error_code.value} error: {exception.error_message} ")
                return JsonResponse(
                    {
                        'error': f'{exception.error_message}',
                        'error_code': exception.error_code.value,
                    },
                    status=400
                )
            except NonPositivePriceTaskToComputeError as exception:
                log_string_message(logger, 'TaskToCompute contains non-positive price.', exception.__class__.__name__)
                return message.concents.ServiceRefused(
                    reason=message.concents.ServiceRefused.REASON.InvalidRequest
                )
            except FieldError as exception:
                log_string_message(logger, 'Golem Message contains wrong fields.', exception.__class__.__name__)
                return JsonResponse({'error': join_messages('Golem Message contains wrong fields.', str(exception))}, status = 400)
            except MessageFromFutureError as exception:
                log_string_message(logger, 'Message timestamp too far in the future.', exception.__class__.__name__)
                return JsonResponse({'error': join_messages('Message timestamp too far in the future.', str(exception))}, status = 400)
            except MessageTooOldError as exception:
                log_string_message(logger, 'Message is too old.', exception.__class__.__name__)
                return JsonResponse({'error': join_messages('Message is too old.', str(exception))}, status = 400)
            except TimestampError as exception:
                log_string_message(logger, 'Error:', exception.__class__.__name__)
                return JsonResponse({'error': f'{exception}'}, status = 400)
            except MessageError as exception:
                log_string_message(logger, ERROR_IN_GOLEM_MESSAGE, exception.__class__.__name__)
                return JsonResponse({'error': join_messages(ERROR_IN_GOLEM_MESSAGE, str(exception))}, status = 400)
        else:
            log_string_message(logger, 'error: Concent supports only application/octet-stream.')
            return JsonResponse({'error': "Concent supports only application/octet-stream."}, status = 415)

        return view(request, golem_message, client_public_key, *args, *kwargs)
    return wrapper


def handle_errors_and_responses(database_name: str) -> Callable:
    """
    Decorator for handling responses from Concent
    for golem clients and handling transactions on given database name if it is not None.
    """
    def decorator(view: Callable) -> Callable:
        @wraps(view)
        def wrapper(
            request: HttpRequest,
            client_message: message.Message,
            client_public_key: bytes,
            *args: list,
            **kwargs: dict,
        ) -> Union[HttpRequest, JsonResponse]:
            assert database_name in settings.DATABASES or database_name is None
            try:
                if database_name is not None:
                    sid = transaction.savepoint(using=database_name)
                response_from_view = view(request, client_message, client_public_key, *args, **kwargs)
                if database_name is not None:
                    transaction.savepoint_commit(sid, using=database_name)

            except CreateModelIntegrityError as exception:
                log_string_message(
                    logger,
                    f'CreateModelIntegrityError occurred. View will be retried. Exception: {exception}.',
                    client_public_key=client_public_key,
                )
                response_from_view = view(request, client_message, client_public_key, *args, **kwargs)
            except ConcentBaseException as exception:
                log_400_error(
                    logger,
                    view.__name__,
                    client_public_key,
                    client_message,
                    exception.error_code,
                    exception.error_message
                )
                if database_name is not None:
                    transaction.savepoint_rollback(sid, using=database_name)
                return JsonResponse(
                    {
                        'error': exception.error_message,
                        'error_code': exception.error_code.value,
                    },
                    status=400
                )
            except ConcentInSoftShutdownMode:
                transaction.savepoint_rollback(sid, using=database_name)

                json_response = JsonResponse({'error': 'Concent is in soft shutdown mode.'}, status=503)
                log_string_message(logger, str(json_response))
                return json_response

            if isinstance(response_from_view, message.Message):
                assert response_from_view.sig is None
                logging.log_message_returned(
                    logger,
                    response_from_view,
                    client_public_key,
                    request.resolver_match._func_path if request.resolver_match is not None else None,
                )
                serialized_message = dump(
                    response_from_view,
                    settings.CONCENT_PRIVATE_KEY,
                    client_public_key,
                )
                return HttpResponse(serialized_message, content_type = 'application/octet-stream')
            elif isinstance(response_from_view, dict):

                json_response = JsonResponse(response_from_view, safe = False)
                log_string_message(logger, str(json_response))
                return json_response
            elif isinstance(response_from_view, HttpResponseNotAllowed):
                log_string_message(
                    logger,
                    f"Endpoint {view.__name__} does not allow HTTP method {request.method}",
                    client_public_key=client_public_key
                )
                return response_from_view
            elif isinstance(response_from_view, HttpResponse):
                logging.log_message_accepted(
                    logger,
                    client_message,
                    client_public_key,
                )
                return response_from_view
            elif response_from_view is None:

                log_string_message(
                    logger,
                    f"A message queue is empty in `{view.__name__}",
                    client_public_key=client_public_key
                )
                return HttpResponse("", status = 204)
            elif isinstance(response_from_view, bytes):
                logging.log_string_message(
                    logger,
                    'Response from core.views - Response is bytes instance'
                )
                return HttpResponse(response_from_view)

            logging.log_string_message(
                logger,
                'Invalid response from core.views type',
                client_public_key=client_public_key
            )
            assert False, "Invalid response type"
            raise Exception("Invalid response type")

        return wrapper
    return decorator


def provides_concent_feature(concent_feature: str) -> Callable:
    """
    Decorator for declaring that given `concent_feature` is required to be in setting CONCENT_FEATURES
    for decorated view or celery task function.
    """
    def decorator(_function: Callable) -> Callable:
        assert callable(_function)

        @wraps(_function)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if concent_feature not in settings.CONCENT_FEATURES:
                raise ConcentFeatureIsNotAvailable(
                    f'Concent feature `{concent_feature}` is not enabled. Function `{_function.__name__}` cannot be called in this configuration.'
                )
            return _function(*args, **kwargs)
        return wrapper
    return decorator


def log_communication(view: Callable) -> Callable:

    @wraps(view)
    def wrapper(request: HttpRequest, golem_message: message.Message, client_public_key: bytes) -> HttpResponse:
        json_message_to_log = get_json_from_message_without_redundant_fields_for_logging(golem_message)
        log_string_message(logger, str(json_message_to_log))
        response_from_view = view(request,  golem_message, client_public_key)
        return response_from_view
    return wrapper


def log_task_errors(task: Callable) -> Callable:

    @wraps(task)
    def wrapper(*args: Any, **kwargs: Any) -> None:
        try:
            return task(*args, **kwargs)
        except Exception as exception:
            log_string_message(
                crash_logger,
                f'Exception occurred while executing task {task.__name__}: {exception}, Traceback: {traceback.format_exc()}',
                subtask_id=kwargs['subtask_id'] if 'subtask_id' in kwargs else None,
                logging_level=LoggingLevel.ERROR)
            raise
    return wrapper
