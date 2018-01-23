import datetime

from django.http                    import HttpResponse
from django.views.decorators.http   import require_POST
from django.utils                   import timezone
from django.conf                    import settings

from golem_messages                 import message
from golem_messages.message.base    import verify_time
from golem_messages.exceptions      import MessageFromFutureError
from golem_messages.exceptions      import MessageTooOldError
from golem_messages.exceptions      import TimestampError

from utils.api_view                 import api_view
from utils.api_view                 import Http400
from .models                        import Message
from .models                        import ReceiveStatus
from .models                        import ReceiveOutOfBandStatus


@api_view
@require_POST
def send(_request, client_message):
    if client_message is not None:
        validate_golem_message_timestamp(client_message.timestamp)

    if isinstance(client_message, message.ForceReportComputedTask):
        return handle_send_force_report_computed_task(client_message)

    elif isinstance(client_message, message.AckReportComputedTask):
        return handle_send_ack_report_computed_task(client_message)

    elif isinstance(client_message, message.RejectReportComputedTask):
        return handle_send_reject_report_computed_task(client_message)
    else:
        return handle_unsupported_golem_messages_type(client_message)


@api_view
@require_POST
def receive(_request, _message):
    last_undelivered_message_status = ReceiveStatus.objects.filter(delivered = False).order_by('timestamp').last()
    if last_undelivered_message_status is None:
        last_delivered_message_status = ReceiveStatus.objects.all().order_by('timestamp').last()
        if last_delivered_message_status is None:
            return None

        if last_delivered_message_status.message.type == message.ForceReportComputedTask.TYPE:
            return handle_receive_delivered_force_report_computed_task(last_delivered_message_status)
        return None

    current_time         = int(datetime.datetime.now().timestamp())

    decoded_message_data = deserialize_message(last_undelivered_message_status.message.data.tobytes())

    assert last_undelivered_message_status.message.type == decoded_message_data.TYPE

    if last_undelivered_message_status.message.type == message.ForceReportComputedTask.TYPE:
        if decoded_message_data.task_to_compute.compute_task_def['deadline'] + settings.CONCENT_MESSAGING_TIME < current_time:
            set_message_as_delivered(last_undelivered_message_status)
            return handle_receive_ack_from_force_report_computed_task(decoded_message_data)
    else:
        set_message_as_delivered(last_undelivered_message_status)

    if isinstance(decoded_message_data, message.ForceReportComputedTask):
        set_message_as_delivered(last_undelivered_message_status)
        decoded_message_data.sig = None
        return decoded_message_data

    if isinstance(decoded_message_data, message.AckReportComputedTask):
        if current_time <= decoded_message_data.task_to_compute.compute_task_def['deadline'] + 2 * settings.CONCENT_MESSAGING_TIME:
            decoded_message_data.sig = None
            return decoded_message_data
        return None

    assert isinstance(decoded_message_data, message.RejectReportComputedTask), (
        "At this point ReceiveStatus must contain ForceReportComputedTask because AckReportComputedTask and RejectReportComputedTask have already been handled"
    )

    force_report_computed_task = Message.objects.get(
        type    = message.ForceReportComputedTask.TYPE,
        task_id = decoded_message_data.cannot_compute_task.task_to_compute.compute_task_def['task_id']
    )

    decoded_message_from_database = deserialize_message(force_report_computed_task.data.tobytes())

    if current_time <= decoded_message_from_database.task_to_compute.compute_task_def['deadline'] + 2 * settings.CONCENT_MESSAGING_TIME:
        if decoded_message_data.reason is not None and decoded_message_data.reason == message.RejectReportComputedTask.REASON.TaskTimeLimitExceeded:
            return handle_receive_ack_from_force_report_computed_task(decoded_message_from_database)
        decoded_message_data.sig = None
        return decoded_message_data

    return None


