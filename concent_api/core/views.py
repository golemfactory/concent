import datetime

from base64                         import b64encode

import requests
from django.conf                    import settings
from django.http                    import HttpResponse
from django.urls                    import reverse
from django.utils                   import timezone
from django.views.decorators.http   import require_POST

from golem_messages                 import message
from golem_messages                 import shortcuts
from golem_messages.message.base    import verify_time
from golem_messages.exceptions      import MessageFromFutureError
from golem_messages.exceptions      import MessageTooOldError
from golem_messages.exceptions      import TimestampError
from golem_messages.datastructures  import MessageHeader

from core                           import exceptions
from utils.api_view                 import api_view
from utils.api_view                 import Http400
from .constants                     import MESSAGE_TASK_ID_MAX_LENGTH
from .models                        import Message
from .models                        import ReceiveOutOfBandStatus
from .models                        import ReceiveStatus


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

    elif isinstance(client_message, message.concents.ForceGetTaskResult) and client_message.report_computed_task is not None:
        return handle_send_force_get_task_result(client_message)

    else:
        return handle_unsupported_golem_messages_type(client_message)


@api_view
@require_POST
def receive(request, _message):
    current_time = int(datetime.datetime.now().timestamp())
    last_undelivered_message_status = ReceiveStatus.objects.filter(delivered = False).order_by('timestamp').last()
    if last_undelivered_message_status is None:
        last_delivered_message_status = ReceiveStatus.objects.all().order_by('timestamp').last()
        if last_delivered_message_status is None:
            return None
        if last_delivered_message_status.message.type == message.ForceReportComputedTask.TYPE:
            return handle_receive_delivered_force_report_computed_task(last_delivered_message_status)
        if last_delivered_message_status.message.type == message.concents.ForceGetTaskResultUpload.TYPE:
            decoded_message_data = deserialize_message(last_delivered_message_status.message.data.tobytes())
            file_uploaded        = get_file_status(decoded_message_data.file_transfer_token)
            if file_uploaded:
                return handle_receive_force_get_task_result_upload_for_requestor(decoded_message_data)
            else:
                return handle_receive_force_get_task_result_failed(decoded_message_data)
        return None

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

    if isinstance(decoded_message_data, message.concents.ForceGetTaskResult):
        set_message_as_delivered(last_undelivered_message_status)
        return handle_receive_force_get_task_result_upload_for_provider(request, decoded_message_data)

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
        reject_force_report_computed_task                 = message.RejectReportComputedTask(
            header = MessageHeader(
                type_     = message.RejectReportComputedTask.TYPE,
                timestamp = client_message.timestamp,
                encrypted = False,
            )
        )
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


def handle_send_force_get_task_result(client_message: message.concents.ForceGetTaskResult) -> message.concents:
    assert client_message.TYPE in message.registered_message_types

    current_time = int(datetime.datetime.now().timestamp())
    validate_golem_message_task_to_compute(client_message.report_computed_task.task_to_compute)

    if Message.objects.filter(
        type    = client_message.TYPE,
        task_id = client_message.report_computed_task.task_to_compute.compute_task_def['task_id']
    ).exists():
        return message.concents.ForceGetTaskResultRejected(
            header = MessageHeader(
                type_     = message.concents.ForceGetTaskResultRejected.TYPE,
                timestamp = client_message.timestamp,
                encrypted = False,
            ),
            reason      = message.concents.ForceGetTaskResultRejected.REASON.OperationAlreadyInitiated,
        )

    elif client_message.report_computed_task.task_to_compute.compute_task_def['deadline'] + settings.FORCE_ACCEPTANCE_TIME < current_time:
        return message.concents.ForceGetTaskResultRejected(
            header = MessageHeader(
                type_     = message.concents.ForceGetTaskResultRejected.TYPE,
                timestamp = client_message.timestamp,
                encrypted = False,
            ),
            reason    = message.concents.ForceGetTaskResultRejected.REASON.AcceptanceTimeLimitExceeded,
        )

    else:
        client_message.sig = None
        store_message_and_message_status(
            client_message.TYPE,
            client_message.report_computed_task.task_to_compute.compute_task_def['task_id'],
            client_message.serialize(),
            status = ReceiveStatus,
        )
        return message.concents.ForceGetTaskResultAck(
            header = MessageHeader(
                type_     = message.concents.ForceGetTaskResultAck.TYPE,
                timestamp = client_message.timestamp,
                encrypted = False,
            )
        )


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


