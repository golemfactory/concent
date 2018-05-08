import datetime

from base64 import b64encode
from typing import Optional

import requests

from django.conf import settings
from django.utils import timezone
from golem_messages import message
from golem_messages import shortcuts
from golem_messages.message import FileTransferToken

from core import exceptions
from core.models import Client
from core.models import PaymentInfo
from core.models import PendingResponse
from core.models import Subtask
from gatekeeper.constants import CLUSTER_DOWNLOAD_PATH
from utils import logging
from utils.helpers import calculate_maximum_download_time
from utils.helpers import deserialize_message
from utils.helpers import get_current_utc_timestamp
from utils.helpers import get_storage_file_path
from utils.helpers import sign_message


def verify_file_status(
    client_public_key: bytes,
):
    """
    Function to verify existence of a file on cluster storage
    """

    encoded_client_public_key = b64encode(client_public_key)
    force_get_task_result_list = Subtask.objects.filter(
        requestor__public_key  =encoded_client_public_key,
        state                  = Subtask.SubtaskState.FORCING_RESULT_TRANSFER.name,  # pylint: disable=no-member
    )

    for get_task_result in force_get_task_result_list:
        report_computed_task    = deserialize_message(get_task_result.report_computed_task.data.tobytes())
        if request_upload_status(report_computed_task):
            subtask               = get_task_result
            subtask.state         = Subtask.SubtaskState.RESULT_UPLOADED.name  # pylint: disable=no-member
            subtask.next_deadline = None
            subtask.full_clean()
            subtask.save()

            store_pending_message(
                response_type       = PendingResponse.ResponseType.ForceGetTaskResultDownload,
                client_public_key   = subtask.requestor.public_key_bytes,
                queue               = PendingResponse.Queue.Receive,
                subtask             = subtask,
            )
            logging.log_file_status(
                subtask.subtask_id,
                subtask.requestor.public_key_bytes,
                subtask.provider.public_key_bytes,
            )


def store_pending_message(
    response_type       = None,
    client_public_key   = None,
    queue               = None,
    subtask             = None,
    payment_message     = None,
):
    client          = Client.objects.get_or_create_full_clean(client_public_key)
    receive_queue   = PendingResponse(
        response_type   = response_type.name,
        client          = client,
        queue           = queue.name,
        subtask         = subtask,
    )
    receive_queue.full_clean()
    receive_queue.save()
    if payment_message is not None:
        payment_committed_message = PaymentInfo(
            payment_ts                  = datetime.datetime.fromtimestamp(payment_message.payment_ts, timezone.utc),
            task_owner_key              = payment_message.task_owner_key,
            provider_eth_account        = payment_message.provider_eth_account,
            amount_paid                 = payment_message.amount_paid,
            recipient_type              = payment_message.recipient_type.name,  # pylint: disable=no-member
            amount_pending              = payment_message.amount_pending,
            pending_response            = receive_queue
        )
        payment_committed_message.full_clean()
        payment_committed_message.save()
        task_id = None
        subtask_id = None
    else:
        task_id = subtask.task_id
        subtask_id = subtask.subtask_id

    logging.log_new_pending_response(
        response_type.name,
        queue.name,
        task_id,
        subtask_id,
        client.public_key_bytes,
    )


def create_file_transfer_token_for_concent(
    report_computed_task: message.tasks.ReportComputedTask,
    authorized_client_public_key: bytes,
    operation: FileTransferToken.Operation,
) -> FileTransferToken:
    ten_minutes = 600
    return _create_file_transfer_token(
        report_computed_task,
        authorized_client_public_key,
        operation,
        ten_minutes,
    )


def create_file_transfer_token_for_golem_client(
    report_computed_task:       message.tasks.ReportComputedTask,
    authorized_client_public_key: bytes,
    operation:                  FileTransferToken.Operation,
) -> FileTransferToken:
    return _create_file_transfer_token(
        report_computed_task,
        authorized_client_public_key,
        operation,
    )


