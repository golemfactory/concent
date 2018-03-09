from base64                         import b64encode
from decimal                        import Decimal
import binascii
import copy
import datetime

import requests
from django.conf                    import settings
from django.http                    import HttpResponse
from django.http                    import JsonResponse
from django.db.models               import Q
from django.utils                   import timezone
from django.views.decorators.http   import require_POST
from django.views.decorators.http   import require_GET

from golem_messages                 import message
from golem_messages                 import shortcuts
from golem_messages.datastructures  import MessageHeader
from golem_messages.exceptions      import MessageError

from core                           import exceptions
from core.payments                  import base
from gatekeeper.constants           import CLUSTER_DOWNLOAD_PATH
from utils                          import logging
from utils.api_view                 import api_view
from utils.api_view                 import Http400
from utils.helpers                  import decode_key
from utils.helpers                  import get_current_utc_timestamp
from utils.helpers                  import parse_timestamp_to_utc_datetime
from .constants                     import MESSAGE_TASK_ID_MAX_LENGTH
from .models                        import Client
from .models                        import MessageAuth
from .models                        import PendingResponse
from .models                        import PaymentInfo
from .models                        import ReceiveOutOfBandStatus
from .models                        import ReceiveStatus
from .models                        import StoredMessage
from .models                        import Subtask


@api_view
@require_POST
def send(request, client_message):
    logging.log_message_received(
        client_message,
        request.META['HTTP_CONCENT_CLIENT_PUBLIC_KEY'],
    )

    client_public_key = decode_client_public_key(request)
    update_timed_out_subtasks(
        client_public_key = client_public_key,
    )

    if isinstance(client_message, message.ForceReportComputedTask):
        return handle_send_force_report_computed_task(request, client_message)

    elif isinstance(client_message, message.AckReportComputedTask):
        return handle_send_ack_report_computed_task(request, client_message)

    elif isinstance(client_message, message.RejectReportComputedTask):
        return handle_send_reject_report_computed_task(request, client_message)

    elif isinstance(client_message, message.concents.ForceGetTaskResult) and client_message.report_computed_task is not None:
        return handle_send_force_get_task_result(request, client_message)

    elif isinstance(client_message, message.concents.ForceSubtaskResults) and client_message.ack_report_computed_task is not None:
        return handle_send_force_subtask_results(request, client_message)

    elif (
        isinstance(client_message, message.concents.ForceSubtaskResultsResponse) and
        (client_message.subtask_results_accepted is not None or client_message.subtask_results_rejected is not None)
    ):
        return handle_send_force_subtask_results_response(request, client_message)

    elif isinstance(client_message, message.concents.ForcePayment):
        return handle_send_force_payment(request, client_message)

    else:
        return handle_unsupported_golem_messages_type(client_message)


@api_view
@require_POST
def receive(request, _message):
    client_public_key = decode_client_public_key(request)
    update_timed_out_subtasks(
        client_public_key = client_public_key,
    )
    return handle_messages_from_database(
        client_public_key  = client_public_key,
        response_type      = PendingResponse.Queue.Receive,
    )


@api_view
@require_POST
def receive_out_of_band(request, _message):
    client_public_key = decode_client_public_key(request)
    update_timed_out_subtasks(
        client_public_key = client_public_key,
    )
    return handle_messages_from_database(
        client_public_key  = client_public_key,
        response_type      = PendingResponse.Queue.ReceiveOutOfBand,
    )


@require_GET
def protocol_constants(_request):
    """ Endpoint which returns Concent time settings. """
    return JsonResponse(
        data = {
            'concent_messaging_time':    settings.CONCENT_MESSAGING_TIME,
            'force_acceptance_time':     settings.FORCE_ACCEPTANCE_TIME,
            'subtask_verification_time': settings.SUBTASK_VERIFICATION_TIME,
            'token_expiration_time':     settings.TOKEN_EXPIRATION_TIME,
        }
    )


def handle_send_force_report_computed_task(request, client_message):
    current_time           = get_current_utc_timestamp()
    client_public_key      = decode_client_public_key(request)
    other_party_public_key = decode_other_party_public_key(request)
    validate_golem_message_task_to_compute(client_message.report_computed_task.task_to_compute)

    if StoredMessage.objects.filter(task_id = client_message.report_computed_task.task_to_compute.compute_task_def['task_id']).exists():
        raise Http400("{} is already being processed for this task.".format(client_message.__class__.__name__))

    if Subtask.objects.filter(
        subtask_id = client_message.report_computed_task.task_to_compute.compute_task_def['subtask_id'],
    ).exists():
        raise Http400("{} is already being processed for this task.".format(client_message.__class__.__name__))

    if client_message.report_computed_task.task_to_compute.compute_task_def['deadline'] < current_time:
        logging.log_timeout(
            client_message,
            request.META['HTTP_CONCENT_CLIENT_PUBLIC_KEY'],
            client_message.report_computed_task.task_to_compute.compute_task_def['deadline'],
        )
        reject_force_report_computed_task                 = message.RejectReportComputedTask(
            header = MessageHeader(
                type_     = message.RejectReportComputedTask.TYPE,
                timestamp = client_message.timestamp,
                encrypted = False,
            )
        )
        reject_force_report_computed_task.reason          = message.RejectReportComputedTask.REASON.TaskTimeLimitExceeded
        reject_force_report_computed_task.task_to_compute = client_message.report_computed_task.task_to_compute
        return message.concents.ForceReportComputedTaskResponse(
            reject_report_computed_task = reject_force_report_computed_task
        )
    store_message_and_message_status(
        client_message.TYPE,
        client_message.report_computed_task.task_to_compute.compute_task_def['task_id'],
        client_message,
        provider_public_key  = client_public_key,
        requestor_public_key = other_party_public_key,
        status               = ReceiveStatus
    )
    subtask = store_subtask(
        task_id              = client_message.report_computed_task.task_to_compute.compute_task_def['task_id'],
        subtask_id           = client_message.report_computed_task.task_to_compute.compute_task_def['subtask_id'],
        provider_public_key  = client_public_key,
        requestor_public_key = other_party_public_key,
        state                = Subtask.SubtaskState.FORCING_REPORT,
        next_deadline        = client_message.report_computed_task.task_to_compute.compute_task_def['deadline'] + settings.CONCENT_MESSAGING_TIME,
        task_to_compute      = client_message.report_computed_task.task_to_compute,
        report_computed_task = client_message.report_computed_task,
    )
    store_pending_message(
        response_type       = PendingResponse.ResponseType.ForceReportComputedTask,
        client_public_key   = other_party_public_key,
        queue               = PendingResponse.Queue.Receive,
        subtask             = subtask,
    )
    logging.log_message_added_to_queue(
        client_message,
        client_public_key,
    )
    return HttpResponse("", status = 202)


def handle_send_ack_report_computed_task(request, client_message):
    current_time      = get_current_utc_timestamp()
    client_public_key = decode_client_public_key(request)
    validate_golem_message_task_to_compute(client_message.task_to_compute)

    if current_time <= client_message.task_to_compute.compute_task_def['deadline'] + settings.CONCENT_MESSAGING_TIME:
        try:
            subtask = Subtask.objects.get(
                subtask_id = client_message.task_to_compute.compute_task_def['subtask_id'],
            )
        except Subtask.DoesNotExist:
            raise Http400("'ForceReportComputedTask' for this subtask_id has not been initiated yet. Can't accept your 'AckReportComputedTask'.")

        if subtask.state_enum != Subtask.SubtaskState.FORCING_REPORT:
            raise Http400("Subtask state is {} instead of FORCING_REPORT. Can't accept your 'AckReportComputedTask'.".format(
                subtask.state
            ))

        if subtask.report_computed_task.subtask_id != client_message.task_to_compute.compute_task_def['subtask_id']:
            raise Http400("Received subtask_id does not match one in related ReportComputedTask. Can't accept your 'AckReportComputedTask'.")

        if subtask.requestor.public_key != request.META['HTTP_CONCENT_CLIENT_PUBLIC_KEY']:
            raise Http400("Subtask requestor key does not match current client key. Can't accept your 'AckReportComputedTask'.")

        if subtask.ack_report_computed_task_id is not None or subtask.reject_report_computed_task_id is not None:
            raise Http400(
                "Received AckReportComputedTask but RejectReportComputedTask "
                "or another AckReportComputedTask for this task has already been submitted."
            )

        force_task_to_compute   = StoredMessage.objects.filter(
            task_id                    = client_message.task_to_compute.compute_task_def['task_id'],
            type                       = message.ForceReportComputedTask.TYPE,
            auth__requestor_public_key = request.META['HTTP_CONCENT_CLIENT_PUBLIC_KEY']
        )
        previous_ack_message    = StoredMessage.objects.filter(
            task_id                    = client_message.task_to_compute.compute_task_def['task_id'],
            type                       = message.AckReportComputedTask.TYPE,
            auth__requestor_public_key = request.META['HTTP_CONCENT_CLIENT_PUBLIC_KEY']
        )
        reject_message          = StoredMessage.objects.filter(
            task_id                    = client_message.task_to_compute.compute_task_def['task_id'],
            type                       = message.RejectReportComputedTask.TYPE,
            auth__requestor_public_key = request.META['HTTP_CONCENT_CLIENT_PUBLIC_KEY']
        )

        if not force_task_to_compute.exists():
            raise Http400("'ForceReportComputedTask' for this task and client has not been initiated yet. Can't accept your 'AckReportComputedTask'.")
        if previous_ack_message.exists() or reject_message.exists():
            raise Http400(
                "Received AckReportComputedTask but RejectReportComputedTask "
                "or another AckReportComputedTask for this task has already been submitted."
            )

        assert force_task_to_compute.count() <= 2, "More that one 'ForceReportComputedTask' found for this task_id."

        store_message_and_message_status(
            client_message.TYPE,
            client_message.task_to_compute.compute_task_def['task_id'],
            client_message,
            provider_public_key  = force_task_to_compute.last().auth.provider_public_key_bytes,
            requestor_public_key = client_public_key,
            status               = ReceiveStatus,
        )
        subtask = update_subtask(
            subtask                     = subtask,
            state                       = Subtask.SubtaskState.REPORTED,
            next_deadline               = None,
            set_next_deadline           = True,
            ack_report_computed_task    = client_message,
        )
        store_pending_message(
            response_type       = PendingResponse.ResponseType.ForceReportComputedTaskResponse,
            client_public_key   = client_message.task_to_compute.provider_public_key,
            queue               = PendingResponse.Queue.Receive,
            subtask             = subtask,
        )
        logging.log_message_added_to_queue(
            client_message,
            client_public_key,
        )

        return HttpResponse("", status = 202)
    else:
        logging.log_timeout(
            client_message,
            request.META['HTTP_CONCENT_CLIENT_PUBLIC_KEY'],
            client_message.task_to_compute.compute_task_def['deadline'] + settings.CONCENT_MESSAGING_TIME,
        )
        raise Http400("Time to acknowledge this task is already over.")


