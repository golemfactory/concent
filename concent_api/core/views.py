import datetime
from base64                         import b64decode

from django.http                    import HttpResponse
from django.http                    import JsonResponse
from django.views.decorators.http   import require_POST
from django.utils                   import timezone
from django.conf                    import settings

from golem_messages.message         import AckReportComputedTask
from golem_messages.message         import CannotComputeTask
from golem_messages.message         import ForceReportComputedTask
from golem_messages.message         import TaskToCompute
from golem_messages.message         import TaskFailure
from golem_messages.message         import RejectReportComputedTask
from golem_messages.message         import VerdictReportComputedTask
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
    if isinstance(message, ForceReportComputedTask):
        validate_golem_message_task_to_compute(message.task_to_compute)
        current_time = int(datetime.datetime.now().timestamp())
        if Message.objects.filter(task_id = message.task_to_compute.compute_task_def['task_id']).exists():
            raise Http400("{} is already being processed for this task.".format(message.__class__.__name__))

        if message.task_to_compute.compute_task_def['deadline'] < current_time:
            reject_force_report_computed_task = RejectReportComputedTask(timestamp = message.timestamp)
            reject_force_report_computed_task.reason = RejectReportComputedTask.Reason.TASK_TIME_LIMIT_EXCEEDED
            reject_force_report_computed_task.task_to_compute = message.task_to_compute
            return reject_force_report_computed_task

        golem_message, message_timestamp = store_message(
            type(message).__name__,
            message.task_to_compute.compute_task_def['task_id'],
            request.body
        )
        store_receive_message_status(
            golem_message,
            message_timestamp,
        )
        return HttpResponse("", status = 202)

    elif isinstance(message, AckReportComputedTask):
        validate_golem_message_task_to_compute(message.task_to_compute)
        current_time = int(datetime.datetime.now().timestamp())
        if current_time <= message.task_to_compute.compute_task_def['deadline'] + settings.CONCENT_MESSAGING_TIME:

            force_task_to_compute   = Message.objects.filter(task_id = message.task_to_compute.compute_task_def['task_id'], type = "ForceReportComputedTask")
            previous_ack_message    = Message.objects.filter(task_id = message.task_to_compute.compute_task_def['task_id'], type = "AckReportComputedTask")
            reject_message          = Message.objects.filter(task_id = message.task_to_compute.compute_task_def['task_id'], type = "RejectReportComputedTask")

            if not force_task_to_compute.exists():
                raise Http400("'ForceReportComputedTask' for this task has not been initiated yet. Can't accept your 'AckReportComputedTask'.")
            if previous_ack_message.exists() or reject_message.exists():
                raise Http400(
                    "Received AckReportComputedTask but RejectReportComputedTask "
                    "or another AckReportComputedTask for this task has already been submitted."
                )

            golem_message, message_timestamp = store_message(
                type(message).__name__,
                message.task_to_compute.compute_task_def['task_id'],
                request.body
            )
            store_receive_message_status(
                golem_message,
                message_timestamp,
            )

            return HttpResponse("", status = 202)
        else:
            raise Http400("Time to acknowledge this task is already over.")

    elif isinstance(message, RejectReportComputedTask):
        validate_golem_message_reject(message.cannot_compute_task)
        current_time        = int(datetime.datetime.now().timestamp())

        force_report_computed_task_from_database = Message.objects.filter(task_id = message.cannot_compute_task.task_to_compute.compute_task_def['task_id'], type = "ForceReportComputedTask")

        if not force_report_computed_task_from_database.exists():
            raise Http400("'ForceReportComputedTask' for this task has not been initiated yet. Can't accept your 'RejectReportComputedTask'.")
        additional_client_public_key = check_additional_client_key(request)
        try:
            force_report_computed_task = load(
                force_report_computed_task_from_database.last().data.tobytes(),
                settings.CONCENT_PRIVATE_KEY,
                additional_client_public_key,
            )
        except AttributeError:
            # TODO: Make error handling more granular when golem-messages adds starts raising more specific exceptions
            return JsonResponse(
                {'error': "Failed to decode ForceReportComputedTask. Message and/or key are malformed or don't match."},
                status = 400
            )
        assert hasattr(force_report_computed_task, 'task_to_compute')
        assert force_report_computed_task.task_to_compute.compute_task_def['task_id'] == message.cannot_compute_task.task_to_compute.compute_task_def['task_id']
        if message.cannot_compute_task.reason == CannotComputeTask.REASON.WrongCTD:

            store_message(
                type(message).__name__,
                force_report_computed_task.task_to_compute.compute_task_def['task_id'],
                request.body
            )
            return HttpResponse("", status = 202)

        if current_time <= force_report_computed_task.task_to_compute.compute_task_def['deadline'] + settings.CONCENT_MESSAGING_TIME:
            ack_message             = Message.objects.filter(task_id = message.cannot_compute_task.task_to_compute.compute_task_def['task_id'], type = "AckReportComputedTask")
            previous_reject_message = Message.objects.filter(task_id = message.cannot_compute_task.task_to_compute.compute_task_def['task_id'], type = "RejectReportComputedTask")

            if ack_message.exists() or previous_reject_message.exists():
                raise Http400("Received RejectReportComputedTask but AckReportComputedTask or another RejectReportComputedTask for this task has already been submitted.")

            golem_message, message_timestamp = store_message(
                type(message).__name__,
                force_report_computed_task.task_to_compute.compute_task_def['task_id'],
                request.body
            )
            store_receive_message_status(
                golem_message,
                message_timestamp,
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

        if last_delivered_message_status.message.type == 'ForceReportComputedTask':
            force_report_task_from_database = last_delivered_message_status.message.data.tobytes()
            try:
                force_report_task = load(
                    force_report_task_from_database,
                    settings.CONCENT_PRIVATE_KEY,
                    client_public_key,
                    check_time = False
                )
            except AttributeError:
                # TODO: Make error handling more granular when golem-messages adds starts raising more specific exceptions
                return JsonResponse(
                    {'error': "Failed to decode ForceReportComputedTask. Message and/or key are malformed or don't match."},
                    status = 400
                )

            ack_report_computed_task = AckReportComputedTask()
            ack_report_computed_task.task_to_compute = force_report_task.task_to_compute
            dumped_ack_report_computed_task = dump(
                ack_report_computed_task,
                settings.CONCENT_PRIVATE_KEY,
                client_public_key,
            )
            store_message(
                type(ack_report_computed_task).__name__,
                force_report_task.task_to_compute.compute_task_def['task_id'],
                dump(
                    ack_report_computed_task,
                    settings.CONCENT_PRIVATE_KEY,
                    settings.CONCENT_PUBLIC_KEY,
                )
            )

            return dumped_ack_report_computed_task

        return None

    current_time = int(datetime.datetime.now().timestamp())

    raw_message_data     = last_undelivered_message_status.message.data.tobytes()
    additional_client_public_key = check_additional_client_key(request)
    if last_undelivered_message_status.message.type == 'RejectReportComputedTask':
        try:
            decoded_message_data = load(
                raw_message_data,
                settings.CONCENT_PRIVATE_KEY,
                additional_client_public_key,
                check_time = False,
            )
        except AttributeError:
            # TODO: Make error handling more granular when golem-messages adds starts raising more specific exceptions
            return JsonResponse(
                {'error': "Failed to decode ForceReportComputedTask. Message and/or key are malformed or don't match."},
                status = 400
            )
    else:
        try:
            decoded_message_data = load(
                raw_message_data,
                settings.CONCENT_PRIVATE_KEY,
                client_public_key,
                check_time = False,
            )
        except AttributeError:
            # TODO: Make error handling more granular when golem-messages adds starts raising more specific exceptions
            return JsonResponse(
                {'error': "Failed to decode ForceReportComputedTask. Message and/or key are malformed or don't match."},
                status = 400
            )
    assert last_undelivered_message_status.message.type == type(decoded_message_data).__name__

    if last_undelivered_message_status.message.type == "ForceReportComputedTask":

        if decoded_message_data.task_to_compute.compute_task_def['deadline'] + settings.CONCENT_MESSAGING_TIME < current_time:
            last_undelivered_message_status.delivered = True
            last_undelivered_message_status.full_clean()
            last_undelivered_message_status.save()
            ack_report_computed_task = AckReportComputedTask()
            ack_report_computed_task.task_to_compute = decoded_message_data.task_to_compute
            return dump(
                ack_report_computed_task,
                settings.CONCENT_PRIVATE_KEY,
                client_public_key
            )
    else:
        last_undelivered_message_status.delivered = True
        last_undelivered_message_status.full_clean()
        last_undelivered_message_status.save()

    if isinstance(decoded_message_data, ForceReportComputedTask):
        last_undelivered_message_status.delivered = True
        last_undelivered_message_status.full_clean()
        last_undelivered_message_status.save()
        return raw_message_data
    if isinstance(decoded_message_data, AckReportComputedTask):
        if current_time <= decoded_message_data.task_to_compute.compute_task_def['deadline'] + 2 * settings.CONCENT_MESSAGING_TIME:
            return raw_message_data
        return HttpResponse("", status = 204)
    if isinstance(decoded_message_data, RejectReportComputedTask):
        message_to_compute = Message.objects.get(
            type = 'ForceReportComputedTask',
            task_id = decoded_message_data.cannot_compute_task.task_to_compute.compute_task_def['task_id']
        )
        raw_message_to_compute        = message_to_compute.data.tobytes()
        try:
            decoded_message_from_database = load(
                raw_message_to_compute,
                settings.CONCENT_PRIVATE_KEY,
                client_public_key,
                check_time = False,
            )
        except AttributeError:
            # TODO: Make error handling more granular when golem-messages adds starts raising more specific exceptions
            return JsonResponse(
                {'error': "Failed to decode ForceReportComputedTask. Message and/or key are malformed or don't match."},
                status = 400
            )
        if current_time <= decoded_message_from_database.task_to_compute.compute_task_def['deadline'] + 2 * settings.CONCENT_MESSAGING_TIME:
            if decoded_message_data.reason is not None and decoded_message_data.reason.value == "TASK_TIME_LIMIT_EXCEEDED":
                ack_report_computed_task = AckReportComputedTask(
                    timestamp = current_time,
                )
                ack_report_computed_task.task_to_compute = decoded_message_from_database.task_to_compute
                return ack_report_computed_task
            return raw_message_data
        return HttpResponse("", status = 204)
    if decoded_message_data.task_to_compute.compute_task_def['deadline'] + settings.CONCENT_MESSAGING_TIME <= current_time <= decoded_message_data.task_to_compute.deadline + 2 * settings.CONCENT_MESSAGING_TIME:
        ack_report_computed_task = AckReportComputedTask(
            task_id                 = decoded_message_data.task_id,
            timestamp               = current_time,
        )
        ack_report_computed_task.task_to_compute = decoded_message_data.task_to_compute
        return ack_report_computed_task
    if current_time <= decoded_message_data.message_task_to_compute.compute_task_def['deadline'] + settings.CONCENT_MESSAGING_TIME:
        return decoded_message_data
    return HttpResponse("", status = 204)


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
            try:
                decoded_ack_message = load(
                    serialized_ack_message,
                    settings.CONCENT_PRIVATE_KEY,
                    client_public_key
                )
            except AttributeError:
                # TODO: Make error handling more granular when golem-messages adds starts raising more specific exceptions
                return JsonResponse(
                    {'error': "Failed to decode AckReportComputedTask. Message and/or key are malformed or don't match."},
                    status = 400
                )

            try:
                decoded_task_to_compute_message = load(
                    decoded_ack_message.message_task_to_compute,
                    settings.CONCENT_PRIVATE_KEY,
                    client_public_key
                )
            except AttributeError:
                # TODO: Make error handling more granular when golem-messages adds starts raising more specific exceptions
                return JsonResponse(
                    {'error': "Failed to decode TaskToCompute. Message and/or key are malformed or don't match."},
                    status = 400
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
            try:
                decoded_force_message = load(
                    serialized_force_message,
                    settings.CONCENT_PRIVATE_KEY,
                    client_public_key
                )
            except AttributeError:
                # TODO: Make error handling more granular when golem-messages adds starts raising more specific exceptions
                return JsonResponse(
                    {'error': "Failed to decode ForceReportComputedTask. Message and/or key are malformed or don't match."},
                    status = 400
                )

            try:
                decoded_task_to_compute_message = load(
                    decoded_force_message.message_task_to_compute,
                    settings.CONCENT_PRIVATE_KEY,
                    client_public_key
                )
            except AttributeError:
                # TODO: Make error handling more granular when golem-messages adds starts raising more specific exceptions
                return JsonResponse(
                    {'error': "Failed to decode TaskToCompute. Message and/or key are malformed or don't match."},
                    status = 400
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
        try:
            message_task_to_compute = load(
                decoded_last_task_message.message_task_to_compute,
                settings.CONCENT_PRIVATE_KEY,
                client_public_key
            )
        except AttributeError:
            # TODO: Make error handling more granular when golem-messages adds starts raising more specific exceptions
            return JsonResponse(
                {'error': "Failed to decode ForceReportComputedTask. Message and/or key are malformed or don't match."},
                status = 400
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
            last_undelivered_receive_out_of_band_status.full_clean()
            last_undelivered_receive_out_of_band_status.save()

            golem_message, message_timestamp = store_message(
                type(message_verdict).__name__,
                message_task_to_compute.task_id,
                dumped_message_verdict
            )
            store_receive_out_of_band(golem_message, message_timestamp)

            return dumped_message_verdict

    if isinstance(decoded_last_task_message, MessageRejectReportComputedTask):
        try:
            message_cannot_compute_task = load(
                decoded_last_task_message.message_cannot_compute_task,
                settings.CONCENT_PRIVATE_KEY,
                client_public_key
            )
        except AttributeError:
            # TODO: Make error handling more granular when golem-messages adds starts raising more specific exceptions
            return JsonResponse(
                {'error': "Failed to decode RejectReportComputedTask. Message and/or key are malformed or don't match."},
                status = 400
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
            last_undelivered_receive_out_of_band_status.full_clean()
            last_undelivered_receive_out_of_band_status.save()

            golem_message, message_timestamp = store_message(
                type(message_verdict).__name__,
                message_cannot_compute_task.task_id,
                dumped_message_verdict
            )
            store_receive_out_of_band(golem_message, message_timestamp)

            return dumped_message_verdict

    return None


def validate_golem_message_task_to_compute(data):
    if not isinstance(data, TaskToCompute):
        raise Http400("Expected TaskToCompute")

    # if not isinstance(data.timestamp, float):
    #     raise Http400("Wrong type of message timestamp field. Not a float.")

    if data.compute_task_def['task_id'] == '':
        raise Http400("Task id doesnt exist")

    if int(data.compute_task_def['task_id']) <= 0:
        raise Http400("task_id cannot be negative.")

    if not isinstance(data.compute_task_def['deadline'], int):
        raise Http400("Wrong type of deadline field.")


def validate_golem_message_reject(data):
    if not isinstance(data, CannotComputeTask) and not isinstance(data, TaskFailure) and not isinstance(data, TaskToCompute):
        raise Http400("Expected CannotComputeTask or TaskFailure or TaskToCompute")

    # if not isinstance(data.timestamp, float):
    #     raise Http400("Wrong type of message timestamp field. Not a float.")

    if isinstance(data, CannotComputeTask):
        if data.task_to_compute.compute_task_def['task_id'] == '':
            raise Http400("Task id doesnt exist")

        if int(data.task_to_compute.compute_task_def['task_id']) <= 0:
            raise Http400("task_id cannot be negative.")

    if isinstance(data, (TaskToCompute, TaskFailure)):
        if data.compute_task_def['task_id'] == '':
            raise Http400("Task id doesnt exist")

        if int(data.compute_task_def['task_id']) <= 0:
            raise Http400("task_id cannot be negative.")

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
    return b64decode(request.META['HTTP_CONCENT_CLIENT_PUBLIC_KEY'].encode('ascii'))


def check_additional_client_key(request):
    if 'HTTP_ADDITIONAL_CLIENT_PUBLIC_KEY' in request.META:
        try:
            return b64decode(request.META['HTTP_ADDITIONAL_CLIENT_PUBLIC_KEY'].encode('ascii'))
        except TypeError:
            return JsonResponse({'error': 'The value in the Additional-Client-Public-Key HTTP is not a valid base64-encoded value.'}, status = 400)
