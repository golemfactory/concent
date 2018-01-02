import datetime
from base64                         import b64decode

from django.http                    import HttpResponse
from django.views.decorators.http   import require_POST
from django.utils                   import timezone
from django.conf                    import settings

from golem_messages.message         import MessageAckReportComputedTask
from golem_messages.message         import MessageForceReportComputedTask
from golem_messages.message         import MessageRejectReportComputedTask
from golem_messages.message         import MessageCannotComputeTask
from golem_messages.message         import MessageTaskFailure
from golem_messages.message         import MessageTaskToCompute
from golem_messages.message         import MessageVerdictReportComputedTask
from golem_messages.shortcuts       import dump
from golem_messages.shortcuts       import load

from utils.api_view                 import api_view
from utils.api_view                 import Http400
from .models                        import Message
from .models                        import ReceiveStatus
from .models                        import ReceiveOutOfBandStatus


@api_view
@require_POST
def send(request, message):
    client_public_key = decode_client_public_key(request)
    current_time      = int(datetime.datetime.now().timestamp())

    if isinstance(message, MessageForceReportComputedTask):
        loaded_message = load(
            message.message_task_to_compute,
            settings.CONCENT_PRIVATE_KEY,
            client_public_key
        )
        validate_golem_message_task_to_compute(loaded_message)

        if Message.objects.filter(task_id = loaded_message.task_id).exists():
            raise Http400("{} is already being processed for this task.".format(message.__class__.__name__))

        if loaded_message.deadline < current_time:
            return MessageRejectReportComputedTask(
                reason                  = "deadline-exceeded",
                message_task_to_compute = message.message_task_to_compute,
            )

        golem_message, message_timestamp = store_message(
            type(message).__name__,
            loaded_message.task_id,
            request.body
        )
        store_receive_message_status(
            golem_message,
            message_timestamp,
        )
        return HttpResponse("", status = 202)

    elif isinstance(message, MessageAckReportComputedTask):
        loaded_message = load(
            message.message_task_to_compute,
            settings.CONCENT_PRIVATE_KEY,
            client_public_key
        )
        validate_golem_message_task_to_compute(loaded_message)

        if current_time <= loaded_message.deadline + settings.CONCENT_MESSAGING_TIME:
            force_task_to_compute   = Message.objects.filter(task_id = loaded_message.task_id, type = "MessageForceReportComputedTask")
            previous_ack_message    = Message.objects.filter(task_id = loaded_message.task_id, type = "MessageAckReportComputedTask")
            reject_message          = Message.objects.filter(task_id = loaded_message.task_id, type = "MessageRejectReportComputedTask")

            if not force_task_to_compute.exists():
                raise Http400("'ForceReportComputedTask' for this task has not been initiated yet. Can't accept your 'AckReportComputedTask'.")
            if previous_ack_message.exists() or reject_message.exists():
                raise Http400(
                    "Received AckReportComputedTask but RejectReportComputedTask. "
                    "or another AckReportComputedTask for this task has already been submitted."
                )

            store_message(
                type(message).__name__,
                loaded_message.task_id,
                request.body
            )
            return HttpResponse("", status = 202)
        else:
            raise Http400("Time to acknowledge this task is already over.")

    elif isinstance(message, MessageRejectReportComputedTask):
        message_cannot_compute_task = load(
            message.message_cannot_compute_task,
            settings.CONCENT_PRIVATE_KEY,
            client_public_key
        )
        validate_golem_message_reject(message_cannot_compute_task)

        force_report_computed_task_message = Message.objects.filter(task_id = message_cannot_compute_task.task_id, type = "MessageForceReportComputedTask")

        if not force_report_computed_task_message.exists():
            raise Http400("'ForceReportComputedTask' for this task has not been initiated yet. Can't accept your 'RejectReportComputedTask'.")

        force_report_computed_task = load(
            force_report_computed_task_message.last().data.tobytes(),
            settings.CONCENT_PRIVATE_KEY,
            client_public_key,
        )
        assert hasattr(force_report_computed_task, 'message_task_to_compute')

        message_task_to_compute = load(
            force_report_computed_task.message_task_to_compute,
            settings.CONCENT_PRIVATE_KEY,
            client_public_key,
        )
        assert message_task_to_compute.task_id == message_cannot_compute_task.task_id
        if message_cannot_compute_task.reason == "deadline-exceeded":

            store_message(
                type(message).__name__,
                message_task_to_compute.task_id,
                request.body,
                deadline_exceeded = True
            )
            return HttpResponse("", status=202)

        if current_time <= message_task_to_compute.deadline + settings.CONCENT_MESSAGING_TIME:
            ack_message             = Message.objects.filter(task_id = message_cannot_compute_task.task_id, type = "MessageAckReportComputedTask")
            previous_reject_message = Message.objects.filter(task_id = message_cannot_compute_task.task_id, type = "MessageRejectReportComputedTask")

            if ack_message.exists() or previous_reject_message.exists():
                raise Http400("Received RejectReportComputedTask but AckReportComputedTask or another RejectReportComputedTask for this task has already been submitted.")
            store_message(
                type(message).__name__,
                message_task_to_compute.task_id,
                request.body
            )
            return HttpResponse("", status = 202)
        else:
            raise Http400("Time to acknowledge this task is already over.")
    else:
        if hasattr(message, 'TYPE'):
            raise Http400("This message type ({}) is either not supported or cannot be submitted to Concent.".format(message.TYPE))
        else:
            raise Http400("Unknown message type or not a Golem message.")