def _create_file_transfer_token(
    report_computed_task: message.tasks.ReportComputedTask,
    authorized_client_public_key: bytes,
    operation: FileTransferToken.Operation,
    deadline: Optional[int] = None

) -> FileTransferToken:
    """
    Function to create FileTransferToken from ReportComputedTask message
    """
    def calculate_token_expiration_deadline(
        operation: FileTransferToken.Operation,
        deadline: Optional[int],
    ) -> int:
        if deadline is not None:
            token_expiration_deadline = get_current_utc_timestamp() + deadline
        else:
            if operation == FileTransferToken.Operation.upload:
                token_expiration_deadline = (
                        report_computed_task.task_to_compute.compute_task_def['deadline'] +
                        3 * settings.CONCENT_MESSAGING_TIME +
                        2 * calculate_maximum_download_time(report_computed_task.size)
                )

            elif operation == FileTransferToken.Operation.download:
                token_expiration_deadline = (
                        report_computed_task.task_to_compute.compute_task_def['deadline'] +
                        settings.SUBTASK_VERIFICATION_TIME
                )
        return token_expiration_deadline

    task_id         = report_computed_task.task_to_compute.compute_task_def['task_id']
    subtask_id      = report_computed_task.task_to_compute.compute_task_def['subtask_id']
    file_path       = get_storage_file_path(task_id, subtask_id)

    assert isinstance(authorized_client_public_key, bytes)
    assert isinstance(deadline, int) and not isinstance(deadline, bool) or deadline is None
    assert operation in [FileTransferToken.Operation.download, FileTransferToken.Operation.upload]

    file_transfer_token = FileTransferToken(
        token_expiration_deadline       = calculate_token_expiration_deadline(operation, deadline),
        storage_cluster_address         = settings.STORAGE_CLUSTER_ADDRESS,
        authorized_client_public_key    = authorized_client_public_key,
        operation                       = operation,
        subtask_id                      = report_computed_task.task_to_compute.compute_task_def['subtask_id']
    )
    file_transfer_token.files = [FileTransferToken.FileInfo()]
    file_transfer_token.files[0]['path']      = file_path
    file_transfer_token.files[0]['checksum']  = report_computed_task.package_hash
    file_transfer_token.files[0]['size']      = report_computed_task.size

    file_transfer_token = sign_message(file_transfer_token, settings.CONCENT_PRIVATE_KEY)

    return file_transfer_token


def request_upload_status(report_computed_task: message.ReportComputedTask) -> bool:
    slash = '/'
    assert settings.STORAGE_CLUSTER_ADDRESS.endswith(slash)

    file_transfer_token = create_file_transfer_token_for_concent(
        report_computed_task,
        settings.CONCENT_PUBLIC_KEY,
        FileTransferToken.Operation.download
    )

    assert len(file_transfer_token.files) == 1
    assert not file_transfer_token.files[0]['path'].startswith(slash)

    file_transfer_token.sig = None
    dumped_file_transfer_token = shortcuts.dump(file_transfer_token, settings.CONCENT_PRIVATE_KEY, settings.CONCENT_PUBLIC_KEY)
    headers = {
        'Authorization': 'Golem ' + b64encode(dumped_file_transfer_token).decode(),
        'Concent-Auth':  b64encode(
            shortcuts.dump(
                message.concents.ClientAuthorization(
                    client_public_key=settings.CONCENT_PUBLIC_KEY,
                ),
                settings.CONCENT_PRIVATE_KEY,
                settings.CONCENT_PUBLIC_KEY
            ),
        ).decode(),
    }
    request_http_address = settings.STORAGE_CLUSTER_ADDRESS + CLUSTER_DOWNLOAD_PATH + file_transfer_token.files[0]['path']

    cluster_storage_response = send_request_to_cluster_storage(headers, request_http_address)

    if cluster_storage_response.status_code == 200:
        return True
    elif cluster_storage_response.status_code in [401, 404]:
        return False
    else:
        raise exceptions.UnexpectedResponse()


def send_request_to_cluster_storage(headers, request_http_address):
    if settings.STORAGE_CLUSTER_SSL_CERTIFICATE_PATH != '':
        return requests.head(
            request_http_address,
            headers=headers,
            verify=settings.STORAGE_CLUSTER_SSL_CERTIFICATE_PATH,
        )

    return requests.head(
        request_http_address,
        headers=headers
    )