@api_view
@require_POST
def receive_out_of_band(_request, _message):
    undelivered_receive_out_of_band_statuses    = ReceiveOutOfBandStatus.objects.filter(delivered = False)
    last_undelivered_receive_out_of_band_status = undelivered_receive_out_of_band_statuses.order_by('timestamp').last()
    last_undelivered_receive_status             = Message.objects.all().order_by('timestamp').last()

    current_time = int(datetime.datetime.now().timestamp())

    if last_undelivered_receive_out_of_band_status is None:
        if last_undelivered_receive_status is None:
            return None

        if last_undelivered_receive_status.timestamp.timestamp() > current_time:
            return None

        if last_undelivered_receive_status.type == message.AckReportComputedTask.TYPE:
            return handle_receive_out_of_band_ack_report_computed_task(last_undelivered_receive_status)

        if last_undelivered_receive_status.type == message.ForceReportComputedTask.TYPE:
            return handle_receive_out_of_band_force_report_computed_task(last_undelivered_receive_status)

        if last_undelivered_receive_status.type == message.RejectReportComputedTask.TYPE:
            return handle_receive_out_of_band_reject_report_computed_task(last_undelivered_receive_status)
        return None

    return None


def handle_send_force_report_computed_task(client_message):
    current_time = int(datetime.datetime.now().timestamp())
    validate_golem_message_task_to_compute(client_message.task_to_compute)

    if Message.objects.filter(task_id = client_message.task_to_compute.compute_task_def['task_id']).exists():
        raise Http400("{} is already being processed for this task.".format(client_message.__class__.__name__))

    if client_message.task_to_compute.compute_task_def['deadline'] < current_time:
        reject_force_report_computed_task                 = message.RejectReportComputedTask(timestamp = client_message.timestamp)
        reject_force_report_computed_task.reason          = message.RejectReportComputedTask.REASON.TaskTimeLimitExceeded
        reject_force_report_computed_task.task_to_compute = client_message.task_to_compute
        return reject_force_report_computed_task
    client_message.sig = None
    store_message_and_message_status(
        client_message.TYPE,
        client_message.task_to_compute.compute_task_def['task_id'],
        client_message.serialize(),
        status = ReceiveStatus
    )
    return HttpResponse("", status = 202)


def handle_send_ack_report_computed_task(client_message):
    current_time = int(datetime.datetime.now().timestamp())
    validate_golem_message_task_to_compute(client_message.task_to_compute)

    if current_time <= client_message.task_to_compute.compute_task_def['deadline'] + settings.CONCENT_MESSAGING_TIME:
        force_task_to_compute   = Message.objects.filter(task_id = client_message.task_to_compute.compute_task_def['task_id'], type = message.ForceReportComputedTask.TYPE)
        previous_ack_message    = Message.objects.filter(task_id = client_message.task_to_compute.compute_task_def['task_id'], type = message.AckReportComputedTask.TYPE)
        reject_message          = Message.objects.filter(task_id = client_message.task_to_compute.compute_task_def['task_id'], type = message.RejectReportComputedTask.TYPE)

        if not force_task_to_compute.exists():
            raise Http400("'ForceReportComputedTask' for this task has not been initiated yet. Can't accept your 'AckReportComputedTask'.")
        if previous_ack_message.exists() or reject_message.exists():
            raise Http400(
                "Received AckReportComputedTask but RejectReportComputedTask "
                "or another AckReportComputedTask for this task has already been submitted."
            )
        client_message.sig = None
        store_message_and_message_status(
            client_message.TYPE,
            client_message.task_to_compute.compute_task_def['task_id'],
            client_message.serialize(),
            status = ReceiveStatus
        )

        return HttpResponse("", status = 202)
    else:
        raise Http400("Time to acknowledge this task is already over.")