def handle_send_reject_report_computed_task(request, client_message):
    current_time      = get_current_utc_timestamp()
    client_public_key = decode_client_public_key(request)
    validate_golem_message_reject(client_message.cannot_compute_task)

    try:
        subtask = Subtask.objects.get(
            subtask_id = client_message.cannot_compute_task.task_to_compute.compute_task_def['subtask_id'],
        )
    except Subtask.DoesNotExist:
        raise Http400("'ForceReportComputedTask' for this task and client has not been initiated yet. Can't accept your 'RejectReportComputedTask'.")

    if subtask.state_enum != Subtask.SubtaskState.FORCING_REPORT:
        raise Http400("Subtask state is {} instead of FORCING_REPORT. Can't accept your 'RejectReportComputedTask'.".format(
            subtask.state
        ))

    if subtask.report_computed_task.subtask_id != client_message.cannot_compute_task.task_to_compute.compute_task_def['subtask_id']:
        raise Http400("Received subtask_id does not match one in related ReportComputedTask. Can't accept your 'RejectReportComputedTask'.")

    if subtask.requestor.public_key != request.META['HTTP_CONCENT_CLIENT_PUBLIC_KEY']:
        raise Http400("Subtask requestor key does not match current client key. Can't accept your 'RejectReportComputedTask'.")

    force_report_computed_task = deserialize_message(subtask.report_computed_task.data.tobytes())

    force_report_computed_task_from_database = StoredMessage.objects.filter(
        task_id                    = client_message.cannot_compute_task.task_to_compute.compute_task_def['task_id'],
        type                       = message.ForceReportComputedTask.TYPE,
        auth__requestor_public_key = request.META['HTTP_CONCENT_CLIENT_PUBLIC_KEY']
    )

    if not force_report_computed_task_from_database.exists():
        raise Http400("'ForceReportComputedTask' for this task and client has not been initiated yet. Can't accept your 'RejectReportComputedTask'.")

    assert force_report_computed_task_from_database.count() <= 2, "More that one 'ForceReportComputedTask' found for this task_id."

    force_report_computed_task = deserialize_message(force_report_computed_task_from_database.last().data.tobytes())

    assert hasattr(force_report_computed_task.report_computed_task, 'task_to_compute')

    assert force_report_computed_task.report_computed_task.task_to_compute.compute_task_def['task_id'] == client_message.cannot_compute_task.task_to_compute.compute_task_def['task_id']
    if client_message.cannot_compute_task.reason == message.CannotComputeTask.REASON.WrongCTD:
        store_message_and_message_status(
            client_message.TYPE,
            force_report_computed_task.report_computed_task.task_to_compute.compute_task_def['task_id'],
            client_message,
            provider_public_key  = force_report_computed_task_from_database.last().auth.provider_public_key_bytes,
            requestor_public_key = client_public_key,
            status               = ReceiveStatus
        )
        subtask = update_subtask(
            subtask                     = subtask,
            state                       = Subtask.SubtaskState.REPORTED,
            next_deadline               = None,
            set_next_deadline           = True,
            reject_report_computed_task = client_message,
        )
        store_pending_message(
            response_type       = PendingResponse.ResponseType.ForceReportComputedTaskResponse,
            client_public_key   = client_message.cannot_compute_task.task_to_compute.provider_public_key,
            queue               = PendingResponse.Queue.Receive,
            subtask             = subtask,
        )
        store_pending_message(
            response_type       = PendingResponse.ResponseType.VerdictReportComputedTask,
            client_public_key   = subtask.requestor.public_key_bytes,
            queue               = PendingResponse.Queue.ReceiveOutOfBand,
            subtask             = subtask,
        )
        logging.log_message_added_to_queue(
            client_message,
            client_public_key,
        )

        return HttpResponse("", status = 202)

    if current_time <= force_report_computed_task.report_computed_task.task_to_compute.compute_task_def['deadline'] + settings.CONCENT_MESSAGING_TIME:
        if subtask.ack_report_computed_task_id is not None or subtask.reject_report_computed_task_id is not None:
            raise Http400("Received RejectReportComputedTask but AckReportComputedTask or another RejectReportComputedTask for this task has already been submitted.")

        ack_message             = StoredMessage.objects.filter(
            task_id                    = client_message.cannot_compute_task.task_to_compute.compute_task_def['task_id'],
            type                       = message.AckReportComputedTask.TYPE,
            auth__requestor_public_key = request.META['HTTP_CONCENT_CLIENT_PUBLIC_KEY']
        )
        previous_reject_message = StoredMessage.objects.filter(
            task_id                    = client_message.cannot_compute_task.task_to_compute.compute_task_def['task_id'],
            type                       = message.RejectReportComputedTask.TYPE,
            auth__requestor_public_key = request.META['HTTP_CONCENT_CLIENT_PUBLIC_KEY']
        )

        if ack_message.exists() or previous_reject_message.exists():
            raise Http400("Received RejectReportComputedTask but AckReportComputedTask or another RejectReportComputedTask for this task has already been submitted.")

        store_message_and_message_status(
            client_message.TYPE,
            force_report_computed_task.report_computed_task.task_to_compute.compute_task_def['task_id'],
            client_message,
            provider_public_key  = force_report_computed_task_from_database.last().auth.provider_public_key_bytes,
            requestor_public_key = client_public_key,
            status               = ReceiveStatus
        )
        subtask = update_subtask(
            subtask                     = subtask,
            state                       = Subtask.SubtaskState.FAILED,
            next_deadline               = None,
            set_next_deadline           = True,
            reject_report_computed_task = client_message,
        )
        store_pending_message(
            response_type       = PendingResponse.ResponseType.ForceReportComputedTaskResponse,
            client_public_key   = client_message.cannot_compute_task.task_to_compute.provider_public_key,
            queue               = PendingResponse.Queue.Receive,
            subtask             = subtask,
        )
        logging.log_message_added_to_queue(
            client_message,
            client_public_key,
        )
        return HttpResponse("", status = 202)
    else:
        logging.log_timeout(
            force_report_computed_task,
            request.META['HTTP_CONCENT_CLIENT_PUBLIC_KEY'],
            force_report_computed_task.report_computed_task.task_to_compute.compute_task_def['deadline'] + settings.CONCENT_MESSAGING_TIME,
        )
        raise Http400("Time to acknowledge this task is already over.")


def handle_send_force_get_task_result(request, client_message: message.concents.ForceGetTaskResult) -> message.concents:
    assert client_message.TYPE in message.registered_message_types

    current_time           = get_current_utc_timestamp()
    client_public_key      = decode_client_public_key(request)
    other_party_public_key = decode_other_party_public_key(request)
    validate_golem_message_task_to_compute(client_message.report_computed_task.task_to_compute)

    if StoredMessage.objects.filter(
        type                       = client_message.TYPE,
        task_id                    = client_message.report_computed_task.task_to_compute.compute_task_def['task_id'],
        auth__requestor_public_key = request.META['HTTP_CONCENT_CLIENT_PUBLIC_KEY']
    ).exists():
        return message.concents.ServiceRefused(
            reason      = message.concents.ServiceRefused.REASON.DuplicateRequest,
        )

    elif Subtask.objects.filter(
        subtask_id = client_message.report_computed_task.task_to_compute.compute_task_def['subtask_id'],
        state      = Subtask.SubtaskState.FORCING_RESULT_TRANSFER.name,  # pylint: disable=no-member
    ).exists():
        return message.concents.ServiceRefused(
            reason = message.concents.ServiceRefused.REASON.DuplicateRequest,
        )

    elif client_message.report_computed_task.task_to_compute.compute_task_def['deadline'] + settings.FORCE_ACCEPTANCE_TIME < current_time:
        logging.log_timeout(
            client_message,
            request.META['HTTP_CONCENT_CLIENT_PUBLIC_KEY'],
            client_message.report_computed_task.task_to_compute.compute_task_def['deadline'] + settings.FORCE_ACCEPTANCE_TIME,
        )
        return message.concents.ForceGetTaskResultRejected(
            reason    = message.concents.ForceGetTaskResultRejected.REASON.AcceptanceTimeLimitExceeded,
        )

    else:
        store_message_and_message_status(
            client_message.TYPE,
            client_message.report_computed_task.task_to_compute.compute_task_def['task_id'],
            client_message,
            provider_public_key  = other_party_public_key,
            requestor_public_key = client_public_key,
            status               = ReceiveStatus,
        )
        subtask = store_or_update_subtask(
            task_id                     = client_message.report_computed_task.task_to_compute.compute_task_def['task_id'],
            subtask_id                  = client_message.report_computed_task.task_to_compute.compute_task_def['subtask_id'],
            provider_public_key         = other_party_public_key,
            requestor_public_key        = client_public_key,
            state                       = Subtask.SubtaskState.FORCING_RESULT_TRANSFER,
            next_deadline               = client_message.report_computed_task.timestamp + settings.FORCE_ACCEPTANCE_TIME + settings.CONCENT_MESSAGING_TIME,
            set_next_deadline           = True,
            report_computed_task        = client_message.report_computed_task,
            task_to_compute             = client_message.report_computed_task.task_to_compute,
        )
        store_pending_message(
            response_type       = PendingResponse.ResponseType.ForceGetTaskResultUpload,
            client_public_key   = other_party_public_key,
            queue               = PendingResponse.Queue.Receive,
            subtask             = subtask,
        )
        return message.concents.AckForceGetTaskResult(
            force_get_task_result = client_message,
        )


