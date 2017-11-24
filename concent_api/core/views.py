import json
import datetime

from django.http                    import HttpResponse
from django.views.decorators.http   import require_POST
from django.utils                   import timezone
from django.conf                    import settings

from golem_messages.message         import MessageCannotComputeTask
from golem_messages.message         import MessageTaskFailure
from golem_messages.message         import MessageTaskToCompute

from utils.api_view                 import api_view, Http400
from .models                        import Message, MessageStatus


@api_view
@require_POST
def send(request, message):
    data = message
    validate_message(data)

    if data['type'] == "MessageForceReportComputedTask":
        validate_message_task_to_compute(data['message_task_to_compute'])

        if Message.objects.filter(task_id = data['message_task_to_compute']['task_id']).exists():
            raise Http400("'ForceReportComputedTask' is already being processed for this task.")

        current_time = int(datetime.datetime.now().timestamp())

        if data['message_task_to_compute']['deadline'] < current_time:
            data['type']   = "MessageRejectReportComputedTask"
            data['reason'] = "deadline-exceeded"
            return data

        store_message(data['type'], data['message_task_to_compute'], request.body)
        return HttpResponse("", status = 202)

    elif data['type'] == "MessageAckReportComputedTask":
        validate_message_task_to_compute(data['message_task_to_compute'])

        current_time = int(datetime.datetime.now().timestamp())

        if current_time <= data['message_task_to_compute']['deadline'] + settings.CONCENT_MESSAGING_TIME:
            task_to_compute     = Message.objects.filter(task_id = data['message_task_to_compute']['task_id'], type = "MessageForceReportComputedTask")
            other_ack_message   = Message.objects.filter(task_id = data['message_task_to_compute']['task_id'], type = "MessageAckReportComputedTask")
            reject_message      = Message.objects.filter(task_id = data['message_task_to_compute']['task_id'], type = "MessageRejectReportComputedTask")

            if not task_to_compute.exists():
                raise Http400("'ForceReportComputedTask' for this task has not been initiated yet. Can't accept your 'AckReportComputedTask'.")
            if other_ack_message.exists() or reject_message.exists():
                raise Http400("Received AckReportComputedTask but RejectReportComputedTask or another AckReportComputedTask for this task has already been submitted.")

            store_message(data['type'], data['message_task_to_compute'], request.body)
            return HttpResponse("", status = 202)

    elif data['type'] == "MessageRejectReportComputedTask":
        validate_message_reject(data['message_cannot_commpute_task'])

        current_time    = int(datetime.datetime.now().timestamp())
        task_to_compute = Message.objects.filter(task_id = data['message_cannot_commpute_task']['task_id'], type = "MessageForceReportComputedTask")

        if not task_to_compute.exists():
            raise Http400("'ForceReportComputedTask' for this task has not been initiated yet. Can't accept your 'RejectReportComputedTask'.")

        rejected_message_task_to_compute = task_to_compute.last()
        raw_message_data                 = rejected_message_task_to_compute.data.tobytes()
        decoded_message_data             = json.loads(raw_message_data.decode('utf-8'))

        if current_time <= decoded_message_data['message_task_to_compute']['deadline'] + settings.CONCENT_MESSAGING_TIME:
            other_ack_message       = Message.objects.filter(task_id = data['message_cannot_commpute_task']['task_id'], type = "MessageAckReportComputedTask")
            reject_message          = Message.objects.filter(task_id = data['message_cannot_commpute_task']['task_id'], type = "MessageRejectReportComputedTask")

            if other_ack_message.exists() or reject_message.exists():
                raise Http400("Received RejectReportComputedTask but AckReportComputedTask or another RejectReportComputedTask for this task has already been submitted.")
            store_message(data['type'], data['message_cannot_commpute_task'], request.body)
            return HttpResponse("", status = 202)


