import datetime

import copy
from base64                         import b64encode
from django.conf                    import settings
from django.http                    import HttpResponse
from django.utils                   import timezone
from golem_messages                 import message
from golem_messages.datastructures  import MessageHeader

from core.exceptions                import Http400
from core.models                    import Client
from core.models                    import PaymentInfo
from core.models                    import PendingResponse
from core.models                    import StoredMessage
from core.models                    import Subtask
from core.payments                  import base
from core.validation                import validate_golem_message_reject
from core.validation                import validate_golem_message_task_to_compute
from core.validation                import validate_id_value
from core.validation                import validate_report_computed_task_time_window
from core.subtask_helpers           import verify_message_subtask_results_accepted
from core.transfer_operations       import store_pending_message
from core.transfer_operations       import create_file_transfer_token
from utils                          import logging
from utils.helpers                  import decode_client_public_key
from utils.helpers                  import decode_other_party_public_key
from utils.helpers                  import deserialize_message
from utils.helpers                  import get_current_utc_timestamp
from utils.helpers                  import parse_timestamp_to_utc_datetime


def handle_send_force_report_computed_task(request, client_message):
    current_time           = get_current_utc_timestamp()
    client_public_key      = decode_client_public_key(request)
    other_party_public_key = decode_other_party_public_key(request)
    validate_golem_message_task_to_compute(client_message.report_computed_task.task_to_compute)
    validate_report_computed_task_time_window(client_message.report_computed_task)
    validate_id_value(client_message.report_computed_task.task_to_compute.compute_task_def['task_id'], 'task_id')
    validate_id_value(client_message.report_computed_task.task_to_compute.compute_task_def['subtask_id'], 'subtask_id')

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
    validate_id_value(client_message.task_to_compute.compute_task_def['task_id'], 'task_id')
    validate_id_value(client_message.task_to_compute.compute_task_def['subtask_id'], 'subtask_id')

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
    validate_id_value(client_message.cannot_compute_task.task_to_compute.compute_task_def['task_id'], 'task_id')
    validate_id_value(client_message.cannot_compute_task.task_to_compute.compute_task_def['subtask_id'], 'subtask_id')

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

    if client_message.cannot_compute_task.reason == message.CannotComputeTask.REASON.WrongCTD:
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

    deserialized_message = deserialize_message(subtask.task_to_compute.data.tobytes())

    if current_time <= deserialized_message.compute_task_def['deadline'] + settings.CONCENT_MESSAGING_TIME:
        if subtask.ack_report_computed_task_id is not None or subtask.ack_report_computed_task_id is not None:
            raise Http400("Received RejectReportComputedTask but AckReportComputedTask or another RejectReportComputedTask for this task has already been submitted.")

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
            client_message,
            request.META['HTTP_CONCENT_CLIENT_PUBLIC_KEY'],
            deserialized_message.compute_task_def['deadline'] + settings.CONCENT_MESSAGING_TIME,
        )
        raise Http400("Time to acknowledge this task is already over.")