def handle_send_force_subtask_results(request, client_message: message.concents.ForceSubtaskResults):
    assert isinstance(client_message, message.concents.ForceSubtaskResults)

    current_time           = get_current_utc_timestamp()
    client_public_key      = decode_client_public_key(request)
    other_party_public_key = decode_other_party_public_key(request)

    if StoredMessage.objects.filter(
        type                      = client_message.TYPE,
        task_id                   = client_message.ack_report_computed_task.task_to_compute.compute_task_def['task_id'],
        auth__provider_public_key = request.META['HTTP_CONCENT_CLIENT_PUBLIC_KEY'],
    ).exists():
        return message.concents.ServiceRefused(
            reason      = message.concents.ServiceRefused.REASON.DuplicateRequest,
        )

    if Subtask.objects.filter(
        subtask_id = client_message.ack_report_computed_task.task_to_compute.compute_task_def['subtask_id'],
        state      = Subtask.SubtaskState.FORCING_ACCEPTANCE.name,  # pylint: disable=no-member
    ).exists():
        return message.concents.ServiceRefused(
            reason = message.concents.ServiceRefused.REASON.DuplicateRequest,
        )

    if not base.is_provider_account_status_positive(request):
        return message.concents.ServiceRefused(
            reason      = message.concents.ServiceRefused.REASON.TooSmallProviderDeposit,
        )

    verification_deadline       = client_message.ack_report_computed_task.timestamp + settings.SUBTASK_VERIFICATION_TIME
    forcing_acceptance_deadline = client_message.ack_report_computed_task.timestamp + settings.SUBTASK_VERIFICATION_TIME + settings.FORCE_ACCEPTANCE_TIME
    if forcing_acceptance_deadline < current_time:
        logging.log_timeout(
            client_message,
            request.META['HTTP_CONCENT_CLIENT_PUBLIC_KEY'],
            forcing_acceptance_deadline,
        )
        return message.concents.ForceSubtaskResultsRejected(
            reason = message.concents.ForceSubtaskResultsRejected.REASON.RequestTooLate,
        )
    elif current_time < verification_deadline:
        logging.log_timeout(
            client_message,
            request.META['HTTP_CONCENT_CLIENT_PUBLIC_KEY'],
            verification_deadline,
        )
        return message.concents.ForceSubtaskResultsRejected(
            reason = message.concents.ForceSubtaskResultsRejected.REASON.RequestPremature,
        )
    else:
        store_message_and_message_status(
            client_message.TYPE,
            client_message.ack_report_computed_task.task_to_compute.compute_task_def['task_id'],
            client_message,
            status               = ReceiveStatus,
            provider_public_key  = client_public_key,
            requestor_public_key = other_party_public_key,
        )
        subtask = store_or_update_subtask(
            task_id                     = client_message.ack_report_computed_task.task_to_compute.compute_task_def['task_id'],
            subtask_id                  = client_message.ack_report_computed_task.task_to_compute.compute_task_def['subtask_id'],
            provider_public_key         = client_public_key,
            requestor_public_key        = other_party_public_key,
            state                       = Subtask.SubtaskState.FORCING_ACCEPTANCE,
            next_deadline               = forcing_acceptance_deadline + settings.CONCENT_MESSAGING_TIME,
            set_next_deadline           = True,
            ack_report_computed_task    = client_message.ack_report_computed_task,
            task_to_compute             = client_message.ack_report_computed_task.task_to_compute,
        )
        store_pending_message(
            response_type       = PendingResponse.ResponseType.ForceSubtaskResults,
            client_public_key   = other_party_public_key,
            queue               = PendingResponse.Queue.Receive,
            subtask             = subtask,
        )
        logging.log_message_added_to_queue(
            client_message,
            client_public_key,
        )
        return HttpResponse("", status = 202)


def handle_send_force_subtask_results_response(request, client_message):
    assert isinstance(client_message, message.concents.ForceSubtaskResultsResponse)

    current_time      = get_current_utc_timestamp()
    client_public_key = decode_client_public_key(request)

    if isinstance(client_message.subtask_results_accepted, message.tasks.SubtaskResultsAccepted):
        client_message_task_id    = client_message.subtask_results_accepted.task_to_compute.compute_task_def['task_id']
        client_message_subtask_id = client_message.subtask_results_accepted.task_to_compute.compute_task_def['subtask_id']
        report_computed_task      = None
        subtask_results_accepted  = client_message.subtask_results_accepted
        subtask_results_rejected  = None
        state                     = Subtask.SubtaskState.ACCEPTED
        response_type             = PendingResponse.ResponseType.ForceSubtaskResultsResponse
        provider_public_key       = client_message.subtask_results_accepted.task_to_compute.provider_public_key
    else:
        client_message_task_id    = client_message.subtask_results_rejected.report_computed_task.task_to_compute.compute_task_def['task_id']
        client_message_subtask_id = client_message.subtask_results_rejected.report_computed_task.task_to_compute.compute_task_def['subtask_id']
        report_computed_task      = client_message.subtask_results_rejected.report_computed_task
        subtask_results_accepted  = None
        subtask_results_rejected  = client_message.subtask_results_rejected
        state                     = Subtask.SubtaskState.REJECTED
        response_type             = PendingResponse.ResponseType.SubtaskResultsRejected
        provider_public_key       = client_message.subtask_results_rejected.report_computed_task.task_to_compute.provider_public_key

    try:
        subtask = Subtask.objects.get(
            subtask_id = client_message_subtask_id,
        )
    except Subtask.DoesNotExist:
        raise Http400("'ForceSubtaskResults' for this subtask has not been initiated yet. Can't accept your '{}'.".format(client_message.TYPE))

    if subtask.state_enum != Subtask.SubtaskState.FORCING_ACCEPTANCE:
        raise Http400("Subtask state is {} instead of FORCING_ACCEPTANCE. Can't accept your '{}'.".format(
            subtask.state,
            client_message.TYPE,
        ))

    if subtask.requestor.public_key != request.META['HTTP_CONCENT_CLIENT_PUBLIC_KEY']:
        raise Http400("Subtask requestor key does not match current client key.  Can't accept your '{}'.".format(
            client_message.TYPE
        ))

    if subtask.subtask_results_accepted_id is not None or subtask.subtask_results_rejected_id is not None:
        raise Http400("This subtask has been resolved already.")

    force_subtask_results                   = StoredMessage.objects.filter(
        task_id                    = client_message_task_id,
        type                       = message.concents.ForceSubtaskResults.TYPE,
        auth__requestor_public_key = request.META['HTTP_CONCENT_CLIENT_PUBLIC_KEY'],
    )
    previous_force_subtask_results_response = StoredMessage.objects.filter(
        task_id                    = client_message_task_id,
        type                       = message.concents.ForceSubtaskResultsResponse.TYPE,
        auth__requestor_public_key = request.META['HTTP_CONCENT_CLIENT_PUBLIC_KEY'],
    )

    if not force_subtask_results.exists():
        raise Http400("'ForceSubtaskResults' for this subtask has not been initiated yet. Can't accept your '{}'.".format(client_message.TYPE))
    if previous_force_subtask_results_response.exists():
        raise Http400("This subtask has been resolved already.")

    assert 1 <= force_subtask_results.count() <= 2, "Other amount of 'ForceSubtaskResults' than 1 or 2 found for this task_id."
    decoded_message_from_database = deserialize_message(force_subtask_results.last().data.tobytes())

    verification_deadline = decoded_message_from_database.ack_report_computed_task.timestamp + settings.SUBTASK_VERIFICATION_TIME
    acceptance_deadline = verification_deadline + settings.FORCE_ACCEPTANCE_TIME + settings.CONCENT_MESSAGING_TIME

    if current_time > acceptance_deadline:
        logging.log_timeout(
            client_message,
            request.META['HTTP_CONCENT_CLIENT_PUBLIC_KEY'],
            client_message.timestamp + settings.CONCENT_MESSAGING_TIME,
        )
        raise Http400("Time to accept this task is already over.")

    store_message_and_message_status(
        client_message.TYPE,
        client_message_task_id,
        client_message,
        status               = ReceiveStatus,
        provider_public_key  = force_subtask_results.last().auth.provider_public_key_bytes,
        requestor_public_key = client_public_key,
    )
    subtask = update_subtask(
        subtask                     = subtask,
        state                       = state,
        next_deadline               = None,
        set_next_deadline           = True,
        report_computed_task        = report_computed_task,
        subtask_results_accepted    = subtask_results_accepted,
        subtask_results_rejected    = subtask_results_rejected,
    )
    store_pending_message(
        response_type       = response_type,
        client_public_key   = provider_public_key,
        queue               = PendingResponse.Queue.Receive,
        subtask             = subtask,
    )
    logging.log_message_added_to_queue(
        client_message,
        client_public_key,
    )
    return HttpResponse("", status = 202)


def verify_message_subtask_results_accepted(subtask_results_accepted_list: dict) -> bool:
    """
    function verify if all requestor public key and ethereum public key
    in subtask_reesults_accepted_list are the same
    """
    verify_public_key           = len(set(subtask_results_accepted.task_to_compute.requestor_public_key             for subtask_results_accepted in subtask_results_accepted_list)) == 1
    verify_ethereum_public_key  = len(set(subtask_results_accepted.task_to_compute.requestor_ethereum_public_key    for subtask_results_accepted in subtask_results_accepted_list)) == 1
    return bool(verify_public_key is True and verify_ethereum_public_key is True)