@api_view
@require_POST
def receive(_request, _message):
    undelivered_message_statuses    = MessageStatus.objects.filter(delivered = False)
    last_undelivered_message_status = undelivered_message_statuses.order_by('id').last()

    if last_undelivered_message_status is None:
        return None

    # Mark message as delivered
    last_undelivered_message_status.delivered = True
    last_undelivered_message_status.save()

    raw_message_data     = last_undelivered_message_status.message.data.tobytes()
    decoded_message_data = json.loads(raw_message_data.decode('utf-8'))
    current_time         = int(datetime.datetime.now().timestamp())

    if decoded_message_data['type'] == "MessageAckReportComputedTask":
        if current_time <= decoded_message_data['message_task_to_compute']['deadline'] + 2 * settings.CONCENT_MESSAGING_TIME:
            return decoded_message_data
        return HttpResponse("", status = 204)

    if decoded_message_data['type'] == "MessageRejectReportComputedTask":
        message_to_compute          = Message.objects.get(type = 'MessageForceReportComputedTask', task_id = decoded_message_data['message_cannot_commpute_task']['task_id'])
        raw_message_to_compute      = message_to_compute.data.tobytes()
        decoded_message_to_compute  = json.loads(raw_message_to_compute.decode('utf-8'))
        if current_time <= decoded_message_to_compute['message_task_to_compute']['deadline'] + 2 * settings.CONCENT_MESSAGING_TIME:
            if decoded_message_data['message_cannot_commpute_task']['reason'] == "deadline-exceeded":
                decoded_message_to_compute['type']      = "MessageAckReportComputedTask"
                decoded_message_to_compute['timestamp'] = current_time
                return decoded_message_to_compute
            return decoded_message_data
        return HttpResponse("", status = 204)

    if decoded_message_data['message_task_to_compute']['deadline'] + settings.CONCENT_MESSAGING_TIME <= current_time <= decoded_message_data['message_task_to_compute']['deadline'] + 2 * settings.CONCENT_MESSAGING_TIME:
        decoded_message_data['type']      = "MessageAckReportComputedTask"
        decoded_message_data['timestamp'] = current_time
        return decoded_message_data

    if current_time <= decoded_message_data['message_task_to_compute']['deadline'] + settings.CONCENT_MESSAGING_TIME:
        return decoded_message_data

    return HttpResponse("", status = 204)


@api_view
@require_POST
def receive_out_of_band(_request, _message):
    last_task_message = Message.objects.order_by('id').last()
    if last_task_message is None:
        return None

    raw_last_task_message     = last_task_message.data.tobytes()
    decoded_last_task_message = json.loads(raw_last_task_message.decode('utf-8'))
    current_time              = int(datetime.datetime.now().timestamp())
    message_verdict           = {
        "type":                               "MessageVerdictReportComputedTask",
        "timestamp":                          current_time,
        "message_force_report_computed_task": {},
        "message_ack_report_computed_task":   {
            "type":      "MessageAckReportComputedTask",
            "timestamp": current_time
        }
    }

    if decoded_last_task_message['type'] == "MessageForceReportComputedTask":
        task_deadline = decoded_last_task_message['message_task_to_compute']['deadline']
        if task_deadline + settings.CONCENT_MESSAGING_TIME <= current_time:
            message_verdict['message_force_report_computed_task'] = decoded_last_task_message
            return message_verdict

    if decoded_last_task_message['type'] == "MessageRejectReportComputedTask":
        if decoded_last_task_message['message_cannot_commpute_task']['reason'] == "deadline-exceeded":
            rejected_task_id                                      = decoded_last_task_message['message_cannot_commpute_task']['task_id']
            message_to_compute                                    = Message.objects.get(type = 'MessageForceReportComputedTask', task_id = rejected_task_id)
            raw_message_to_compute                                = message_to_compute.data.tobytes()
            decoded_message_to_compute                            = json.loads(raw_message_to_compute.decode('utf-8'))
            message_verdict['message_force_report_computed_task'] = decoded_message_to_compute
            return message_verdict

    return HttpResponse("", status = 204)


def validate_golem_message_task_to_compute(data):
    if not isinstance(data, MessageTaskToCompute):
        raise Http400("Expected MessageTaskToCompute.")

    if not isinstance(data.timestamp, float):
        raise Http400("Wrong type of message timestamp field. Not a float.")

    if data.task_id <= 0:
        raise Http400("task_id cannot be negative.")
    if not isinstance(data.deadline, int):
        raise Http400("Wrong type of deadline field.")


def validate_golem_message_reject(data):
    if not isinstance(data, MessageCannotComputeTask) and not isinstance(data, MessageTaskFailure):
        raise Http400("Expected MessageCannotComputeTask or MessageTaskFailure.")


def store_message(msg_type, data, raw_message):
    message_timestamp   = datetime.datetime.now(timezone.utc)
    new_message         = Message(
        type        = msg_type,
        timestamp   = message_timestamp,
        data        = raw_message,
        task_id     = data['task_id']
    )
    new_message.full_clean()
    new_message.save()
    new_message_status = MessageStatus(
        message   = new_message,
        timestamp = message_timestamp,
        delivered = False
    )
    new_message_status.full_clean()
    new_message_status.save()