def handle_send_force_get_task_result(request, client_message: message.concents.ForceGetTaskResult) -> message.concents:
    assert client_message.TYPE in message.registered_message_types

    current_time           = get_current_utc_timestamp()
    client_public_key      = decode_client_public_key(request)
    other_party_public_key = decode_other_party_public_key(request)
    validate_golem_message_task_to_compute(client_message.report_computed_task.task_to_compute)
    validate_id_value(client_message.report_computed_task.task_to_compute.compute_task_def['task_id'], 'task_id')
    validate_id_value(client_message.report_computed_task.task_to_compute.compute_task_def['subtask_id'], 'subtask_id')
    force_get_task_result_deadline = (
        client_message.report_computed_task.task_to_compute.compute_task_def['deadline'] +
        2 * settings.CONCENT_MESSAGING_TIME +
        settings.MAXIMUM_DOWNLOAD_TIME
    )

    if Subtask.objects.filter(
        subtask_id = client_message.report_computed_task.task_to_compute.compute_task_def['subtask_id'],
        state      = Subtask.SubtaskState.FORCING_RESULT_TRANSFER.name,  # pylint: disable=no-member
    ).exists():
        return message.concents.ServiceRefused(
            reason = message.concents.ServiceRefused.REASON.DuplicateRequest,
        )

    elif force_get_task_result_deadline < current_time:
        logging.log_timeout(
            client_message,
            request.META['HTTP_CONCENT_CLIENT_PUBLIC_KEY'],
            force_get_task_result_deadline,
        )
        return message.concents.ForceGetTaskResultRejected(
            reason    = message.concents.ForceGetTaskResultRejected.REASON.AcceptanceTimeLimitExceeded,
        )

    else:
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
    validate_id_value(client_message.ack_report_computed_task.task_to_compute.compute_task_def['task_id'], 'task_id')
    validate_id_value(client_message.ack_report_computed_task.task_to_compute.compute_task_def['subtask_id'], 'subtask_id')

    current_time           = get_current_utc_timestamp()
    client_public_key      = decode_client_public_key(request)
    other_party_public_key = decode_other_party_public_key(request)

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

    verification_deadline       = (
        client_message.ack_report_computed_task.task_to_compute.compute_task_def['deadline'] +
        settings.SUBTASK_VERIFICATION_TIME
    )
    forcing_acceptance_deadline = (
        client_message.ack_report_computed_task.task_to_compute.compute_task_def['deadline'] +
        settings.SUBTASK_VERIFICATION_TIME +
        settings.FORCE_ACCEPTANCE_TIME
    )
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
        validate_golem_message_task_to_compute(client_message.subtask_results_accepted.task_to_compute)
        client_message_subtask_id = client_message.subtask_results_accepted.task_to_compute.compute_task_def['subtask_id']
        report_computed_task      = None
        subtask_results_accepted  = client_message.subtask_results_accepted
        subtask_results_rejected  = None
        state                     = Subtask.SubtaskState.ACCEPTED
        response_type             = PendingResponse.ResponseType.ForceSubtaskResultsResponse
        provider_public_key       = client_message.subtask_results_accepted.task_to_compute.provider_public_key
        computation_deadline      = client_message.subtask_results_accepted.task_to_compute.compute_task_def['deadline']
    else:
        validate_golem_message_task_to_compute(client_message.subtask_results_rejected.report_computed_task.task_to_compute)
        client_message_subtask_id = client_message.subtask_results_rejected.report_computed_task.task_to_compute.compute_task_def['subtask_id']
        report_computed_task      = client_message.subtask_results_rejected.report_computed_task
        subtask_results_accepted  = None
        subtask_results_rejected  = client_message.subtask_results_rejected
        state                     = Subtask.SubtaskState.REJECTED
        response_type             = PendingResponse.ResponseType.SubtaskResultsRejected
        provider_public_key       = client_message.subtask_results_rejected.report_computed_task.task_to_compute.provider_public_key
        computation_deadline      = client_message.subtask_results_rejected.report_computed_task.task_to_compute.compute_task_def['deadline']

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

    acceptance_deadline = (
        computation_deadline +
        settings.SUBTASK_VERIFICATION_TIME +
        settings.FORCE_ACCEPTANCE_TIME +
        settings.CONCENT_MESSAGING_TIME
    )

    if acceptance_deadline < current_time:
        logging.log_timeout(
            client_message,
            request.META['HTTP_CONCENT_CLIENT_PUBLIC_KEY'],
            client_message.timestamp + settings.CONCENT_MESSAGING_TIME,
        )
        raise Http400("Time to accept this task is already over.")

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

    # Any of the items from list of overdue acceptances matches condition current_time < payment_ts + PAYMENT_DUE_TIME.
    acceptance_time_overdue = any(current_time < subtask_results_accepted.payment_ts + settings.PAYMENT_DUE_TIME for subtask_results_accepted in client_message.subtask_results_accepted_list)

    if T1_is_bigger_than_payments_ts or acceptance_time_overdue:
        return message.concents.ForcePaymentRejected(
            reason = message.concents.ForcePaymentRejected.REASON.TimestampError
        )

    # Concent gets list of list of forced payments from payment API where T0 <= payment_ts + PAYMENT_DUE_TIME.
    list_of_forced_payments = base.get_forced_payments(oldest_payments_ts, requestor_ethereum_public_key, client_public_key, request = request)

    sum_of_payments = base.payment_summary(request = request, subtask_results_accepted_list = client_message.subtask_results_accepted_list, list_of_transactions = list_of_transactions, list_of_forced_payments = list_of_forced_payments)  # pylint: disable=no-value-for-parameter

    # Concent defines time T2 (end time) equal to youngest payment_ts from passed SubtaskResultAccepted messages from subtask_results_accepted_list.
    payment_ts = min(subtask_results_accepted.payment_ts for subtask_results_accepted in client_message.subtask_results_accepted_list)

    if sum_of_payments <= 0:
        return message.concents.ForcePaymentRejected(
            reason = message.concents.ForcePaymentRejected.REASON.NoUnsettledTasksFound
        )
    elif sum_of_payments > 0:
        amount_paid = base.make_payment_to_provider(
            sum_of_payments,
            payment_ts,
            requestor_ethereum_public_key,
            client_public_key
        )

        amount_pending = sum_of_payments - amount_paid
        provider_force_payment_commited = message.concents.ForcePaymentCommitted(
            payment_ts              = payment_ts,
            task_owner_key          = requestor_ethereum_public_key,
            provider_eth_account    = client_public_key,
            amount_paid             = amount_paid,
            amount_pending          = amount_pending,
            recipient_type          = message.concents.ForcePaymentCommitted.Actor.Provider,
        )

        requestor_force_payment_commited = message.concents.ForcePaymentCommitted(
            payment_ts              = payment_ts,
            task_owner_key          = requestor_ethereum_public_key,
            provider_eth_account    = client_public_key,
            amount_paid             = amount_paid,
            amount_pending          = amount_pending,
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


def handle_messages_from_database(
    client_public_key:  bytes                   = None,
    response_type:      PendingResponse.Queue   = None,
):
    assert client_public_key    not in ['', None]

    encoded_client_public_key = b64encode(client_public_key)
    pending_response = PendingResponse.objects.filter(
        client__public_key = encoded_client_public_key,
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
            encoded_client_public_key,
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
            encoded_client_public_key,
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


def handle_message(client_message, request):
    if isinstance(client_message, message.ForceReportComputedTask):
        return handle_send_force_report_computed_task(request, client_message)

    elif isinstance(client_message, message.AckReportComputedTask):
        return handle_send_ack_report_computed_task(request, client_message)

    elif isinstance(client_message, message.RejectReportComputedTask):
        return handle_send_reject_report_computed_task(request, client_message)

    elif isinstance(client_message,
                    message.concents.ForceGetTaskResult) and client_message.report_computed_task is not None:
        return handle_send_force_get_task_result(request, client_message)

    elif isinstance(client_message,
                    message.concents.ForceSubtaskResults) and client_message.ack_report_computed_task is not None:
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