def handle_send_force_payment(request, client_message: message.concents.ForcePayment) -> message.concents.ForcePaymentCommitted:  # pylint: disable=inconsistent-return-statements
    client_public_key       = decode_client_public_key(request)
    other_party_public_key  = decode_other_party_public_key(request)
    current_time            = get_current_utc_timestamp()

    if not verify_message_subtask_results_accepted(client_message.subtask_results_accepted_list):
        return message.concents.ServiceRefused(
            reason = message.concents.ServiceRefused.REASON.InvalidRequest
        )
    requestor_ethereum_public_key = client_message.subtask_results_accepted_list[0].task_to_compute.requestor_ethereum_public_key

    # Concent defines time T0 equal to oldest payment_ts from passed SubtaskResultAccepted messages from subtask_results_accepted_list.
    oldest_payments_ts = min(subtask_results_accepted.payment_ts for subtask_results_accepted in client_message.subtask_results_accepted_list)

    # Concent gets list of transactions from payment API where timestamp >= T0.
    list_of_transactions = base.get_list_of_transactions(current_time = current_time, request = request)  # pylint: disable=no-value-for-parameter

    # Concent defines time T1 equal to youngest timestamp from list of transactions.
    youngest_transaction = max(transaction['timestamp'] for transaction in list_of_transactions)

    # Concent checks if all passed SubtaskResultAccepted messages from subtask_results_accepted_list have payment_ts < T1
    T1_is_bigger_than_payments_ts = any(youngest_transaction > subtask_results_accepted.payment_ts for subtask_results_accepted in client_message.subtask_results_accepted_list)

    # Any of the items from list of overdue acceptances matches condition current_time < payment_ts + PAYMENT_DUE_TIME + PAYMENT_GRACE_PERIOD.
    acceptance_time_overdue = any(current_time < subtask_results_accepted.payment_ts + settings.PAYMENT_DUE_TIME + settings.PAYMENT_GRACE_PERIOD for subtask_results_accepted in client_message.subtask_results_accepted_list)

    if T1_is_bigger_than_payments_ts or acceptance_time_overdue:
        return message.concents.ForcePaymentRejected(
            reason = message.concents.ForcePaymentRejected.REASON.TimestampError
        )

    # Concent gets list of list of forced payments from payment API where T0 <= payment_ts + PAYMENT_DUE_TIME + PAYMENT_GRACE_PERIOD.
    list_of_forced_payments = base.get_forced_payments(oldest_payments_ts, requestor_ethereum_public_key, client_public_key, request = request)

    sum_of_payments = base.payment_summary(request = request, subtask_results_accepted_list = client_message.subtask_results_accepted_list, list_of_transactions = list_of_transactions, list_of_forced_payments = list_of_forced_payments)  # pylint: disable=no-value-for-parameter

    # Concent defines time T2 (end time) equal to youngest payment_ts from passed SubtaskResultAccepted messages from subtask_results_accepted_list.
    payment_ts = min(subtask_results_accepted.payment_ts for subtask_results_accepted in client_message.subtask_results_accepted_list)

    if sum_of_payments <= 0:
        return message.concents.ForcePaymentRejected(
            reason = message.concents.ForcePaymentRejected.REASON.NoUnsettledTasksFound
        )
    elif sum_of_payments > 0:
        base.make_payment_to_provider(sum_of_payments, payment_ts, requestor_ethereum_public_key, client_public_key)
        provider_force_payment_commited = message.concents.ForcePaymentCommitted(
            payment_ts              = payment_ts,
            task_owner_key          = requestor_ethereum_public_key,
            provider_eth_account    = client_public_key,
            amount_paid             = Decimal('10.99'),
            amount_pending          = Decimal('0.01'),
            recipient_type          = message.concents.ForcePaymentCommitted.Actor.Provider,
        )

        store_message_and_message_status(
            provider_force_payment_commited.TYPE,
            None,
            provider_force_payment_commited,
            provider_public_key     = client_public_key,
            requestor_public_key    = other_party_public_key,
        )

        requestor_force_payment_commited = message.concents.ForcePaymentCommitted(
            payment_ts              = payment_ts,
            task_owner_key          = requestor_ethereum_public_key,
            provider_eth_account    = client_public_key,
            amount_paid             = Decimal('10.99'),
            amount_pending          = Decimal('0.01'),
            recipient_type          = message.concents.ForcePaymentCommitted.Actor.Requestor,
        )
        store_pending_message(
            response_type       = PendingResponse.ResponseType.ForcePaymentCommitted,
            client_public_key   = other_party_public_key,
            queue               = PendingResponse.Queue.ReceiveOutOfBand,
            payment_message     = requestor_force_payment_commited
        )

        provider_force_payment_commited.sig = None
        return provider_force_payment_commited


def handle_unsupported_golem_messages_type(client_message):
    if hasattr(client_message, 'TYPE'):
        raise Http400("This message type ({}) is either not supported or cannot be submitted to Concent.".format(client_message.TYPE))
    else:
        raise Http400("Unknown message type or not a Golem message.")


def handle_receive_delivered_force_report_computed_task(request, delivered_message):
    force_report_task = deserialize_message(delivered_message.message.data.tobytes())
    client_public_key = decode_client_public_key(request)

    ack_report_computed_task                    = message.AckReportComputedTask()
    ack_report_computed_task.task_to_compute    = force_report_task.report_computed_task.task_to_compute
    force_report_computed_task_response         = message.concents.ForceReportComputedTaskResponse(
        ack_report_computed_task = ack_report_computed_task
    )
    store_message_and_message_status(
        force_report_computed_task_response.TYPE,
        force_report_computed_task_response.ack_report_computed_task.task_to_compute.compute_task_def['task_id'],  # pylint: disable=no-member
        force_report_computed_task_response,
        provider_public_key  = client_public_key,
        requestor_public_key = delivered_message.message.auth.requestor_public_key_bytes,
    )
    return force_report_computed_task_response


def handle_receive_ack_from_force_report_computed_task(request, decoded_message, undelivered_message):
    force_report_computed_task_response = message.concents.ForceReportComputedTaskResponse(
        ack_report_computed_task = message.concents.AckReportComputedTask(
            task_to_compute = decoded_message.report_computed_task.task_to_compute
        )
    )
    client_public_key = decode_client_public_key(request)
    store_message_and_message_status(
        force_report_computed_task_response.TYPE,
        force_report_computed_task_response.ack_report_computed_task.task_to_compute.compute_task_def['task_id'],  # pylint: disable=no-member
        force_report_computed_task_response,
        status                  = ReceiveStatus,
        delivered               = True,
        provider_public_key     = client_public_key,
        requestor_public_key    = undelivered_message.message.auth.requestor_public_key_bytes,
    )
    return force_report_computed_task_response


def handle_receive_force_report_computed_task(request, decoded_message, undelivered_message):
    force_report_computed_task = message.concents.ForceReportComputedTask(
        report_computed_task = decoded_message.report_computed_task
    )
    client_public_key = decode_client_public_key(request)
    store_message_and_message_status(
        force_report_computed_task.TYPE,
        force_report_computed_task.report_computed_task.task_to_compute.compute_task_def['task_id'],
        force_report_computed_task,
        status                  = ReceiveStatus,
        delivered               = True,
        provider_public_key     = undelivered_message.message.auth.provider_public_key_bytes,
        requestor_public_key    = client_public_key,
    )
    return force_report_computed_task


def handle_receive_force_subtask_results_settled(
    decoded_message:        message.concents.ForceSubtaskResults,
    provider_public_key,
    requestor_public_key,
    message_model
) -> message.concents.ForceSubtaskResults:
    assert isinstance(decoded_message, message.concents.ForceSubtaskResults)

    subtask_results_settled = message.concents.SubtaskResultsSettled(
        origin = message.concents.SubtaskResultsSettled.Origin.ResultsAcceptedTimeout,
    )

    subtask_results_settled.task_to_compute = decoded_message.ack_report_computed_task.task_to_compute
    store_message_and_message_status(
        subtask_results_settled.TYPE,
        subtask_results_settled.task_to_compute.compute_task_def['task_id'],
        subtask_results_settled,
        provider_public_key  = provider_public_key,
        requestor_public_key = requestor_public_key,
        status               = message_model,
        delivered            = True,
    )
    return subtask_results_settled


def handle_receive_ack_or_reject_report_computed_task(request, decoded_message, undelivered_message):
    if isinstance(decoded_message, message.concents.RejectReportComputedTask):
        force_report_computed_task_response = message.concents.ForceReportComputedTaskResponse(
            reject_report_computed_task = decoded_message
        )
        task_id = decoded_message.cannot_compute_task.task_to_compute.compute_task_def['task_id']
    else:
        force_report_computed_task_response = message.concents.ForceReportComputedTaskResponse(
            ack_report_computed_task = decoded_message
        )
        task_id = decoded_message.task_to_compute.compute_task_def['task_id']

    client_public_key = decode_client_public_key(request)
    store_message_and_message_status(
        force_report_computed_task_response.TYPE,
        task_id,
        force_report_computed_task_response,
        status                  = ReceiveStatus,
        delivered               = True,
        provider_public_key     = client_public_key,
        requestor_public_key    = undelivered_message.message.auth.requestor_public_key_bytes,
    )
    return force_report_computed_task_response