@api_view
@require_POST
def receive(request, _message):
    client_public_key               = decode_client_public_key(request)
    last_undelivered_message_status = ReceiveStatus.objects.filter(delivered = False).order_by('timestamp').last()
    if last_undelivered_message_status is None:
        last_delivered_message_status = ReceiveStatus.objects.all().order_by('timestamp').last()
        if last_delivered_message_status is None:
            return None

        if last_delivered_message_status.message.type == 'MessageForceReportComputedTask':
            message_force_report_task_from_database = last_delivered_message_status.message.data.tobytes()

            message_force_report_task = load(
                message_force_report_task_from_database,
                settings.CONCENT_PRIVATE_KEY,
                client_public_key
            )

            message_task_to_compute = load(
                message_force_report_task.message_task_to_compute,
                settings.CONCENT_PRIVATE_KEY,
                client_public_key
            )
            message_ack_report_computed_task = MessageAckReportComputedTask(
                message_task_to_compute = message_force_report_task.message_task_to_compute
            )
            dumped_message_ack_report_computed_task = dump(
                message_ack_report_computed_task,
                settings.CONCENT_PRIVATE_KEY,
                client_public_key,
            )
            store_message(
                type(message_ack_report_computed_task).__name__,
                message_task_to_compute.task_id,
                dumped_message_ack_report_computed_task
            )

            ReceiveStatus.objects.filter(delivered = True).order_by('timestamp').last().delivered = False

            return dumped_message_ack_report_computed_task

        return None

    current_time = int(datetime.datetime.now().timestamp())

    raw_message_data     = last_undelivered_message_status.message.data.tobytes()
    decoded_message_data = load(
        raw_message_data,
        settings.CONCENT_PRIVATE_KEY,
        client_public_key,
    )
    assert last_undelivered_message_status.message.type == type(decoded_message_data).__name__

    # Mark message as delivered
    if last_undelivered_message_status.message.type == "MessageForceReportComputedTask":
        message_task_to_compute_from_force = load(
            decoded_message_data.message_task_to_compute,
            settings.CONCENT_PRIVATE_KEY,
            client_public_key
        )

        if message_task_to_compute_from_force.deadline + settings.CONCENT_MESSAGING_TIME < current_time:
            last_undelivered_message_status.delivered = True
            last_undelivered_message_status.save()

            return dump(
                MessageAckReportComputedTask(message_task_to_compute = decoded_message_data.message_task_to_compute),
                settings.CONCENT_PRIVATE_KEY,
                client_public_key,
            )
    else:
        last_undelivered_message_status.delivered = True
        last_undelivered_message_status.save()

    if isinstance(decoded_message_data, MessageForceReportComputedTask):
        last_undelivered_message_status.delivered = True
        last_undelivered_message_status.save()
        return raw_message_data

    elif isinstance(decoded_message_data, MessageAckReportComputedTask):
        message_task_to_compute = load(
            decoded_message_data.message_task_to_compute,
            settings.CONCENT_PRIVATE_KEY,
            client_public_key
        )
        if current_time <= message_task_to_compute.deadline + 2 * settings.CONCENT_MESSAGING_TIME:
            return raw_message_data

        return None

    elif isinstance(decoded_message_data, MessageRejectReportComputedTask):
        message_cannot_compute_task = load(
            decoded_message_data.message_cannot_compute_task,
            settings.CONCENT_PRIVATE_KEY,
            client_public_key
        )
        message_to_compute = Message.objects.get(
            type    = 'MessageForceReportComputedTask',
            task_id = message_cannot_compute_task.task_id
        )
        raw_message_to_compute        = message_to_compute.data.tobytes()
        decoded_message_from_database = load(
            raw_message_to_compute,
            settings.CONCENT_PRIVATE_KEY,
            client_public_key,
        )
        message_task_to_compute = load(
            decoded_message_from_database.message_task_to_compute,
            settings.CONCENT_PRIVATE_KEY,
            client_public_key,
        )
        if current_time <= message_task_to_compute.deadline + 2 * settings.CONCENT_MESSAGING_TIME:
            if decoded_message_data.reason == "deadline-exceeded" or decoded_message_from_database.reason == "deadline-exceeded":
                message_ack_report_computed_task = MessageAckReportComputedTask(
                    timestamp               = current_time,
                    message_task_to_compute = decoded_message_from_database.message_task_to_compute,
                )
                return message_ack_report_computed_task
            return raw_message_data

        return None
    else:
        message_task_to_compute = load(
            decoded_message_data.message_task_to_compute,
            settings.CONCENT_PRIVATE_KEY,
            client_public_key
        )
        if message_task_to_compute.deadline + settings.CONCENT_MESSAGING_TIME <= current_time <= message_task_to_compute.deadline + 2 * settings.CONCENT_MESSAGING_TIME:
            return MessageAckReportComputedTask(
                task_id                 = decoded_message_data.task_id,
                message_task_to_compute = decoded_message_data.message_task_to_compute,
                timestamp               = current_time,
            )
        if current_time <= message_task_to_compute.deadline + settings.CONCENT_MESSAGING_TIME:
            return decoded_message_data

        return None