def handle_send_reject_report_computed_task(client_message):
    current_time = int(datetime.datetime.now().timestamp())
    validate_golem_message_reject(client_message.cannot_compute_task)

    force_report_computed_task_from_database = Message.objects.filter(task_id = client_message.cannot_compute_task.task_to_compute.compute_task_def['task_id'], type = message.ForceReportComputedTask.TYPE)

    if not force_report_computed_task_from_database.exists():
        raise Http400("'ForceReportComputedTask' for this task has not been initiated yet. Can't accept your 'RejectReportComputedTask'.")

    force_report_computed_task = deserialize_message(force_report_computed_task_from_database.last().data.tobytes())

    assert hasattr(force_report_computed_task, 'task_to_compute')

    assert force_report_computed_task.task_to_compute.compute_task_def['task_id'] == client_message.cannot_compute_task.task_to_compute.compute_task_def['task_id']
    if client_message.cannot_compute_task.reason == message.CannotComputeTask.REASON.WrongCTD:
        client_message.sig = None
        store_message_and_message_status(
            client_message.TYPE,
            force_report_computed_task.task_to_compute.compute_task_def['task_id'],
            client_message.serialize(),
            status = ReceiveStatus
        )

        return HttpResponse("", status = 202)

    if current_time <= force_report_computed_task.task_to_compute.compute_task_def['deadline'] + settings.CONCENT_MESSAGING_TIME:
        ack_message             = Message.objects.filter(task_id = client_message.cannot_compute_task.task_to_compute.compute_task_def['task_id'], type = message.AckReportComputedTask.TYPE)
        previous_reject_message = Message.objects.filter(task_id = client_message.cannot_compute_task.task_to_compute.compute_task_def['task_id'], type = message.RejectReportComputedTask.TYPE)

        if ack_message.exists() or previous_reject_message.exists():
            raise Http400("Received RejectReportComputedTask but AckReportComputedTask or another RejectReportComputedTask for this task has already been submitted.")

        client_message.sig = None
        store_message_and_message_status(
            client_message.TYPE,
            force_report_computed_task.task_to_compute.compute_task_def['task_id'],
            client_message.serialize(),
            status = ReceiveStatus
        )
        return HttpResponse("", status = 202)
    else:
        raise Http400("Time to acknowledge this task is already over.")


def handle_unsupported_golem_messages_type(client_message):
    if hasattr(client_message, 'TYPE'):
        raise Http400("This message type ({}) is either not supported or cannot be submitted to Concent.".format(client_message.TYPE))
    else:
        raise Http400("Unknown message type or not a Golem message.")


def handle_receive_delivered_force_report_computed_task(delivered_message):
    force_report_task = deserialize_message(delivered_message.message.data.tobytes())

    ack_report_computed_task                 = message.AckReportComputedTask()
    ack_report_computed_task.task_to_compute = force_report_task.task_to_compute
    store_message_and_message_status(
        ack_report_computed_task.TYPE,
        force_report_task.task_to_compute.compute_task_def['task_id'],
        ack_report_computed_task.serialize(),
    )
    ack_report_computed_task.sig = None
    return ack_report_computed_task


def handle_receive_ack_from_force_report_computed_task(decoded_message):
    ack_report_computed_task                 = message.AckReportComputedTask()
    ack_report_computed_task.task_to_compute = decoded_message.task_to_compute
    return ack_report_computed_task


def set_message_as_delivered(client_message):
    client_message.delivered = True
    client_message.full_clean()
    client_message.save()


def handle_receive_out_of_band_ack_report_computed_task(undelivered_message):
    decoded_ack_report_computed_task = deserialize_message(undelivered_message.data.tobytes())

    force_report_computed_task                  = message.ForceReportComputedTask()
    force_report_computed_task.task_to_compute  = decoded_ack_report_computed_task.task_to_compute

    message_verdict                             = message.VerdictReportComputedTask()
    message_verdict.force_report_computed_task  = force_report_computed_task
    message_verdict.ack_report_computed_task    = decoded_ack_report_computed_task

    store_message_and_message_status(
        message_verdict.TYPE,
        decoded_ack_report_computed_task.task_to_compute.compute_task_def['task_id'],
        message_verdict.serialize(),
        status = ReceiveOutOfBandStatus,
    )
    message_verdict.sig = None
    return message_verdict