def handle_receive_force_get_task_result_upload_for_provider(
    request,
    decoded_message:                       message.concents.ForceGetTaskResult,
    previous_message_status_from_database: ReceiveStatus
) -> message.concents.ForceGetTaskResult:
    assert decoded_message.TYPE in message.registered_message_types

    current_time            = get_current_utc_timestamp()
    client_public_key       = decode_client_public_key(request)
    file_transfer_token     = message.concents.FileTransferToken(
        token_expiration_deadline       = current_time + settings.TOKEN_EXPIRATION_TIME,
        storage_cluster_address         = settings.STORAGE_CLUSTER_ADDRESS,
        authorized_client_public_key    = request.META['HTTP_CONCENT_CLIENT_PUBLIC_KEY'],
        operation                       = 'upload',
    )

    assert file_transfer_token.timestamp <= file_transfer_token.token_expiration_deadline  # pylint: disable=no-member

    task_id     = decoded_message.report_computed_task.task_to_compute.compute_task_def['task_id']
    part_id     = '0'
    file_path   = '{}/{}/result'.format(task_id, part_id)

    file_transfer_token.files                 = [message.concents.FileTransferToken.FileInfo()]
    file_transfer_token.files[0]['path']      = file_path
    file_transfer_token.files[0]['checksum']  = decoded_message.report_computed_task.package_hash
    file_transfer_token.files[0]['size']      = decoded_message.report_computed_task.size

    force_get_task_result_upload = message.concents.ForceGetTaskResultUpload(
        force_get_task_result   = decoded_message,
        file_transfer_token     = file_transfer_token,
    )

    store_message_and_message_status(
        force_get_task_result_upload.TYPE,
        decoded_message.report_computed_task.task_to_compute.compute_task_def['task_id'],
        force_get_task_result_upload,
        provider_public_key  = client_public_key,
        requestor_public_key = previous_message_status_from_database.message.auth.requestor_public_key_bytes,
        status               = ReceiveStatus,
        delivered            = True,
    )
    return force_get_task_result_upload


def handle_receive_force_get_task_result_failed(
    request,
    decoded_message:                       message.concents.ForceGetTaskResultUpload,
    previous_message_status_from_database: ReceiveStatus
) -> message.concents.ForceGetTaskResultUpload:
    assert decoded_message.TYPE in message.registered_message_types

    client_public_key = decode_client_public_key(request)
    force_get_task_result_failed = message.concents.ForceGetTaskResultFailed()
    force_get_task_result_failed.task_to_compute = decoded_message.force_get_task_result.report_computed_task.task_to_compute
    store_message_and_message_status(
        force_get_task_result_failed.TYPE,
        force_get_task_result_failed.task_to_compute.compute_task_def['task_id'],
        force_get_task_result_failed,
        provider_public_key  = previous_message_status_from_database.message.auth.provider_public_key_bytes,
        requestor_public_key = client_public_key,
        status               = ReceiveStatus,
        delivered            = True,
    )
    return force_get_task_result_failed


def handle_receive_force_subtask_results_response(
    request,
    decoded_message,
    undelivered_message,
):
    client_public_key = decode_client_public_key(request)
    if isinstance(decoded_message.subtask_results_rejected, message.tasks.SubtaskResultsRejected):
        task_id = decoded_message.subtask_results_rejected.report_computed_task.task_to_compute.compute_task_def['task_id']
    else:
        task_id = decoded_message.subtask_results_accepted.task_to_compute.compute_task_def['task_id']
    force_subtask_results_response              = message.concents.ForceSubtaskResultsResponse(
        subtask_results_rejected = decoded_message.subtask_results_rejected,
        subtask_results_accepted = decoded_message.subtask_results_accepted,
    )
    store_message_and_message_status(
        force_subtask_results_response.TYPE,
        task_id,
        force_subtask_results_response,
        status                  = ReceiveStatus,
        delivered               = True,
        provider_public_key     = client_public_key,
        requestor_public_key    = undelivered_message.message.auth.requestor_public_key_bytes,
    )
    return force_subtask_results_response


def handle_receive_force_get_task_result_upload_for_requestor(
    request,
    decoded_message:                       message.concents.ForceGetTaskResultUpload,
    previous_message_status_from_database: ReceiveStatus
) -> message.concents.ForceGetTaskResultUpload:
    assert decoded_message.TYPE in message.registered_message_types

    client_public_key   = decode_client_public_key(request)
    current_time        = get_current_utc_timestamp()
    file_transfer_token = message.concents.FileTransferToken(
        token_expiration_deadline    = current_time + settings.TOKEN_EXPIRATION_TIME,
        storage_cluster_address      = decoded_message.file_transfer_token.storage_cluster_address,
        authorized_client_public_key = decoded_message.file_transfer_token.authorized_client_public_key,
        operation                    = 'download',
        files                        = decoded_message.file_transfer_token.files,
    )

    assert file_transfer_token.timestamp <= file_transfer_token.token_expiration_deadline  # pylint: disable=no-member

    force_get_task_result_upload = message.concents.ForceGetTaskResultUpload(
        file_transfer_token = file_transfer_token,
    )
    force_get_task_result_upload.force_get_task_result = decoded_message.force_get_task_result

    store_message_and_message_status(
        force_get_task_result_upload.TYPE,
        force_get_task_result_upload.force_get_task_result.report_computed_task.task_to_compute.compute_task_def['task_id'],
        force_get_task_result_upload,
        provider_public_key  = previous_message_status_from_database.message.auth.provider_public_key_bytes,
        requestor_public_key = client_public_key,
        status               = ReceiveStatus,
        delivered            = True,
    )
    return force_get_task_result_upload


def handle_receive_force_subtask_results(
    request,
    decoded_message:                 message.concents.ForceSubtaskResults,
    last_undelivered_message_status: ReceiveStatus
):
    assert decoded_message.TYPE in message.registered_message_types

    client_public_key = decode_client_public_key(request)

    requestor_force_subtask_results                             = message.concents.ForceSubtaskResults()
    requestor_force_subtask_results.ack_report_computed_task    = decoded_message.ack_report_computed_task

    store_message_and_message_status(
        requestor_force_subtask_results.TYPE,
        decoded_message.ack_report_computed_task.task_to_compute.compute_task_def['task_id'],
        requestor_force_subtask_results,
        provider_public_key  = last_undelivered_message_status.message.auth.provider_public_key_bytes,
        requestor_public_key = client_public_key,
        status               = ReceiveStatus,
        delivered            = True,
    )
    return requestor_force_subtask_results


def set_message_as_delivered(client_message):
    client_message.delivered = True
    client_message.full_clean()
    client_message.save()


def handle_receive_out_of_band_ack_report_computed_task(request, undelivered_message):
    client_public_key = decode_client_public_key(request)
    decoded_force_report_computed_task_response = deserialize_message(undelivered_message.data.tobytes())

    force_report_computed_task                                      = message.concents.ForceReportComputedTask()
    force_report_computed_task.report_computed_task                 = message.tasks.ReportComputedTask()
    force_report_computed_task.report_computed_task.task_to_compute = decoded_force_report_computed_task_response.ack_report_computed_task.task_to_compute

    message_verdict                             = message.VerdictReportComputedTask()
    message_verdict.force_report_computed_task  = force_report_computed_task
    message_verdict.ack_report_computed_task    = decoded_force_report_computed_task_response.ack_report_computed_task

    store_message_and_message_status(
        message_verdict.TYPE,
        decoded_force_report_computed_task_response.ack_report_computed_task.task_to_compute.compute_task_def['task_id'],
        message_verdict,
        provider_public_key  = undelivered_message.auth.provider_public_key_bytes,
        requestor_public_key = client_public_key,
        status               = ReceiveOutOfBandStatus,
        delivered            = True
    )
    return message_verdict


def handle_receive_out_of_band_force_report_computed_task(request, undelivered_message):
    client_public_key = decode_client_public_key(request)
    decoded_force_report_computed_task = deserialize_message(undelivered_message.data.tobytes())

    ack_report_computed_task                    = message.AckReportComputedTask()
    ack_report_computed_task.task_to_compute    = decoded_force_report_computed_task.report_computed_task.task_to_compute

    message_verdict                             = message.VerdictReportComputedTask()
    message_verdict.ack_report_computed_task    = ack_report_computed_task
    message_verdict.force_report_computed_task  = decoded_force_report_computed_task

    store_message_and_message_status(
        message_verdict.TYPE,
        decoded_force_report_computed_task.report_computed_task.task_to_compute.compute_task_def['task_id'],
        message_verdict,
        provider_public_key  = undelivered_message.auth.provider_public_key_bytes,
        requestor_public_key = client_public_key,
        status               = ReceiveOutOfBandStatus,
        delivered            = True
    )
    return message_verdict


def handle_receive_out_of_band_reject_report_computed_task(request, undelivered_message):
    client_public_key = decode_client_public_key(request)
    decoded_reject_report_computed_task = deserialize_message(undelivered_message.data.tobytes())

    message_verdict                                          = message.VerdictReportComputedTask()
    message_verdict.ack_report_computed_task                 = message.AckReportComputedTask()
    message_verdict.ack_report_computed_task.task_to_compute = decoded_reject_report_computed_task.cannot_compute_task.task_to_compute

    store_message_and_message_status(
        message_verdict.TYPE,
        decoded_reject_report_computed_task.cannot_compute_task.task_to_compute.compute_task_def['task_id'],
        message_verdict,
        provider_public_key  = undelivered_message.auth.provider_public_key_bytes,
        requestor_public_key = client_public_key,
        status               = ReceiveOutOfBandStatus,
        delivered            = True
    )
    return message_verdict


def handle_receive_out_of_band_force_payment_commited(request, undelivered_message):
    client_public_key = decode_client_public_key(request)

    decoded_force_payment_commited  = deserialize_message(undelivered_message.data.tobytes())
    last_force_payment              = ReceiveOutOfBandStatus.objects.filter(
        delivered       = True,
        message__type   = undelivered_message.type,
    ).order_by('timestamp')
    if last_force_payment.exists():
        for force_payment_message in last_force_payment:
            payment_ts = deserialize_message(force_payment_message.message.data.tobytes()).payment_ts
            if decoded_force_payment_commited.payment_ts == payment_ts:
                return None

    requestor_force_payment_commited = message.concents.ForcePaymentCommitted(
        payment_ts              = decoded_force_payment_commited.payment_ts,
        task_owner_key          = decoded_force_payment_commited.task_owner_key,
        provider_eth_account    = decoded_force_payment_commited.provider_eth_account,
        amount_paid             = decoded_force_payment_commited.amount_paid,
        amount_pending          = decoded_force_payment_commited.amount_pending,
        recipient_type          = message.concents.ForcePaymentCommitted.Actor.Requestor,
    )

    store_message_and_message_status(
        requestor_force_payment_commited.TYPE,
        None,
        requestor_force_payment_commited,
        status                  = ReceiveOutOfBandStatus,
        delivered               = True,
        provider_public_key     = undelivered_message.auth.provider_public_key_bytes,
        requestor_public_key    = client_public_key,
    )
    return requestor_force_payment_commited


