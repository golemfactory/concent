import json
import datetime

from django.http                    import HttpResponse
from django.views.decorators.http   import require_POST
from django.utils                   import timezone
from django.conf                    import settings

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

    if current_time <= decoded_message_data['message_task_to_compute']['deadline'] + settings.CONCENT_MESSAGING_TIME:
        return decoded_message_data


@api_view
@require_POST
def receive_out_of_band(_request):
    return HttpResponse("out of band message sent", status = 200)


def validate_message(data):
    if 'type' not in data:
        raise Http400("Unspecified message data type.")

    if not isinstance(data['type'], str):
        raise Http400("Invalid message type. Not a string.")

    if 'timestamp' not in data:
        raise Http400("Message timestamp field is missing.")

    if not isinstance(data['timestamp'], int):
        raise Http400("Wrong type of message timestamp. Not an integer.")


def validate_message_task_to_compute(data):
    if data['type'] != "MessageTaskToCompute":
        raise Http400("Expected MessageTaskToCompute")

    if 'deadline' not in data:
        raise Http400("'deadline' field is missing.")

    if not isinstance(data['deadline'], int):
        raise Http400("Wrong type of 'deadline' field. Not an integer.")

    if 'timestamp' not in data:
        raise Http400("Message timestamp field is missing.")

    if not isinstance(data['timestamp'], int):
        raise Http400("Wrong type of message timestamp. Not an integer.")

    if 'task_id' not in data:
        raise Http400("'task_if' field is missing.")

    if not isinstance(data['task_id'], int):
        raise Http400("Wrong type of inside message task id. Not an integer.")


def validate_message_reject(data):
    if data['type'] not in ["MessageCannotComputeTask", "MessageTaskFailure"]:
        raise Http400("Expected MessageCannotComputeTask or MessageTaskFailure")

    if 'reason' not in data:
        raise Http400("'reason' field is missing.")

    if not isinstance(data['reason'], str):
        raise Http400("Wrong type of 'reason' field. Not an string.")


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