def handle_receive_force_get_task_result_upload_for_provider(request, decoded_message: message.concents.ForceGetTaskResult) -> message.concents.ForceGetTaskResult:
    assert decoded_message.TYPE in message.registered_message_types

    current_time            = int(datetime.datetime.now().timestamp())
    file_transfer_token     = message.concents.FileTransferToken(
        token_expiration_deadline       = current_time + settings.TOKEN_EXPIRATION_DEADLINE,
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
        status    = ReceiveStatus,
        delivered = True,
    )
    force_get_task_result_upload.sig = None
    return force_get_task_result_upload


def handle_receive_force_get_task_result_failed(decoded_message: message.concents.ForceGetTaskResultUpload) -> message.concents.ForceGetTaskResultUpload:
    assert decoded_message.TYPE in message.registered_message_types

    force_get_task_result_failed = message.concents.ForceGetTaskResultFailed()
    force_get_task_result_failed.task_to_compute = decoded_message.force_get_task_result.report_computed_task.task_to_compute
    store_message_and_message_status(
        force_get_task_result_failed.TYPE,
        force_get_task_result_failed.task_to_compute.compute_task_def['task_id'],
        force_get_task_result_failed.serialize(),
        status    = ReceiveStatus,
        delivered = True,
    )
    force_get_task_result_failed.sig = None
    return force_get_task_result_failed


def handle_receive_force_get_task_result_upload_for_requestor(decoded_message: message.concents.ForceGetTaskResultUpload) -> message.concents.ForceGetTaskResultUpload:
    assert decoded_message.TYPE in message.registered_message_types

    current_time = int(datetime.datetime.now().timestamp())
    file_transfer_token = message.concents.FileTransferToken(
        token_expiration_deadline    = current_time + settings.TOKEN_EXPIRATION_DEADLINE,
        storage_cluster_address      = decoded_message.file_transfer_token.storage_cluster_address,
        authorized_client_public_key = decoded_message.file_transfer_token.authorized_client_public_key,
        operation                    = 'download',
        files                        = decoded_message.file_transfer_token.files,
    )

    assert file_transfer_token.timestamp <= file_transfer_token.token_expiration_deadline  # pylint: disable=no-member

    force_get_task_result_upload = message.concents.ForceGetTaskResultUpload(
        file_transfer_token   = file_transfer_token,
    )
    force_get_task_result_upload.force_get_task_result = decoded_message.force_get_task_result

    store_message_and_message_status(
        force_get_task_result_upload.TYPE,
        force_get_task_result_upload.force_get_task_result.report_computed_task.task_to_compute.compute_task_def['task_id'],
        force_get_task_result_upload.serialize(),
        status    = ReceiveStatus,
        delivered = True,
    )
    force_get_task_result_upload.sig = None
    return force_get_task_result_upload


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
        delivered = True
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
        delivered = True
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
        status = ReceiveOutOfBandStatus,
        delivered = True
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


def validate_golem_message_timestamp(timestamp):
    try:
        verify_time(timestamp)
    except MessageFromFutureError:
        raise Http400('Message timestamp too far in the future.')
    except MessageTooOldError:
        raise Http400('Message is too old.')
    except TimestampError as exception:
        raise Http400(exception)


def store_message_and_message_status(golem_message_type: int, task_id: str, raw_golem_message: bytes, status = None, delivered: bool = False):
    assert golem_message_type   in message.registered_message_types
    assert status               in [ReceiveStatus, ReceiveOutOfBandStatus, None]

    message_timestamp = datetime.datetime.now(timezone.utc)
    golem_message = Message(
        type        = golem_message_type,
        timestamp   = message_timestamp,
        data        = raw_golem_message,
        task_id     = task_id
    )
    golem_message.full_clean()
    golem_message.save()

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

    current_time = int(datetime.datetime.now().timestamp())
    file_transfer_token = message.concents.FileTransferToken(
        token_expiration_deadline       = current_time + settings.TOKEN_EXPIRATION_DEADLINE,
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
    request_http_address = settings.STORAGE_CLUSTER_ADDRESS + reverse('gatekeeper:download') + file_transfer_token.files[0]['path']

    cluster_storage_response = requests.head(
        request_http_address,
        headers = headers
    )
    if cluster_storage_response.status_code == 200:
        return True
    elif cluster_storage_response.status_code == 404:
        return False
    else:
        raise exceptions.UnexpectedResponse()