def deserialize_message(raw_message_data):
    try:
        golem_message = message.Message.deserialize(
            raw_message_data,
            None,
            check_time = False
        )
        assert golem_message is not None
        return golem_message
    except MessageError as exception:
        raise Http400("Unable to deserialize Golem Message: {}.".format(exception))


def validate_golem_message_task_to_compute(data):
    if not isinstance(data, message.TaskToCompute):
        raise Http400("Expected TaskToCompute.")

    data.compute_task_def['deadline'] = validate_int_value(data.compute_task_def['deadline'])

    validate_task_id(data.compute_task_def['task_id'])


def validate_golem_message_reject(data):
    if not isinstance(data, message.CannotComputeTask) and not isinstance(data, message.TaskFailure) and not isinstance(data, message.TaskToCompute):
        raise Http400("Expected CannotComputeTask, TaskFailure or TaskToCompute.")

    if isinstance(data, message.CannotComputeTask):
        validate_task_id(data.task_to_compute.compute_task_def['task_id'])

    if isinstance(data, (message.TaskToCompute, message.TaskFailure)):
        if data.compute_task_def['task_id'] == '':
            raise Http400("task_id cannot be blank.")

        data.compute_task_def['deadline'] = validate_int_value(data.compute_task_def['deadline'])


def validate_int_value(value):
    """
    Checks if value is an integer. If not, tries to cast it to an integer.
    Then checks if value is non-negative.

    """
    if not isinstance(value, int):
        try:
            value = int(value)
        except (ValueError, TypeError):
            raise Http400("Wrong type, expected a value that can be converted to an integer.")
    if value < 0:
        raise Http400("Wrong type, expected non-negative integer but negative integer provided.")
    return value


def validate_task_id(task_id):
    if not isinstance(task_id, str):
        raise Http400("task_id must be string.")

    if task_id == '':
        raise Http400("task_id cannot be blank.")

    if len(task_id) > MESSAGE_TASK_ID_MAX_LENGTH:
        raise Http400("task_id cannot be longer than {} chars.".format(MESSAGE_TASK_ID_MAX_LENGTH))


def store_message_and_message_status(
    golem_message_type:     int,
    task_id:                str,
    golem_message:          message.base.Message,
    provider_public_key:    str,
    requestor_public_key:   str,
    status:                 type    = None,
    delivered:              bool    = False
):
    assert golem_message_type   in message.registered_message_types
    assert status               in [ReceiveStatus, ReceiveOutOfBandStatus, None]
    assert provider_public_key  is not None
    assert requestor_public_key is not None

    message_timestamp = datetime.datetime.now(timezone.utc)
    stored_message = StoredMessage(
        type        = golem_message_type,
        timestamp   = message_timestamp,
        data        = copy.copy(golem_message).serialize(),
        task_id     = task_id
    )
    stored_message.full_clean()
    stored_message.save()

    message_auth = MessageAuth(
        message                    = stored_message,
        provider_public_key_bytes  = provider_public_key,
        requestor_public_key_bytes = requestor_public_key,
    )
    message_auth.full_clean()
    message_auth.save()

    if status is not None:
        receive_message_status  = status(
            message     = stored_message,
            timestamp   = message_timestamp,
            delivered   = delivered
        )
        receive_message_status.full_clean()
        receive_message_status.save()


def store_subtask(
    task_id:                        str,
    subtask_id:                     str,
    provider_public_key:            bytes,
    requestor_public_key:           bytes,
    state:                          Subtask.SubtaskState,
    next_deadline:                  int,
    task_to_compute:                message.TaskToCompute                = None,
    report_computed_task:           message.ReportComputedTask           = None,
    ack_report_computed_task:       message.AckReportComputedTask        = None,
    reject_report_computed_task:    message.RejectReportComputedTask     = None,
    subtask_results_accepted:       message.tasks.SubtaskResultsAccepted = None,
    subtask_results_rejected:       message.tasks.SubtaskResultsRejected = None,
):
    """
    Validates and stores subtask and its data in Subtask table.
    Stores related messages in StoredMessage table and adds relation to newly created subtask.
    """
    assert isinstance(task_id,              str)
    assert isinstance(subtask_id,           str)
    assert isinstance(provider_public_key,  bytes)
    assert isinstance(requestor_public_key, bytes)
    assert state in Subtask.SubtaskState
    assert (state in Subtask.ACTIVE_STATES)  == (next_deadline is not None)
    assert (state in Subtask.PASSIVE_STATES) == (next_deadline is None)

    provider  = Client.objects.get_or_create_full_clean(provider_public_key)
    requestor = Client.objects.get_or_create_full_clean(requestor_public_key)

    subtask = Subtask(
        task_id         = task_id,
        subtask_id      = subtask_id,
        provider        = provider,
        requestor       = requestor,
        state           = state.name,
        next_deadline   = parse_timestamp_to_utc_datetime(next_deadline),
    )

    set_subtask_messages(
        subtask,
        task_to_compute             = task_to_compute,
        report_computed_task        = report_computed_task,
        ack_report_computed_task    = ack_report_computed_task,
        reject_report_computed_task = reject_report_computed_task,
        subtask_results_accepted    = subtask_results_accepted,
        subtask_results_rejected    = subtask_results_rejected,
    )

    subtask.full_clean()
    subtask.save()

    logging.log_subtask_stored(
        task_id,
        subtask_id,
        state.name,
        subtask.provider.public_key,
        subtask.requestor.public_key,
        next_deadline,
    )

    return subtask


def verify_file_status(
    client_public_key: bytes,
):
    """
    Function to verify existence of a file on cluster storage
    """

    force_get_task_result_list = Subtask.objects.filter(
        requestor__public_key  = b64encode(client_public_key),
        state                  = Subtask.SubtaskState.FORCING_RESULT_TRANSFER.name,  # pylint: disable=no-member
    )

    for get_task_result in force_get_task_result_list:
        report_computed_task    = deserialize_message(get_task_result.report_computed_task.data.tobytes())
        file_transfer_token     = create_file_transfer_token(
            report_computed_task,
            client_public_key,
            'upload'
        )
        if request_upload_status(file_transfer_token):
            subtask               = get_task_result
            subtask.state         = Subtask.SubtaskState.RESULT_UPLOADED.name  # pylint: disable=no-member
            subtask.next_deadline = None
            subtask.full_clean()
            subtask.save()

            store_pending_message(
                response_type       = PendingResponse.ResponseType.ForceGetTaskResultDownload,
                client_public_key   = subtask.requestor.public_key_bytes,
                queue               = PendingResponse.Queue.Receive,
                subtask             = subtask,
            )
            logging.log_file_status(
                subtask.subtask_id,
                subtask.requestor.public_key,
                subtask.provider.public_key,
            )


def update_timed_out_subtasks(
    client_public_key: bytes,
):
    verify_file_status(client_public_key)

    clients_subtask_list = Subtask.objects.filter(
        Q(requestor__public_key = b64encode(client_public_key)) | Q(provider__public_key = b64encode(client_public_key)),
        state__in               = [state.name for state in Subtask.ACTIVE_STATES],
        next_deadline__lte      = timezone.now()
    )

    if clients_subtask_list.exists():
        for subtask in clients_subtask_list:
            if subtask.state == Subtask.SubtaskState.FORCING_REPORT.name:  # pylint: disable=no-member
                update_subtask_state(
                    subtask                 = subtask,
                    state                   = Subtask.SubtaskState.REPORTED.name,  # pylint: disable=no-member
                )
                store_pending_message(
                    response_type       = PendingResponse.ResponseType.ForceReportComputedTaskResponse,
                    client_public_key   = subtask.provider.public_key_bytes,
                    queue               = PendingResponse.Queue.Receive,
                    subtask             = subtask,
                )
                store_pending_message(
                    response_type       = PendingResponse.ResponseType.VerdictReportComputedTask,
                    client_public_key   = subtask.requestor.public_key_bytes,
                    queue               = PendingResponse.Queue.ReceiveOutOfBand,
                    subtask             = subtask,
                )
            elif subtask.state == Subtask.SubtaskState.FORCING_RESULT_TRANSFER.name:  # pylint: disable=no-member
                update_subtask_state(
                    subtask                 = subtask,
                    state                   = Subtask.SubtaskState.FAILED.name,  # pylint: disable=no-member
                )
                store_pending_message(
                    response_type       = PendingResponse.ResponseType.ForceGetTaskResultFailed,
                    client_public_key   = subtask.requestor.public_key_bytes,
                    queue               = PendingResponse.Queue.Receive,
                    subtask             = subtask,
                )
            elif subtask.state == Subtask.SubtaskState.FORCING_ACCEPTANCE.name:  # pylint: disable=no-member
                update_subtask_state(
                    subtask                 = subtask,
                    state                   = Subtask.SubtaskState.ACCEPTED.name,  # pylint: disable=no-member
                )
                store_pending_message(
                    response_type       = PendingResponse.ResponseType.SubtaskResultsSettled,
                    client_public_key   = subtask.provider.public_key_bytes,
                    queue               = PendingResponse.Queue.Receive,
                    subtask             = subtask,
                )
                store_pending_message(
                    response_type       = PendingResponse.ResponseType.SubtaskResultsSettled,
                    client_public_key   = subtask.requestor.public_key_bytes,
                    queue               = PendingResponse.Queue.ReceiveOutOfBand,
                    subtask             = subtask,
                )
            assert subtask.state is not Subtask.SubtaskState.ADDITIONAL_VERIFICATION.name  # pylint: disable=no-member

        logging.log_changes_in_subtask_states(
            b64encode(client_public_key),
            clients_subtask_list.count(),
        )
    else:
        logging.log_no_changes_in_subtask_states(
            b64encode(client_public_key)
        )


def update_subtask_state(
    subtask,
    state,
):
    logging.log_change_subtask_state_name(
        subtask.state,
        state,
    )
    subtask.state    = state
    subtask.next_deadline = None
    subtask.full_clean()
    subtask.save()


