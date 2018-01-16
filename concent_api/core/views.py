import datetime
from base64                         import b64decode

from django.http                    import HttpResponse
from django.http                    import JsonResponse
from django.views.decorators.http   import require_POST
from django.utils                   import timezone
from django.conf                    import settings

from golem_messages                 import message
from golem_messages.exceptions      import InvalidSignature
from golem_messages.shortcuts       import dump
from golem_messages.shortcuts       import load

from utils.api_view                 import api_view
from utils.api_view                 import Http400
from .models                        import Message
from .models                        import ReceiveStatus
from .models                        import ReceiveOutOfBandStatus


@api_view
@require_POST
def send(_request, client_message):
    current_time = int(datetime.datetime.now().timestamp())
    if isinstance(client_message, message.ForceReportComputedTask):
        validate_golem_message_task_to_compute(client_message.task_to_compute)

        if Message.objects.filter(task_id = client_message.task_to_compute.compute_task_def['task_id']).exists():
            raise Http400("{} is already being processed for this task.".format(client_message.__class__.__name__))

        if client_message.task_to_compute.compute_task_def['deadline'] < current_time:
            reject_force_report_computed_task                 = message.RejectReportComputedTask(timestamp = client_message.timestamp)
            reject_force_report_computed_task.reason          = message.RejectReportComputedTask.Reason.TASK_TIME_LIMIT_EXCEEDED
            reject_force_report_computed_task.task_to_compute = client_message.task_to_compute
            return reject_force_report_computed_task

        golem_message, message_timestamp = store_message(
            type(client_message).__name__,
            client_message.task_to_compute.compute_task_def['task_id'],
            client_message.serialize()
        )
        store_receive_message_status(
            golem_message,
            message_timestamp,
        )
        return HttpResponse("", status = 202)

    elif isinstance(client_message, message.AckReportComputedTask):
        validate_golem_message_task_to_compute(client_message.task_to_compute)

        if current_time <= client_message.task_to_compute.compute_task_def['deadline'] + settings.CONCENT_MESSAGING_TIME:
            force_task_to_compute   = Message.objects.filter(task_id = client_message.task_to_compute.compute_task_def['task_id'], type = "ForceReportComputedTask")
            previous_ack_message    = Message.objects.filter(task_id = client_message.task_to_compute.compute_task_def['task_id'], type = "AckReportComputedTask")
            reject_message          = Message.objects.filter(task_id = client_message.task_to_compute.compute_task_def['task_id'], type = "RejectReportComputedTask")

            if not force_task_to_compute.exists():
                raise Http400("'ForceReportComputedTask' for this task has not been initiated yet. Can't accept your 'AckReportComputedTask'.")
            if previous_ack_message.exists() or reject_message.exists():
                raise Http400(
                    "Received AckReportComputedTask but RejectReportComputedTask "
                    "or another AckReportComputedTask for this task has already been submitted."
                )
            client_message.sig = None
            golem_message, message_timestamp = store_message(
                type(client_message).__name__,
                client_message.task_to_compute.compute_task_def['task_id'],
                client_message.serialize()
            )
            store_receive_message_status(
                golem_message,
                message_timestamp,
            )

            return HttpResponse("", status = 202)
        else:
            raise Http400("Time to acknowledge this task is already over.")

    elif isinstance(client_message, message.RejectReportComputedTask):
        validate_golem_message_reject(client_message.cannot_compute_task)

        force_report_computed_task_from_database = Message.objects.filter(task_id = client_message.cannot_compute_task.task_to_compute.compute_task_def['task_id'], type = "ForceReportComputedTask")

        if not force_report_computed_task_from_database.exists():
            raise Http400("'ForceReportComputedTask' for this task has not been initiated yet. Can't accept your 'RejectReportComputedTask'.")

        force_report_computed_task = message.Message.deserialize(
            force_report_computed_task_from_database.last().data.tobytes(),
            None,
            check_time = False
        )

        assert hasattr(force_report_computed_task, 'task_to_compute')

        assert force_report_computed_task.task_to_compute.compute_task_def['task_id'] == client_message.cannot_compute_task.task_to_compute.compute_task_def['task_id']
        if client_message.cannot_compute_task.reason == message.CannotComputeTask.REASON.WrongCTD:
            store_message(
                type(client_message).__name__,
                force_report_computed_task.task_to_compute.compute_task_def['task_id'],
                client_message.serialize()
            )
            return HttpResponse("", status = 202)

        if current_time <= force_report_computed_task.task_to_compute.compute_task_def['deadline'] + settings.CONCENT_MESSAGING_TIME:
            ack_message             = Message.objects.filter(task_id = client_message.cannot_compute_task.task_to_compute.compute_task_def['task_id'], type = "AckReportComputedTask")
            previous_reject_message = Message.objects.filter(task_id = client_message.cannot_compute_task.task_to_compute.compute_task_def['task_id'], type = "RejectReportComputedTask")

            if ack_message.exists() or previous_reject_message.exists():
                raise Http400("Received RejectReportComputedTask but AckReportComputedTask or another RejectReportComputedTask for this task has already been submitted.")

            golem_message, message_timestamp = store_message(
                type(client_message).__name__,
                force_report_computed_task.task_to_compute.compute_task_def['task_id'],
                client_message.serialize()
            )
            store_receive_message_status(
                golem_message,
                message_timestamp,
            )
            return HttpResponse("", status = 202)
        else:
            raise Http400("Time to acknowledge this task is already over.")
    else:
        if hasattr(client_message, 'TYPE'):
            raise Http400("This message type ({}) is either not supported or cannot be submitted to Concent.".format(client_message.TYPE))
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

        if last_delivered_message_status.message.type == 'ForceReportComputedTask':
            force_report_task_from_database = last_delivered_message_status.message.data.tobytes()

            force_report_task = message.Message.deserialize(
                force_report_task_from_database,
                None,
                check_time = False
            )

            ack_report_computed_task                 = message.AckReportComputedTask()
            ack_report_computed_task.task_to_compute = force_report_task.task_to_compute
            ack_report_computed_task.sig = None
            store_message(
                type(ack_report_computed_task).__name__,
                force_report_task.task_to_compute.compute_task_def['task_id'],
                ack_report_computed_task.serialize(),
            )
            ack_report_computed_task.sig = None
            return ack_report_computed_task

        return None

    current_time         = int(datetime.datetime.now().timestamp())
    raw_message_data     = last_undelivered_message_status.message.data.tobytes()

    decoded_message_data = message.Message.deserialize(
        raw_message_data,
        None,
        check_time = False
    )

    assert last_undelivered_message_status.message.type == type(decoded_message_data).__name__

    if last_undelivered_message_status.message.type == "ForceReportComputedTask":
        if decoded_message_data.task_to_compute.compute_task_def['deadline'] + settings.CONCENT_MESSAGING_TIME < current_time:
            last_undelivered_message_status.delivered = True
            last_undelivered_message_status.full_clean()
            last_undelivered_message_status.save()

            ack_report_computed_task                 = message.AckReportComputedTask()
            ack_report_computed_task.task_to_compute = decoded_message_data.task_to_compute
            return dump(
                ack_report_computed_task,
                settings.CONCENT_PRIVATE_KEY,
                client_public_key,
            )
    else:
        last_undelivered_message_status.delivered = True
        last_undelivered_message_status.full_clean()
        last_undelivered_message_status.save()

    if isinstance(decoded_message_data, message.ForceReportComputedTask):
        last_undelivered_message_status.delivered = True
        last_undelivered_message_status.full_clean()
        last_undelivered_message_status.save()
        decoded_message_data.sig = None
        return decoded_message_data

    if isinstance(decoded_message_data, message.AckReportComputedTask):
        if current_time <= decoded_message_data.task_to_compute.compute_task_def['deadline'] + 2 * settings.CONCENT_MESSAGING_TIME:
            decoded_message_data.sig = None
            return decoded_message_data
        return None

    if isinstance(decoded_message_data, message.RejectReportComputedTask):
        force_report_computed_task = Message.objects.get(
            type    = 'ForceReportComputedTask',
            task_id = decoded_message_data.cannot_compute_task.task_to_compute.compute_task_def['task_id']
        )
        raw_force_report_computed_task = force_report_computed_task.data.tobytes()
        try:
            decoded_message_from_database = load(
                raw_force_report_computed_task,
                settings.CONCENT_PRIVATE_KEY,
                client_public_key,
                check_time = False,
            )
        except InvalidSignature as exception:
            return JsonResponse({'error': "Failed to decode ForceReportComputedTask. {}".format(exception)}, status = 400)

        if current_time <= decoded_message_from_database.task_to_compute.compute_task_def['deadline'] + 2 * settings.CONCENT_MESSAGING_TIME:
            if decoded_message_data.reason is not None and decoded_message_data.reason == message.RejectReportComputedTask.Reason.TASK_TIME_LIMIT_EXCEEDED:
                ack_report_computed_task = message.AckReportComputedTask(timestamp = current_time)
                ack_report_computed_task.task_to_compute = decoded_message_from_database.task_to_compute
                return ack_report_computed_task
            decoded_message_data.sig = None
            return decoded_message_data
        return None
    else:
        if decoded_message_data.task_to_compute.compute_task_def['deadline'] + settings.CONCENT_MESSAGING_TIME <= current_time <= decoded_message_data.task_to_compute.deadline + 2 * settings.CONCENT_MESSAGING_TIME:
            ack_report_computed_task = message.AckReportComputedTask(
                task_id                 = decoded_message_data.task_id,
                timestamp               = current_time,
            )
            ack_report_computed_task.task_to_compute = decoded_message_data.task_to_compute
            return ack_report_computed_task

        if current_time <= decoded_message_data.message_task_to_compute.compute_task_def['deadline'] + settings.CONCENT_MESSAGING_TIME:
            return decoded_message_data

        return None