@api_view
@require_POST
def receive_out_of_band(request, _message):
    undelivered_receive_out_of_band_statuses    = ReceiveOutOfBandStatus.objects.filter(delivered = False)
    last_undelivered_receive_out_of_band_status = undelivered_receive_out_of_band_statuses.order_by('timestamp').last()
    last_undelivered_receive_status             = Message.objects.all().order_by('timestamp').last()
    client_public_key = decode_client_public_key(request)

    current_time    = int(datetime.datetime.now().timestamp())
    message_verdict = MessageVerdictReportComputedTask()

    if last_undelivered_receive_out_of_band_status is None:
        if last_undelivered_receive_status is None:
            return None
        if last_undelivered_receive_status.timestamp.timestamp() > current_time:
            return None
        if last_undelivered_receive_status.type == 'MessageAckReportComputedTask':
            serialized_ack_message = last_undelivered_receive_status.data.tobytes()
            decoded_ack_message = load(
                serialized_ack_message,
                settings.CONCENT_PRIVATE_KEY,
                client_public_key
            )

            decoded_task_to_compute_message = load(
                decoded_ack_message.message_task_to_compute,
                settings.CONCENT_PRIVATE_KEY,
                client_public_key
            )

            force_report_computed_task = MessageForceReportComputedTask(
                message_task_to_compute = decoded_ack_message.message_task_to_compute,
            )
            message_verdict.message_force_report_computed_task = dump(
                force_report_computed_task,
                settings.CONCENT_PRIVATE_KEY,
                client_public_key
            )
            message_verdict.message_ack_report_computed_task = serialized_ack_message

            dumped_message_verdict = dump(
                message_verdict,
                settings.CONCENT_PRIVATE_KEY,
                client_public_key
            )
            store_message(
                type(message_verdict).__name__,
                decoded_task_to_compute_message.task_id,
                dumped_message_verdict
            )

            return message_verdict

        if last_undelivered_receive_status.type == 'MessageForceReportComputedTask':
            serialized_force_message = last_undelivered_receive_status.data.tobytes()
            decoded_force_message = load(
                serialized_force_message,
                settings.CONCENT_PRIVATE_KEY,
                client_public_key
            )

            decoded_task_to_compute_message = load(
                decoded_force_message.message_task_to_compute,
                settings.CONCENT_PRIVATE_KEY,
                client_public_key
            )

            ack_report_computed_task = MessageAckReportComputedTask(
                message_task_to_compute = decoded_force_message.message_task_to_compute
            )
            message_verdict.message_ack_report_computed_task = dump(
                ack_report_computed_task,
                settings.CONCENT_PRIVATE_KEY,
                client_public_key
            )
            message_verdict.message_ack_report_computed_task = serialized_force_message
            dumped_message_verdict = dump(
                message_verdict,
                settings.CONCENT_PRIVATE_KEY,
                client_public_key
            )
            store_message(
                type(message_verdict).__name__,
                decoded_task_to_compute_message.task_id,
                dumped_message_verdict
            )

            return message_verdict

        return None

    raw_last_task_message       = last_undelivered_receive_out_of_band_status.message.data.tobytes()
    decoded_last_task_message   = load(
        raw_last_task_message,
        settings.CONCENT_PRIVATE_KEY,
        client_public_key
    )
    message_ack_report_computed_task = MessageAckReportComputedTask()

    if isinstance(decoded_last_task_message, MessageForceReportComputedTask):
        message_task_to_compute = load(
            decoded_last_task_message.message_task_to_compute,
            settings.CONCENT_PRIVATE_KEY,
            client_public_key
        )
        if message_task_to_compute.deadline + settings.CONCENT_MESSAGING_TIME <= current_time:
            message_verdict.message_force_report_computed_task = dump(
                decoded_last_task_message,
                settings.CONCENT_PRIVATE_KEY,
                client_public_key,
            )
            message_ack_report_computed_task = MessageAckReportComputedTask(
                message_task_to_compute = decoded_last_task_message.message_task_to_compute
            )
            message_verdict.message_ack_report_computed_task = dump(
                message_ack_report_computed_task,
                settings.CONCENT_PRIVATE_KEY,
                client_public_key,
            )
            dumped_message_verdict = dump(
                message_verdict,
                settings.CONCENT_PRIVATE_KEY,
                client_public_key
            )

            last_undelivered_receive_out_of_band_status.delivered = True
            last_undelivered_receive_out_of_band_status.save()

            store_message(
                type(message_verdict).__name__,
                message_task_to_compute.task_id,
                dumped_message_verdict
            )

            return dumped_message_verdict

    if isinstance(decoded_last_task_message, MessageRejectReportComputedTask):
        message_cannot_compute_task = load(
            decoded_last_task_message.message_cannot_compute_task,
            settings.CONCENT_PRIVATE_KEY,
            client_public_key
        )
        if decoded_last_task_message.reason == "deadline-exceeded":
            rejected_task_id           = message_cannot_compute_task.task_id
            message_to_compute         = Message.objects.get(type = 'MessageForceReportComputedTask', task_id = rejected_task_id)
            raw_message_to_compute     = message_to_compute.data.tobytes()
            force_report_computed_task = load(
                raw_message_to_compute,
                settings.CONCENT_PRIVATE_KEY,
                client_public_key
            )

            message_ack_report_computed_task.message_task_to_compute = force_report_computed_task.message_task_to_compute

            dumped_message_ack_report_computed_task = dump(
                message_ack_report_computed_task,
                settings.CONCENT_PRIVATE_KEY,
                client_public_key
            )
            message_verdict.message_ack_report_computed_task = dumped_message_ack_report_computed_task

            dumped_message_verdict = dump(
                message_verdict,
                settings.CONCENT_PRIVATE_KEY,
                client_public_key
            )

            last_undelivered_receive_out_of_band_status.delivered = True
            last_undelivered_receive_out_of_band_status.save()

            store_message(
                type(message_verdict).__name__,
                message_cannot_compute_task.task_id,
                dumped_message_verdict
            )

            return dumped_message_verdict

    return None


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


def store_message(golem_message_type, task_id, raw_golem_message, deadline_exceeded = False):
    message_timestamp   = datetime.datetime.now(timezone.utc)
    golem_message = Message(
        type        = golem_message_type,
        timestamp   = message_timestamp,
        data        = raw_golem_message,
        task_id     = task_id
    )
    golem_message.full_clean()
    golem_message.save()
    return golem_message, message_timestamp


def store_receive_message_status(golem_message, message_timestamp):
    receive_message_status  = ReceiveStatus(
        message     = golem_message,
        timestamp   = message_timestamp
    )
    receive_message_status.full_clean()
    receive_message_status.save()


def store_receive_out_of_bend(golem_message, message_timestamp):
    receive_out_of_band_status = ReceiveOutOfBandStatus(
        message     = golem_message,
        timestamp   = message_timestamp
    )
    receive_out_of_band_status.full_clean()
    receive_out_of_band_status.save()


def decode_client_public_key(request):
    return b64decode(request.META['HTTP_CONCENT_CLIENT_PUBLIC_KEY'].encode('ascii'))
