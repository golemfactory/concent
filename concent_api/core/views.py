from base64                         import b64encode
import binascii
import datetime

import requests
from django.conf                    import settings
from django.http                    import HttpResponse
from django.http                    import JsonResponse
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
from .constants                     import MESSAGE_TASK_ID_MAX_LENGTH
from .models                        import StoredMessage
from .models                        import MessageAuth
from .models                        import ReceiveOutOfBandStatus
from .models                        import ReceiveStatus


@api_view
@require_POST
def send(request, client_message):
    logging.log_message_received(
        client_message,
        request.META['HTTP_CONCENT_CLIENT_PUBLIC_KEY'],
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
    current_time      = get_current_utc_timestamp()
    client_public_key = decode_client_public_key(request)
    last_undelivered_message_status = ReceiveStatus.objects.filter_public_key(
        request.META['HTTP_CONCENT_CLIENT_PUBLIC_KEY']
    ).filter(delivered = False).order_by('timestamp').last()
    if last_undelivered_message_status is None:
        last_delivered_message_status = ReceiveStatus.objects.filter_public_key(
            request.META['HTTP_CONCENT_CLIENT_PUBLIC_KEY']
        ).order_by('timestamp').last()
        if last_delivered_message_status is None:
            return None

        decoded_message_data = deserialize_message(last_delivered_message_status.message.data.tobytes())
        if (
            last_delivered_message_status.message.type                           == message.ForceReportComputedTask.TYPE and
            last_delivered_message_status.message.auth.provider_public_key_bytes == client_public_key and
            current_time >= decoded_message_data.report_computed_task.task_to_compute.compute_task_def['deadline'] + settings.CONCENT_MESSAGING_TIME
        ):
            return handle_receive_delivered_force_report_computed_task(request, last_delivered_message_status)

        if (
            last_delivered_message_status.message.type                            == message.concents.ForceGetTaskResultUpload.TYPE and
            last_delivered_message_status.message.auth.requestor_public_key_bytes == client_public_key
        ):
            file_uploaded        = get_file_status(decoded_message_data.file_transfer_token)
            if file_uploaded:
                return handle_receive_force_get_task_result_upload_for_requestor(
                    request,
                    decoded_message_data,
                    last_delivered_message_status,
                )
            else:
                return handle_receive_force_get_task_result_failed(
                    request,
                    decoded_message_data,
                    last_delivered_message_status,
                )
        acceptance_deadline = settings.SUBTASK_VERIFICATION_TIME + settings.FORCE_ACCEPTANCE_TIME + settings.CONCENT_MESSAGING_TIME
        if (
            last_delivered_message_status.message.type                           == message.concents.ForceSubtaskResults.TYPE and
            last_delivered_message_status.message.auth.provider_public_key_bytes == client_public_key and
            current_time > decoded_message_data.ack_report_computed_task.timestamp + acceptance_deadline
        ):
            base.make_forced_payment('provider', 'requestor')
            return handle_receive_force_subtask_results_settled(
                decoded_message_data,
                last_delivered_message_status.message.auth.provider_public_key_bytes,
                last_delivered_message_status.message.auth.requestor_public_key_bytes,
                ReceiveStatus
            )

        return None

    decoded_message_data = deserialize_message(last_undelivered_message_status.message.data.tobytes())

    assert last_undelivered_message_status.message.type == decoded_message_data.TYPE
    if last_undelivered_message_status.message.type == message.ForceReportComputedTask.TYPE:
        if client_public_key != last_undelivered_message_status.message.auth.requestor_public_key_bytes:
            return None
        if decoded_message_data.report_computed_task.task_to_compute.compute_task_def['deadline'] + settings.CONCENT_MESSAGING_TIME < current_time:
            set_message_as_delivered(last_undelivered_message_status)
            logging.log_message_delivered(
                decoded_message_data,
                client_public_key,
            )
            return handle_receive_ack_from_force_report_computed_task(
                request,
                decoded_message_data,
                last_undelivered_message_status
            )
        logging.log_timeout(
            decoded_message_data,
            request.META['HTTP_CONCENT_CLIENT_PUBLIC_KEY'],
            decoded_message_data.report_computed_task.task_to_compute.compute_task_def['deadline'] + settings.CONCENT_MESSAGING_TIME,
        )

    if isinstance(decoded_message_data, message.ForceReportComputedTask):
        if client_public_key != last_undelivered_message_status.message.auth.requestor_public_key_bytes:
            return None
        set_message_as_delivered(last_undelivered_message_status)
        logging.log_message_delivered(
            decoded_message_data,
            client_public_key,
        )
        return handle_receive_force_report_computed_task(
            request,
            decoded_message_data,
            last_undelivered_message_status
        )

    if isinstance(decoded_message_data, message.AckReportComputedTask):
        if (
            current_time <= decoded_message_data.task_to_compute.compute_task_def['deadline'] + 2 * settings.CONCENT_MESSAGING_TIME and
            client_public_key == last_undelivered_message_status.message.auth.provider_public_key_bytes
        ):
            set_message_as_delivered(last_undelivered_message_status)
            logging.log_message_delivered(
                decoded_message_data,
                client_public_key,
            )
            return handle_receive_ack_or_reject_report_computed_task(
                request,
                decoded_message_data,
                last_undelivered_message_status,
            )
        elif current_time > decoded_message_data.task_to_compute.compute_task_def['deadline'] + 2 * settings.CONCENT_MESSAGING_TIME:
            logging.log_timeout(
                decoded_message_data,
                request.META['HTTP_CONCENT_CLIENT_PUBLIC_KEY'],
                decoded_message_data.task_to_compute.compute_task_def['deadline'] + settings.CONCENT_MESSAGING_TIME,
            )
        return None

    if isinstance(decoded_message_data, message.concents.ForceGetTaskResult):
        if client_public_key != last_undelivered_message_status.message.auth.provider_public_key_bytes:
            return None
        set_message_as_delivered(last_undelivered_message_status)
        logging.log_message_delivered(
            decoded_message_data,
            client_public_key,
        )
        return handle_receive_force_get_task_result_upload_for_provider(
            request,
            decoded_message_data,
            last_undelivered_message_status,
        )

    if isinstance(decoded_message_data, message.concents.ForceSubtaskResults):
        if client_public_key != last_undelivered_message_status.message.auth.requestor_public_key_bytes:
            return None
        set_message_as_delivered(last_undelivered_message_status)
        logging.log_message_delivered(
            decoded_message_data,
            client_public_key,
        )
        if current_time < decoded_message_data.timestamp + settings.CONCENT_MESSAGING_TIME:
            return handle_receive_force_subtask_results(
                request,
                decoded_message_data,
                last_undelivered_message_status,
            )
        logging.log_timeout(
            decoded_message_data,
            request.META['HTTP_CONCENT_CLIENT_PUBLIC_KEY'],
            decoded_message_data.timestamp + settings.CONCENT_MESSAGING_TIME,
        )
        return handle_receive_force_subtask_results(
            request,
            decoded_message_data,
            last_undelivered_message_status,
        )

    if isinstance(decoded_message_data, message.concents.ForceSubtaskResultsResponse):
        if client_public_key != last_undelivered_message_status.message.auth.provider_public_key_bytes:
            return None
        set_message_as_delivered(last_undelivered_message_status)
        logging.log_message_delivered(
            decoded_message_data,
            client_public_key,
        )
        return handle_receive_force_subtask_results_response(
            request,
            decoded_message_data,
            last_undelivered_message_status
        )

    assert isinstance(decoded_message_data, message.RejectReportComputedTask), (
        "At this point ReceiveStatus must contain ForceReportComputedTask because AckReportComputedTask and RejectReportComputedTask have already been handled"
    )

    if client_public_key != last_undelivered_message_status.message.auth.provider_public_key_bytes:
        return None

    force_report_computed_task = StoredMessage.objects.filter(
        type    = message.ForceReportComputedTask.TYPE,
        task_id = decoded_message_data.cannot_compute_task.task_to_compute.compute_task_def['task_id']
    ).order_by('timestamp').last()

    decoded_message_from_database = deserialize_message(force_report_computed_task.data.tobytes())

    if current_time <= decoded_message_from_database.report_computed_task.task_to_compute.compute_task_def['deadline'] + 2 * settings.CONCENT_MESSAGING_TIME:
        if decoded_message_data.reason is not None and decoded_message_data.reason == message.RejectReportComputedTask.REASON.TaskTimeLimitExceeded:
            return handle_receive_ack_from_force_report_computed_task(
                request,
                decoded_message_from_database,
                last_undelivered_message_status
            )
        return handle_receive_ack_or_reject_report_computed_task(
            request,
            decoded_message_data,
            last_undelivered_message_status,
        )

    logging.log_timeout(
        decoded_message_data,
        request.META['HTTP_CONCENT_CLIENT_PUBLIC_KEY'],
        decoded_message_from_database.task_to_compute.compute_task_def['deadline'] + 2 * settings.CONCENT_MESSAGING_TIME,
    )

    return None


@api_view
@require_POST
def receive_out_of_band(request, _message):
    undelivered_receive_out_of_band_statuses    = ReceiveOutOfBandStatus.objects.filter(delivered = False)
    last_undelivered_receive_out_of_band_status = undelivered_receive_out_of_band_statuses.order_by('timestamp').last()
    last_undelivered_receive_status             = StoredMessage.objects.filter(
        auth__requestor_public_key = request.META['HTTP_CONCENT_CLIENT_PUBLIC_KEY'],
    ).order_by('timestamp').last()
    current_time = get_current_utc_timestamp()
    if last_undelivered_receive_out_of_band_status is None:
        if last_undelivered_receive_status is None:
            return None

        if last_undelivered_receive_status.timestamp.timestamp() > current_time:
            return None

        if last_undelivered_receive_status.type == message.ForceReportComputedTask.TYPE:
            return handle_receive_out_of_band_force_report_computed_task(request, last_undelivered_receive_status)

        if last_undelivered_receive_status.type == message.concents.ForceReportComputedTaskResponse.TYPE:
            decoded_message = deserialize_message(last_undelivered_receive_status.data.tobytes())
            if isinstance(decoded_message.ack_report_computed_task, message.concents.AckReportComputedTask):
                return handle_receive_out_of_band_ack_report_computed_task(request, last_undelivered_receive_status)

            elif isinstance(decoded_message.reject_report_computed_task, message.concents.RejectReportComputedTask):
                return handle_receive_out_of_band_reject_report_computed_task(request, last_undelivered_receive_status)

        if last_undelivered_receive_status.type == message.concents.ForcePaymentCommitted.TYPE:
            return handle_receive_out_of_band_force_payment_commited(request, last_undelivered_receive_status)

        last_receive_status = ReceiveStatus.objects.filter(
            message__auth__requestor_public_key = request.META['HTTP_CONCENT_CLIENT_PUBLIC_KEY'],
            message__type = last_undelivered_receive_status.type
        ).order_by('timestamp')

        if last_receive_status.exists() and last_undelivered_receive_status.type == message.concents.SubtaskResultsSettled.TYPE:
            last_undelivered_receive_status = StoredMessage.objects.filter(
                auth__requestor_public_key = request.META['HTTP_CONCENT_CLIENT_PUBLIC_KEY'],
            ).exclude(id = last_undelivered_receive_status.id).order_by('timestamp').last()
            if last_undelivered_receive_status is None:
                return None

        if last_undelivered_receive_status.type == message.concents.ForceSubtaskResults.TYPE:
            acceptance_deadline = settings.SUBTASK_VERIFICATION_TIME + settings.FORCE_ACCEPTANCE_TIME + settings.CONCENT_MESSAGING_TIME
            decoded_message_data = deserialize_message(last_undelivered_receive_status.data.tobytes())

            if current_time > decoded_message_data.ack_report_computed_task.timestamp + acceptance_deadline:

                return handle_receive_force_subtask_results_settled(
                    decoded_message_data,
                    last_undelivered_receive_status.auth.provider_public_key_bytes,
                    last_undelivered_receive_status.auth.requestor_public_key_bytes,
                    ReceiveOutOfBandStatus
                )
        return None

    return None


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
    client_message.sig = None
    store_message_and_message_status(
        client_message.TYPE,
        client_message.report_computed_task.task_to_compute.compute_task_def['task_id'],
        client_message.serialize(),
        provider_public_key  = client_public_key,
        requestor_public_key = other_party_public_key,
        status               = ReceiveStatus
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

        client_message.sig = None
        store_message_and_message_status(
            client_message.TYPE,
            client_message.task_to_compute.compute_task_def['task_id'],
            client_message.serialize(),
            provider_public_key  = force_task_to_compute.last().auth.provider_public_key_bytes,
            requestor_public_key = client_public_key,
            status               = ReceiveStatus,
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
        client_message.sig = None
        store_message_and_message_status(
            client_message.TYPE,
            force_report_computed_task.report_computed_task.task_to_compute.compute_task_def['task_id'],
            client_message.serialize(),
            provider_public_key  = force_report_computed_task_from_database.last().auth.provider_public_key_bytes,
            requestor_public_key = client_public_key,
            status               = ReceiveStatus
        )
        logging.log_message_added_to_queue(
            client_message,
            client_public_key,
        )

        return HttpResponse("", status = 202)

    if current_time <= force_report_computed_task.report_computed_task.task_to_compute.compute_task_def['deadline'] + settings.CONCENT_MESSAGING_TIME:
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

        client_message.sig = None
        store_message_and_message_status(
            client_message.TYPE,
            force_report_computed_task.report_computed_task.task_to_compute.compute_task_def['task_id'],
            client_message.serialize(),
            provider_public_key  = force_report_computed_task_from_database.last().auth.provider_public_key_bytes,
            requestor_public_key = client_public_key,
            status               = ReceiveStatus
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
        client_message.sig = None
        store_message_and_message_status(
            client_message.TYPE,
            client_message.report_computed_task.task_to_compute.compute_task_def['task_id'],
            client_message.serialize(),
            provider_public_key  = other_party_public_key,
            requestor_public_key = client_public_key,
            status               = ReceiveStatus,
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

    if not base.is_provider_account_status_positive(request):
        return message.concents.ServiceRefused(
            reason      = message.concents.ServiceRefused.REASON.TooSmallProviderDeposit,
        )

    client_message_send_too_soon = client_message.ack_report_computed_task.timestamp + settings.SUBTASK_VERIFICATION_TIME
    client_message_send_too_late = client_message.ack_report_computed_task.timestamp + settings.SUBTASK_VERIFICATION_TIME + settings.FORCE_ACCEPTANCE_TIME
    if client_message_send_too_late < current_time:
        logging.log_timeout(
            client_message,
            request.META['HTTP_CONCENT_CLIENT_PUBLIC_KEY'],
            client_message_send_too_late,
        )
        return message.concents.ForceSubtaskResultsRejected(
            reason = message.concents.ForceSubtaskResultsRejected.REASON.RequestTooLate,
        )
    elif current_time < client_message_send_too_soon:
        logging.log_timeout(
            client_message,
            request.META['HTTP_CONCENT_CLIENT_PUBLIC_KEY'],
            client_message_send_too_soon,
        )
        return message.concents.ForceSubtaskResultsRejected(
            reason = message.concents.ForceSubtaskResultsRejected.REASON.RequestPremature,
        )
    else:
        client_message.sig = None
        store_message_and_message_status(
            client_message.TYPE,
            client_message.ack_report_computed_task.task_to_compute.compute_task_def['task_id'],
            client_message.serialize(),
            status               = ReceiveStatus,
            provider_public_key  = client_public_key,
            requestor_public_key = other_party_public_key,
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
        client_message_task_id = client_message.subtask_results_accepted.task_to_compute.compute_task_def['task_id']
    else:
        client_message_task_id = client_message.subtask_results_rejected.report_computed_task.task_to_compute.compute_task_def['task_id']

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

    client_message.sig = None
    store_message_and_message_status(
        client_message.TYPE,
        client_message_task_id,
        client_message.serialize(),
        status               = ReceiveStatus,
        provider_public_key  = force_subtask_results.last().auth.provider_public_key_bytes,
        requestor_public_key = client_public_key,
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
            amount_paid             = 10.99,
            amount_pending          = 0.01,
            recipient_type          = message.concents.ForcePaymentCommitted.Actor.Provider,
        )

        store_message_and_message_status(
            provider_force_payment_commited.TYPE,
            None,
            provider_force_payment_commited.serialize(),
            provider_public_key     = client_public_key,
            requestor_public_key    = other_party_public_key,
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
        force_report_computed_task_response.serialize(),
        provider_public_key  = client_public_key,
        requestor_public_key = delivered_message.message.auth.requestor_public_key_bytes,
    )
    force_report_computed_task_response.sig = None
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
        force_report_computed_task_response.serialize(),
        status                  = ReceiveStatus,
        delivered               = True,
        provider_public_key     = client_public_key,
        requestor_public_key    = undelivered_message.message.auth.requestor_public_key_bytes,
    )
    force_report_computed_task_response.sig = None
    return force_report_computed_task_response


def handle_receive_force_report_computed_task(request, decoded_message, undelivered_message):
    force_report_computed_task = message.concents.ForceReportComputedTask(
        report_computed_task = decoded_message.report_computed_task
    )
    client_public_key = decode_client_public_key(request)
    store_message_and_message_status(
        force_report_computed_task.TYPE,
        force_report_computed_task.report_computed_task.task_to_compute.compute_task_def['task_id'],
        force_report_computed_task.serialize(),
        status                  = ReceiveStatus,
        delivered               = True,
        provider_public_key     = undelivered_message.message.auth.provider_public_key_bytes,
        requestor_public_key    = client_public_key,
    )
    force_report_computed_task.sig = None
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
        subtask_results_settled.serialize(),
        provider_public_key  = provider_public_key,
        requestor_public_key = requestor_public_key,
        status               = message_model,
        delivered            = True,
    )
    subtask_results_settled.sig = None
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
        force_report_computed_task_response.serialize(),
        status                  = ReceiveStatus,
        delivered               = True,
        provider_public_key     = client_public_key,
        requestor_public_key    = undelivered_message.message.auth.requestor_public_key_bytes,
    )
    force_report_computed_task_response.sig = None
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
    file_transfer_token.files[0]['checksum']  = decoded_message.report_computed_task.checksum
    file_transfer_token.files[0]['size']      = decoded_message.report_computed_task.size

    force_get_task_result_upload = message.concents.ForceGetTaskResultUpload(
        force_get_task_result   = decoded_message,
        file_transfer_token     = file_transfer_token,
    )

    store_message_and_message_status(
        force_get_task_result_upload.TYPE,
        decoded_message.report_computed_task.task_to_compute.compute_task_def['task_id'],
        force_get_task_result_upload.serialize(),
        provider_public_key  = client_public_key,
        requestor_public_key = previous_message_status_from_database.message.auth.requestor_public_key_bytes,
        status               = ReceiveStatus,
        delivered            = True,
    )
    force_get_task_result_upload.sig = None
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
        force_get_task_result_failed.serialize(),
        provider_public_key  = previous_message_status_from_database.message.auth.provider_public_key_bytes,
        requestor_public_key = client_public_key,
        status               = ReceiveStatus,
        delivered            = True,
    )
    force_get_task_result_failed.sig = None
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
        force_subtask_results_response.serialize(),
        status                  = ReceiveStatus,
        delivered               = True,
        provider_public_key     = client_public_key,
        requestor_public_key    = undelivered_message.message.auth.requestor_public_key_bytes,
    )
    force_subtask_results_response.sig = None
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
        force_get_task_result_upload.serialize(),
        provider_public_key  = previous_message_status_from_database.message.auth.provider_public_key_bytes,
        requestor_public_key = client_public_key,
        status               = ReceiveStatus,
        delivered            = True,
    )
    force_get_task_result_upload.sig = None
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
        requestor_force_subtask_results.serialize(),
        provider_public_key  = last_undelivered_message_status.message.auth.provider_public_key_bytes,
        requestor_public_key = client_public_key,
        status               = ReceiveStatus,
        delivered            = True,
    )
    requestor_force_subtask_results.sig = None
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
        message_verdict.serialize(),
        provider_public_key  = undelivered_message.auth.provider_public_key_bytes,
        requestor_public_key = client_public_key,
        status               = ReceiveOutOfBandStatus,
        delivered            = True
    )
    message_verdict.sig = None
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
        message_verdict.serialize(),
        provider_public_key  = undelivered_message.auth.provider_public_key_bytes,
        requestor_public_key = client_public_key,
        status               = ReceiveOutOfBandStatus,
        delivered            = True
    )
    message_verdict.sig = None
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
        message_verdict.serialize(),
        provider_public_key  = undelivered_message.auth.provider_public_key_bytes,
        requestor_public_key = client_public_key,
        status               = ReceiveOutOfBandStatus,
        delivered            = True
    )
    message_verdict.sig = None
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
        requestor_force_payment_commited.serialize(),
        status                  = ReceiveOutOfBandStatus,
        delivered               = True,
        provider_public_key     = undelivered_message.auth.provider_public_key_bytes,
        requestor_public_key    = client_public_key,
    )
    requestor_force_payment_commited.sig = None
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
    raw_golem_message:      bytes,
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
    golem_message = StoredMessage(
        type        = golem_message_type,
        timestamp   = message_timestamp,
        data        = raw_golem_message,
        task_id     = task_id
    )
    golem_message.full_clean()
    golem_message.save()

    message_auth = MessageAuth(
        message                    = golem_message,
        provider_public_key_bytes  = provider_public_key,
        requestor_public_key_bytes = requestor_public_key,
    )
    message_auth.full_clean()
    message_auth.save()

    if status is not None:
        receive_message_status  = status(
            message     = golem_message,
            timestamp   = message_timestamp,
            delivered   = delivered
        )
        receive_message_status.full_clean()
        receive_message_status.save()


def get_file_status(file_transfer_token_from_database: message.concents.FileTransferToken) -> bool:
    slash = '/'
    assert len(file_transfer_token_from_database.files) == 1
    assert not file_transfer_token_from_database.files[0]['path'].startswith(slash)
    assert settings.STORAGE_CLUSTER_ADDRESS.endswith(slash)

    current_time = get_current_utc_timestamp()
    file_transfer_token = message.concents.FileTransferToken(
        token_expiration_deadline       = current_time + settings.TOKEN_EXPIRATION_TIME,
        storage_cluster_address         = settings.STORAGE_CLUSTER_ADDRESS,
        authorized_client_public_key    = settings.CONCENT_PUBLIC_KEY,
        operation                       = 'download',
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