@api_view
@require_POST
def receive_out_of_band(request, _message):
    undelivered_receive_out_of_band_statuses    = ReceiveOutOfBandStatus.objects.filter(delivered = False)
    last_undelivered_receive_out_of_band_status = undelivered_receive_out_of_band_statuses.order_by('timestamp').last()
    last_undelivered_receive_status             = Message.objects.all().order_by('timestamp').last()
    client_public_key                           = decode_client_public_key(request)

    current_time    = int(datetime.datetime.now().timestamp())
    message_verdict = message.VerdictReportComputedTask()

    if last_undelivered_receive_out_of_band_status is None:
        if last_undelivered_receive_status is None:
            return None

        if last_undelivered_receive_status.timestamp.timestamp() > current_time:
            return None

        if last_undelivered_receive_status.type == 'AckReportComputedTask':
            serialized_ack_report_computed_task = last_undelivered_receive_status.data.tobytes()

            try:
                decoded_ack_report_computed_task = message.Message.deserialize(
                    serialized_ack_report_computed_task,
                    None,
                    check_time = False
                )

            except InvalidSignature as exception:
                return JsonResponse({'error': "Failed to decode AckReportComputedTask. {}".format(exception)}, status = 400)

            force_report_computed_task = message.ForceReportComputedTask()
            force_report_computed_task.task_to_compute = decoded_ack_report_computed_task.task_to_compute

            message_verdict.force_report_computed_task = force_report_computed_task
            message_verdict.ack_report_computed_task   = decoded_ack_report_computed_task
            message_verdict.sig = None
            store_message(
                type(message_verdict).__name__,
                decoded_ack_report_computed_task.task_to_compute.compute_task_def['task_id'],
                message_verdict.serialize()
            )
            message_verdict.sig = None
            return message_verdict

        if last_undelivered_receive_status.type == 'ForceReportComputedTask':
            serialized_force_report_computed_task = last_undelivered_receive_status.data.tobytes()
            try:
                decoded_force_report_computed_task = load(
                    serialized_force_report_computed_task,
                    settings.CONCENT_PRIVATE_KEY,
                    client_public_key,
                    check_time = False
                )
            except InvalidSignature as exception:
                return JsonResponse({'error': "Failed to decode ForceReportComputedTask. {}".format(exception)}, status = 400)

            ack_report_computed_task                    = message.AckReportComputedTask()
            ack_report_computed_task.task_to_compute    = decoded_force_report_computed_task.task_to_compute
            message_verdict.ack_report_computed_task    = ack_report_computed_task
            message_verdict.force_report_computed_task  = decoded_force_report_computed_task

            message_verdict.sig = None
            store_message(
                type(message_verdict).__name__,
                decoded_force_report_computed_task.task_to_compute.compute_task_def['task_id'],
                message_verdict.serialize()
            )
            message_verdict.sig = None
            return message_verdict
        return None

    raw_last_task_message = last_undelivered_receive_out_of_band_status.message.data.tobytes()
    try:
        decoded_last_task_message = load(
            raw_last_task_message,
            settings.CONCENT_PRIVATE_KEY,
            client_public_key,
            check_time = False,
        )
    except InvalidSignature as exception:
        return JsonResponse({'error': "Failed to decode a Golem Message. {}".format(exception)}, status = 400)

    message_ack_report_computed_task = message.AckReportComputedTask()
    if isinstance(decoded_last_task_message, message.ForceReportComputedTask):
        if decoded_last_task_message.task_to_compute.compute_task_def['deadline'] + settings.CONCENT_MESSAGING_TIME <= current_time:
            message_verdict.force_report_computed_task = decoded_last_task_message
            message_ack_report_computed_task = message.AckReportComputedTask()
            message_ack_report_computed_task.task_to_compute = decoded_last_task_message.task_to_compute

            message_verdict.ack_report_computed_task = message_ack_report_computed_task

            last_undelivered_receive_out_of_band_status.delivered = True
            last_undelivered_receive_out_of_band_status.full_clean()
            last_undelivered_receive_out_of_band_status.save()
            message_verdict.sig = None

            golem_message, message_timestamp = store_message(
                type(message_verdict).__name__,
                decoded_last_task_message.task_to_compute.compute_task_def['task_id'],
                message_verdict.serialize()
            )
            store_receive_out_of_band(golem_message, message_timestamp)
            message_verdict.sig = None
            return message_verdict

    if isinstance(decoded_last_task_message, message.RejectReportComputedTask):
        if decoded_last_task_message.reason == message.RejectReportComputedTask.Reason.TASK_TIME_LIMIT_EXCEEDED:
            rejected_task_id               = decoded_last_task_message.message_cannot_compute_task.task_to_compute.compute_task_def['task_id']
            force_report_computed_task     = Message.objects.get(type = 'ForceReportComputedTask', task_id = rejected_task_id)
            raw_force_report_computed_task = force_report_computed_task.data.tobytes()
            try:
                force_report_computed_task     = load(
                    raw_force_report_computed_task,
                    settings.CONCENT_PRIVATE_KEY,
                    client_public_key
                )
            except InvalidSignature as exception:
                return JsonResponse({'error': "Failed to decode ForceReportComputedTask. {}".format(exception)}, status = 400)

            message_ack_report_computed_task.task_to_compute = force_report_computed_task.task_to_compute
            message_verdict.ack_report_computed_task         = message_ack_report_computed_task

            last_undelivered_receive_out_of_band_status.delivered = True
            last_undelivered_receive_out_of_band_status.full_clean()
            last_undelivered_receive_out_of_band_status.save()

            message_verdict.sig = None
            golem_message, message_timestamp = store_message(
                type(message_verdict).__name__,
                decoded_last_task_message.message_cannot_compute_task.task_to_compute.compute_task_def['task_id'],
                message_verdict.serialize()
            )
            store_receive_out_of_band(golem_message, message_timestamp)
            message_verdict.sig = None
            return message_verdict

    return None


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


def store_message(golem_message_type, task_id, raw_golem_message):
    message_timestamp = datetime.datetime.now(timezone.utc)
    golem_message = Message(
        type        = golem_message_type,
        timestamp   = message_timestamp,
        data        = raw_golem_message,
        task_id     = task_id
    )
    golem_message.full_clean()
    golem_message.save()
    return (golem_message, message_timestamp)


def store_receive_message_status(golem_message, message_timestamp):
    receive_message_status  = ReceiveStatus(
        message     = golem_message,
        timestamp   = message_timestamp
    )
    receive_message_status.full_clean()
    receive_message_status.save()


def store_receive_out_of_band(golem_message, message_timestamp):
    receive_out_of_band_status = ReceiveOutOfBandStatus(
        message     = golem_message,
        timestamp   = message_timestamp
    )
    receive_out_of_band_status.full_clean()
    receive_out_of_band_status.save()


def decode_client_public_key(request):
    return b64decode(request.META['HTTP_CONCENT_CLIENT_PUBLIC_KEY'].encode('ascii'), validate = True)