def handle_receive_out_of_band_force_report_computed_task(undelivered_message):
    decoded_force_report_computed_task = deserialize_message(undelivered_message.data.tobytes())

    ack_report_computed_task                    = message.AckReportComputedTask()
    ack_report_computed_task.task_to_compute    = decoded_force_report_computed_task.task_to_compute

    message_verdict                             = message.VerdictReportComputedTask()
    message_verdict.ack_report_computed_task    = ack_report_computed_task
    message_verdict.force_report_computed_task  = decoded_force_report_computed_task

    store_message_and_message_status(
        message_verdict.TYPE,
        decoded_force_report_computed_task.task_to_compute.compute_task_def['task_id'],
        message_verdict.serialize(),
        status = ReceiveOutOfBandStatus,
    )
    message_verdict.sig = None
    return message_verdict


def handle_receive_out_of_band_reject_report_computed_task(undelivered_message):
    decoded_reject_report_computed_task = deserialize_message(undelivered_message.data.tobytes())

    message_verdict                                          = message.VerdictReportComputedTask()
    message_verdict.ack_report_computed_task                 = message.AckReportComputedTask()
    message_verdict.ack_report_computed_task.task_to_compute = decoded_reject_report_computed_task.cannot_compute_task.task_to_compute

    store_message_and_message_status(
        message_verdict.TYPE,
        decoded_reject_report_computed_task.cannot_compute_task.task_to_compute.compute_task_def['task_id'],
        message_verdict.serialize(),
        status = ReceiveOutOfBandStatus
    )
    message_verdict.sig = None
    return message_verdict


def deserialize_message(raw_message_data):
    return message.Message.deserialize(
        raw_message_data,
        None,
        check_time = False
    )


def validate_golem_message_task_to_compute(data):
    if not isinstance(data, message.TaskToCompute):
        raise Http400("Expected TaskToCompute.")

    if data.compute_task_def['task_id'] == '':
        raise Http400("task_id cannot be blank.")

    if not isinstance(data.compute_task_def['deadline'], int):
        raise Http400("Wrong type of deadline field.")


def validate_golem_message_reject(data):
    if not isinstance(data, message.CannotComputeTask) and not isinstance(data, message.TaskFailure) and not isinstance(data, message.TaskToCompute):
        raise Http400("Expected CannotComputeTask, TaskFailure or TaskToCompute.")

    if isinstance(data, message.CannotComputeTask):
        if data.task_to_compute.compute_task_def['task_id'] == '':
            raise Http400("task_id cannot be blank.")

    if isinstance(data, (message.TaskToCompute, message.TaskFailure)):
        if data.compute_task_def['task_id'] == '':
            raise Http400("task_id cannot be blank.")

        if not isinstance(data.compute_task_def['deadline'], int):
            raise Http400("Wrong type of deadline field.")


def validate_golem_message_timestamp(timestamp):
    try:
        verify_time(timestamp)
    except MessageFromFutureError:
        raise Http400('Message timestamp too far in the future.')
    except MessageTooOldError:
        raise Http400('Message is too old.')
    except TimestampError as exception:
        raise Http400(exception)


def store_message_and_message_status(golem_message_type, task_id, raw_golem_message, status = None):
    message_timestamp = datetime.datetime.now(timezone.utc)
    golem_message = Message(
        type        = golem_message_type,
        timestamp   = message_timestamp,
        data        = raw_golem_message,
        task_id     = task_id
    )
    golem_message.full_clean()
    golem_message.save()

    if status == ReceiveStatus:
        receive_message_status  = ReceiveStatus(
            message     = golem_message,
            timestamp   = message_timestamp
        )
        receive_message_status.full_clean()
        receive_message_status.save()

    elif status == ReceiveOutOfBandStatus:
        receive_out_of_band_status = ReceiveOutOfBandStatus(
            message     = golem_message,
            timestamp   = message_timestamp,
            delivered   = True
        )
        receive_out_of_band_status.full_clean()
        receive_out_of_band_status.save()
    else:
        return None
