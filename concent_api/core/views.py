import json
import datetime

from django.http                    import HttpResponse
from django.views.decorators.http   import require_POST
from django.utils                   import timezone

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


@api_view
@require_POST
def receive(_request):
    return "message sent"


@api_view
@require_POST
def receive_out_of_band(_request):
    return HttpResponse("out of band message sent", status = 200)


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