def store_pending_message(
    response_type       = None,
    client_public_key   = None,
    queue               = None,
    subtask             = None,
    payment_message     = None,
):
    client          = Client.objects.get_or_create_full_clean(client_public_key)
    receive_queue   = PendingResponse(
        response_type   = response_type.name,
        client          = client,
        queue           = queue.name,
        subtask         = subtask,
    )
    receive_queue.full_clean()
    receive_queue.save()
    if payment_message is not None:
        payment_committed_message = PaymentInfo(
            payment_ts                  = datetime.datetime.fromtimestamp(payment_message.payment_ts, timezone.utc),
            task_owner_key_bytes        = decode_key(payment_message.task_owner_key),
            provider_eth_account_bytes  = payment_message.provider_eth_account,
            amount_paid                 = payment_message.amount_paid,
            recipient_type              = payment_message.recipient_type.name,  # pylint: disable=no-member
            amount_pending              = payment_message.amount_pending,
            pending_response            = receive_queue
        )
        payment_committed_message.full_clean()
        payment_committed_message.save()
        subtask_id = None
    else:
        subtask_id = subtask.subtask_id

    logging.log_new_pending_response(
        response_type.name,
        queue.name,
        subtask_id,
        client.public_key,
    )


def handle_messages_from_database(
    client_public_key:  bytes                   = None,
    response_type:      PendingResponse.Queue   = None,
):
    assert client_public_key    not in ['', None]

    pending_response = PendingResponse.objects.filter(
        client__public_key = b64encode(client_public_key),
        queue              = response_type.name,
        delivered          = False,
    ).order_by('created_at').first()

    if pending_response is None:
        return None

    assert pending_response.response_type_enum in set(PendingResponse.ResponseType)

    if pending_response.response_type == PendingResponse.ResponseType.ForceReportComputedTask.name:  # pylint: disable=no-member
        report_computed_task = deserialize_message(pending_response.subtask.report_computed_task.data.tobytes())
        response_to_client = message.concents.ForceReportComputedTask(
            report_computed_task = report_computed_task
        )
        mark_message_as_delivered_and_log(pending_response, response_to_client)
        return response_to_client

    elif pending_response.response_type == PendingResponse.ResponseType.ForceReportComputedTaskResponse.name:  # pylint: disable=no-member
        if pending_response.subtask.ack_report_computed_task is not None:
            ack_report_computed_task = deserialize_message(pending_response.subtask.ack_report_computed_task.data.tobytes())
            response_to_client = message.concents.ForceReportComputedTaskResponse(
                ack_report_computed_task = ack_report_computed_task,
            )
            mark_message_as_delivered_and_log(pending_response, response_to_client)
            return response_to_client

        elif pending_response.subtask.reject_report_computed_task is not None:
            reject_report_computed_task = deserialize_message(pending_response.subtask.reject_report_computed_task.data.tobytes())
            response_to_client          = message.concents.ForceReportComputedTaskResponse(
                reject_report_computed_task = reject_report_computed_task,
            )
            if reject_report_computed_task.reason == message.concents.RejectReportComputedTask.REASON.TaskTimeLimitExceeded:
                ack_report_computed_task = message.concents.AckReportComputedTask(
                    task_to_compute = deserialize_message(pending_response.subtask.task_to_compute.data.tobytes()),
                    subtask_id      = pending_response.subtask.subtask_id,
                )
                response_to_client.ack_report_computed_task = ack_report_computed_task
            mark_message_as_delivered_and_log(pending_response, response_to_client)
            return response_to_client
        else:
            response_to_client = message.concents.ForceReportComputedTaskResponse(
                ack_report_computed_task = message.concents.AckReportComputedTask(
                    task_to_compute = deserialize_message(pending_response.subtask.task_to_compute.data.tobytes()),
                    subtask_id      = pending_response.subtask.subtask_id,
                ),
            )
            mark_message_as_delivered_and_log(pending_response, response_to_client)
            return response_to_client

    elif pending_response.response_type == PendingResponse.ResponseType.VerdictReportComputedTask.name:  # pylint: disable=no-member
        ack_report_computed_task = message.concents.AckReportComputedTask(
            task_to_compute = deserialize_message(pending_response.subtask.task_to_compute.data.tobytes()),
            subtask_id      = pending_response.subtask.subtask_id,
        )
        report_computed_task     = deserialize_message(pending_response.subtask.report_computed_task.data.tobytes())
        response_to_client = message.concents.VerdictReportComputedTask(
            ack_report_computed_task    = ack_report_computed_task,
            force_report_computed_task  = message.concents.ForceReportComputedTask(
                report_computed_task = report_computed_task,
            ),
        )
        mark_message_as_delivered_and_log(pending_response, response_to_client)
        return response_to_client

    elif pending_response.response_type == PendingResponse.ResponseType.ForceGetTaskResultRejected.name:  # pylint: disable=no-member
        report_computed_task = deserialize_message(pending_response.subtask.report_computed_task.data.tobytes())
        response_to_client = message.concents.ForceGetTaskResultRejected(
            force_get_task_result = message.concents.ForceGetTaskResult(
                report_computed_task = report_computed_task,
            )
        )
        mark_message_as_delivered_and_log(pending_response, response_to_client)
        return response_to_client

    elif pending_response.response_type == PendingResponse.ResponseType.ForceGetTaskResultFailed.name:  # pylint: disable=no-member
        task_to_compute = deserialize_message(pending_response.subtask.task_to_compute.data.tobytes())
        response_to_client = message.concents.ForceGetTaskResultFailed(
            task_to_compute = task_to_compute,
        )
        mark_message_as_delivered_and_log(pending_response, response_to_client)
        return response_to_client

    elif pending_response.response_type == PendingResponse.ResponseType.ForceGetTaskResultUpload.name:  # pylint: disable=no-member
        report_computed_task    = deserialize_message(pending_response.subtask.report_computed_task.data.tobytes())
        file_transfer_token     = create_file_transfer_token(
            report_computed_task,
            client_public_key,
            'upload',
        )

        response_to_client = message.concents.ForceGetTaskResultUpload(
            file_transfer_token     = file_transfer_token,
            force_get_task_result   = message.concents.ForceGetTaskResult(
                report_computed_task = report_computed_task,
            )
        )
        mark_message_as_delivered_and_log(pending_response, response_to_client)
        return response_to_client

    elif pending_response.response_type == PendingResponse.ResponseType.ForceGetTaskResultDownload.name:  # pylint: disable=no-member
        report_computed_task    = deserialize_message(pending_response.subtask.report_computed_task.data.tobytes())
        file_transfer_token     = create_file_transfer_token(
            report_computed_task,
            client_public_key,
            'download',
        )

        response_to_client = message.concents.ForceGetTaskResultDownload(
            file_transfer_token     = file_transfer_token,
            force_get_task_result   = message.concents.ForceGetTaskResult(
                report_computed_task = report_computed_task,
            )
        )
        mark_message_as_delivered_and_log(pending_response, response_to_client)
        return response_to_client

    elif pending_response.response_type == PendingResponse.ResponseType.ForceSubtaskResults.name:  # pylint: disable=no-member
        ack_report_computed_task = deserialize_message(pending_response.subtask.ack_report_computed_task.data.tobytes())
        response_to_client = message.concents.ForceSubtaskResults(
            ack_report_computed_task = ack_report_computed_task
        )
        mark_message_as_delivered_and_log(pending_response, response_to_client)
        return response_to_client

    elif pending_response.response_type == PendingResponse.ResponseType.SubtaskResultsSettled.name:  # pylint: disable=no-member
        task_to_compute = deserialize_message(pending_response.subtask.task_to_compute.data.tobytes())
        response_to_client = message.concents.SubtaskResultsSettled(
            task_to_compute = task_to_compute,
        )
        mark_message_as_delivered_and_log(pending_response, response_to_client)
        return response_to_client

    elif pending_response.response_type == PendingResponse.ResponseType.ForceSubtaskResultsResponse.name:  # pylint: disable=no-member
        subtask_results_accepted = deserialize_message(pending_response.subtask.subtask_results_accepted.data.tobytes())
        response_to_client = message.concents.ForceSubtaskResultsResponse(
            subtask_results_accepted = subtask_results_accepted,
        )
        mark_message_as_delivered_and_log(pending_response, response_to_client)
        return response_to_client

    elif pending_response.response_type == PendingResponse.ResponseType.SubtaskResultsRejected.name:  # pylint: disable=no-member
        subtask_results_rejected = deserialize_message(pending_response.subtask.subtask_results_rejected.data.tobytes())
        response_to_client = message.concents.ForceSubtaskResultsResponse(
            subtask_results_rejected = subtask_results_rejected,
        )
        mark_message_as_delivered_and_log(pending_response, response_to_client)
        return response_to_client

    elif pending_response.response_type == PendingResponse.ResponseType.ForcePaymentCommitted.name:  # pylint: disable=no-member
        payment_message = pending_response.payments.filter(
            pending_response__pk = pending_response.pk
        ).order_by('id').last()

        response_to_client = message.concents.ForcePaymentCommitted(
            payment_ts              = datetime.datetime.timestamp(payment_message.payment_ts),
            task_owner_key          = payment_message.task_owner_key,
            provider_eth_account    = payment_message.provider_eth_account,
            amount_paid             = payment_message.amount_paid,
            amount_pending          = payment_message.amount_pending,
        )
        if payment_message.recipient_type == PaymentInfo.RecipientType.Requestor.name:  # pylint: disable=no-member
            response_to_client.recipient_type = message.concents.ForcePaymentCommitted.Actor.Requestor
        elif payment_message.recipient_type == PaymentInfo.RecipientType.Provider.name:  # pylint: disable=no-member
            response_to_client.recipient_type = message.concents.ForcePaymentCommitted.Actor.Provider
        else:
            return None
        mark_message_as_delivered_and_log(pending_response, response_to_client)
        return response_to_client

    else:
        return None


def mark_message_as_delivered_and_log(undelivered_message, log_message):
    undelivered_message.delivered = True
    undelivered_message.full_clean()
    undelivered_message.save()

    logging.log_receive_message_from_database(
        log_message,
        undelivered_message.client.public_key,
        undelivered_message.response_type,
        undelivered_message.queue
    )


def update_subtask(
    subtask:                        Subtask,
    state:                          Subtask.SubtaskState,
    next_deadline:                  int                                  = None,
    set_next_deadline:              bool                                 = False,
    task_to_compute:                message.TaskToCompute                = None,
    report_computed_task:           message.ReportComputedTask           = None,
    ack_report_computed_task:       message.AckReportComputedTask        = None,
    reject_report_computed_task:    message.RejectReportComputedTask     = None,
    subtask_results_accepted:       message.tasks.SubtaskResultsAccepted = None,
    subtask_results_rejected:       message.tasks.SubtaskResultsRejected = None,
):
    """
    Validates and updates subtask and its data.
    Stores related messages in StoredMessage table and adds relation to newly created subtask.
    """
    assert isinstance(subtask, Subtask)
    assert state in Subtask.SubtaskState
    assert (state in Subtask.ACTIVE_STATES)  == (next_deadline is not None)
    assert (state in Subtask.PASSIVE_STATES) == (next_deadline is None)

    set_subtask_messages(
        subtask,
        task_to_compute             = task_to_compute,
        report_computed_task        = report_computed_task,
        ack_report_computed_task    = ack_report_computed_task,
        reject_report_computed_task = reject_report_computed_task,
        subtask_results_accepted    = subtask_results_accepted,
        subtask_results_rejected    = subtask_results_rejected,
    )

    if set_next_deadline:
        subtask.next_deadline = next_deadline
    subtask.state = state.name
    subtask.full_clean()
    subtask.save()

    logging.log_subtask_updated(
        subtask.task_id,
        subtask.subtask_id,
        state.name,
        subtask.provider.public_key,
        subtask.requestor.public_key,
        next_deadline,
    )

    return subtask


def set_subtask_messages(
    subtask:                        Subtask,
    task_to_compute:                message.TaskToCompute                       = None,
    report_computed_task:           message.ReportComputedTask                  = None,
    ack_report_computed_task:       message.concents.AckReportComputedTask      = None,
    reject_report_computed_task:    message.concents.RejectReportComputedTask   = None,
    subtask_results_accepted:       message.tasks.SubtaskResultsAccepted        = None,
    subtask_results_rejected:       message.tasks.SubtaskResultsRejected        = None,
):
    """
    Stores and adds relation of passed StoredMessages to given subtask.
    If the message name is not present in kwargs, it doesn't do anything with it.
    """
    subtask_messages_to_set = {
        'task_to_compute':              task_to_compute,
        'report_computed_task':         report_computed_task,
        'ack_report_computed_task':     ack_report_computed_task,
        'reject_report_computed_task':  reject_report_computed_task,
        'subtask_results_accepted':     subtask_results_accepted,
        'subtask_results_rejected':     subtask_results_rejected,
    }

    assert set(subtask_messages_to_set).issubset({f.name for f in Subtask._meta.get_fields()})
    assert set(subtask_messages_to_set).issubset(set(Subtask.MESSAGE_FOR_FIELD))

    for message_name, message_type in Subtask.MESSAGE_FOR_FIELD.items():
        message_to_store = subtask_messages_to_set.get(message_name)
        if message_to_store is not None and getattr(subtask, message_name) is None:
            assert isinstance(message_to_store, message_type)
            stored_message = store_message(
                message_to_store,
                subtask.task_id,
                subtask.subtask_id,
            )
            setattr(subtask, message_name, stored_message)
            logging.log_stored_message_added_to_subtask(
                subtask.subtask_id,
                subtask.state,
                message_type.TYPE,
            )


def store_or_update_subtask(
    task_id:                        str,
    subtask_id:                     str,
    provider_public_key:            bytes,
    requestor_public_key:           bytes,
    state:                          Subtask.SubtaskState,
    next_deadline:                  int                                  = None,
    set_next_deadline:              bool                                 = False,
    task_to_compute:                message.TaskToCompute                = None,
    report_computed_task:           message.ReportComputedTask           = None,
    ack_report_computed_task:       message.AckReportComputedTask        = None,
    reject_report_computed_task:    message.RejectReportComputedTask     = None,
    subtask_results_accepted:       message.tasks.SubtaskResultsAccepted = None,
    subtask_results_rejected:       message.tasks.SubtaskResultsRejected = None,
):
    try:
        subtask = Subtask.objects.get(
            subtask_id = subtask_id,
        )
    except Subtask.DoesNotExist:
        subtask = None

    if subtask is not None:
        subtask = update_subtask(
            subtask                         = subtask,
            state                           = state,
            next_deadline                   = next_deadline,
            set_next_deadline               = set_next_deadline,
            task_to_compute                 = task_to_compute,
            report_computed_task            = report_computed_task,
            ack_report_computed_task        = ack_report_computed_task,
            reject_report_computed_task     = reject_report_computed_task,
            subtask_results_accepted        = subtask_results_accepted,
            subtask_results_rejected        = subtask_results_rejected,
        )
    else:
        subtask = store_subtask(
            task_id                         = task_id,
            subtask_id                      = subtask_id,
            provider_public_key             = provider_public_key,
            requestor_public_key            = requestor_public_key,
            state                           = state,
            next_deadline                   = next_deadline,
            task_to_compute                 = task_to_compute,
            report_computed_task            = report_computed_task,
            ack_report_computed_task        = ack_report_computed_task,
            reject_report_computed_task     = reject_report_computed_task,
            subtask_results_accepted        = subtask_results_accepted,
            subtask_results_rejected        = subtask_results_rejected,
        )
    return subtask


def store_message(
    golem_message:          message.base.Message,
    task_id:                str,
    subtask_id:             str,
):
    assert golem_message.TYPE in message.registered_message_types

    message_timestamp = datetime.datetime.now(timezone.utc)
    stored_message = StoredMessage(
        type        = golem_message.TYPE,
        timestamp   = message_timestamp,
        data        = copy.copy(golem_message).serialize(),
        task_id     = task_id,
        subtask_id  = subtask_id,
    )
    stored_message.full_clean()
    stored_message.save()

    return stored_message


def create_file_transfer_token(
    report_computed_task:   message.tasks.ReportComputedTask,
    client_public_key:      bytes,
    operation:              str,
) -> message.concents.FileTransferToken:
    """
    Function to create FileTransferToken from ReportComputedTask message
    """
    current_time    = get_current_utc_timestamp()
    task_id         = report_computed_task.task_to_compute.compute_task_def['task_id']
    subtask_id      = report_computed_task.task_to_compute.compute_task_def['subtask_id']
    file_path       = '{}/{}/result'.format(subtask_id, task_id)

    file_transfer_token = message.concents.FileTransferToken(
        token_expiration_deadline       = current_time + settings.TOKEN_EXPIRATION_TIME,
        storage_cluster_address         = settings.STORAGE_CLUSTER_ADDRESS,
        authorized_client_public_key    = b64encode(client_public_key),
        operation                       = operation,
    )
    file_transfer_token.files = [message.concents.FileTransferToken.FileInfo()]
    file_transfer_token.files[0]['path']      = file_path
    file_transfer_token.files[0]['checksum']  = report_computed_task.package_hash
    file_transfer_token.files[0]['size']      = report_computed_task.size

    return file_transfer_token


def request_upload_status(file_transfer_token_from_database: message.concents.FileTransferToken) -> bool:
    slash = '/'
    assert len(file_transfer_token_from_database.files) == 1
    assert not file_transfer_token_from_database.files[0]['path'].startswith(slash)
    assert settings.STORAGE_CLUSTER_ADDRESS.endswith(slash)

    current_time = get_current_utc_timestamp()
    file_transfer_token = message.concents.FileTransferToken(
        token_expiration_deadline       = current_time + settings.TOKEN_EXPIRATION_TIME,
        storage_cluster_address         = settings.STORAGE_CLUSTER_ADDRESS,
        authorized_client_public_key    = settings.CONCENT_PUBLIC_KEY,
        operation                       = 'upload',
    )

    assert file_transfer_token.timestamp <= file_transfer_token.token_expiration_deadline  # pylint: disable=no-member

    file_transfer_token.files                 = [message.concents.FileTransferToken.FileInfo()]
    file_transfer_token.files[0]['path']      = file_transfer_token_from_database.files[0]['path']
    file_transfer_token.files[0]['checksum']  = file_transfer_token_from_database.files[0]['checksum']
    file_transfer_token.files[0]['size']      = file_transfer_token_from_database.files[0]['size']

    dumped_file_transfer_token = shortcuts.dump(file_transfer_token, settings.CONCENT_PRIVATE_KEY, settings.CONCENT_PUBLIC_KEY)
    headers = {
        'Authorization':                'Golem ' + b64encode(dumped_file_transfer_token).decode(),
        'Concent-Client-Public-Key':    b64encode(settings.CONCENT_PUBLIC_KEY).decode(),
    }
    request_http_address = settings.STORAGE_CLUSTER_ADDRESS + CLUSTER_DOWNLOAD_PATH + file_transfer_token.files[0]['path']

    cluster_storage_response = requests.head(
        request_http_address,
        headers = headers
    )
    if cluster_storage_response.status_code == 200:
        return True
    elif cluster_storage_response.status_code in [401, 404]:
        return False
    else:
        raise exceptions.UnexpectedResponse()


def decode_client_public_key(request):
    assert 'HTTP_CONCENT_CLIENT_PUBLIC_KEY' in request.META
    return decode_key(request.META['HTTP_CONCENT_CLIENT_PUBLIC_KEY'])


def decode_other_party_public_key(request):
    if 'HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY' not in request.META:
        raise Http400('Missing Concent-Other-Party-Public-Key HTTP when expected.')
    try:
        return decode_key(request.META['HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY'])
    except binascii.Error:
        raise Http400('The value in the Concent-Other-Party-Public-Key HTTP is not a valid base64-encoded value.')
