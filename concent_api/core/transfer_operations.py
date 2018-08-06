import datetime

from base64 import b64encode
from logging import getLogger
from typing import Optional

import requests

from django.conf import settings
from django.utils import timezone
from golem_messages import message
from golem_messages import shortcuts
from golem_messages.message.concents import FileTransferToken

from core import exceptions
from core.models import Client
from core.models import PaymentInfo
from core.models import PendingResponse
from core.models import Subtask
from core.utils import calculate_maximum_download_time
from core.utils import calculate_subtask_verification_time
from gatekeeper.constants import CLUSTER_DOWNLOAD_PATH
from common import logging
from common.helpers import deserialize_message
from common.helpers import get_current_utc_timestamp
from common.helpers import get_storage_result_file_path
from common.helpers import get_storage_source_file_path
from common.helpers import sign_message
from common.validations import validate_file_transfer_token

logger = getLogger(__name__)


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
                logger,
                subtask.task_id,
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

    logging.log_new_pending_response(
        logger,
        response_type.name,
        queue.name,
        subtask
    )


def create_file_transfer_token_for_concent(
    subtask_id: str,
    result_package_path: str,
    result_size: int,
    result_package_hash: str,
    operation: FileTransferToken.Operation,
    source_package_path: Optional[str] = None,
    source_size: Optional[int] = None,
    source_package_hash: Optional[str] = None,
) -> FileTransferToken:
    return _create_file_transfer_token(
        subtask_id=subtask_id,
        source_package_path=source_package_path,
        source_size=source_size,
        source_package_hash=source_package_hash,
        result_package_path=result_package_path,
        result_size=result_size,
        result_package_hash=result_package_hash,
        authorized_client_public_key=settings.CONCENT_PUBLIC_KEY,
        operation=operation,
        token_expiration_deadline=get_current_utc_timestamp() + calculate_maximum_download_time(result_size, settings.MINIMUM_UPLOAD_RATE)
    )


def create_file_transfer_token_for_golem_client(
    report_computed_task: message.tasks.ReportComputedTask,
    authorized_client_public_key: bytes,
    operation: FileTransferToken.Operation,
) -> FileTransferToken:
    subtask_id = report_computed_task.task_to_compute.compute_task_def['subtask_id']
    task_id = report_computed_task.task_to_compute.compute_task_def['task_id']
    return _create_file_transfer_token(
        subtask_id=subtask_id,
        source_package_path=get_storage_source_file_path(
            subtask_id=subtask_id,
            task_id=task_id,
        ),
        source_size=report_computed_task.task_to_compute.size,
        source_package_hash=report_computed_task.task_to_compute.package_hash,
        result_package_path=get_storage_result_file_path(
            subtask_id=subtask_id,
            task_id=task_id,
        ),
        result_size=report_computed_task.size,
        result_package_hash=report_computed_task.package_hash,
        authorized_client_public_key=authorized_client_public_key,
        operation=operation,
        token_expiration_deadline=calculate_token_expiration_deadline(operation, report_computed_task)
    )


def _create_file_transfer_token(
    subtask_id: str,
    result_package_path: str,
    result_size: int,
    result_package_hash: str,
    authorized_client_public_key: bytes,
    operation: FileTransferToken.Operation,
    source_package_path: Optional[str] = None,
    source_size: Optional[int] = None,
    source_package_hash: Optional[str] = None,
    token_expiration_deadline: Optional[int] = None,
) -> FileTransferToken:

    assert (source_size and source_package_hash and source_package_path) or (result_size and result_package_hash and result_package_path)
    assert isinstance(authorized_client_public_key, bytes)
    assert isinstance(token_expiration_deadline, int) and not isinstance(token_expiration_deadline, bool) or token_expiration_deadline is None
    assert operation in [FileTransferToken.Operation.download, FileTransferToken.Operation.upload]

    file_transfer_token = FileTransferToken(
        token_expiration_deadline       = token_expiration_deadline,
        storage_cluster_address         = settings.STORAGE_CLUSTER_ADDRESS,
        authorized_client_public_key    = authorized_client_public_key,
        operation                       = operation,
        subtask_id                      = subtask_id
    )
    files = []
    if result_package_path and result_package_hash and result_size:
        files.append(
            create_file_info(
                file_path=result_package_path,
                package_hash=result_package_hash,
                size=result_size,
                category=FileTransferToken.FileInfo.Category.results,
            )
        )

    if source_package_path and source_package_hash and source_size:
        files.append(
            create_file_info(
                file_path=source_package_path,
                package_hash=source_package_hash,
                size=source_size,
                category=FileTransferToken.FileInfo.Category.resources,
            )
        )

    file_transfer_token.files = files
    file_transfer_token = sign_message(file_transfer_token, settings.CONCENT_PRIVATE_KEY)

    validate_file_transfer_token(file_transfer_token)

    return file_transfer_token


def create_file_info(
    file_path: str,
    package_hash: str,
    size: int,
    category: FileTransferToken.FileInfo.Category,
) -> FileTransferToken.FileInfo:
    assert isinstance(category, FileTransferToken.FileInfo.Category)
    return FileTransferToken.FileInfo(
        path=file_path,
        checksum=package_hash,
        size=size,
        category=category
    )


def request_upload_status(report_computed_task: message.ReportComputedTask) -> bool:
    slash = '/'
    assert settings.STORAGE_CLUSTER_ADDRESS.endswith(slash)

    file_transfer_token = create_file_transfer_token_for_concent(
        subtask_id=report_computed_task.subtask_id,
        result_package_path=get_storage_result_file_path(
            subtask_id=report_computed_task.subtask_id,
            task_id=report_computed_task.task_id,
        ),
        result_size=report_computed_task.size,
        result_package_hash=report_computed_task.package_hash,
        operation=FileTransferToken.Operation.download
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

    storage_cluster_response = send_request_to_storage_cluster(headers, request_http_address)

    if storage_cluster_response.status_code == 200:
        return True
    elif storage_cluster_response.status_code == 404:
        return False
    else:
        raise exceptions.UnexpectedResponse(f'Cluster storage returned HTTP {storage_cluster_response.status_code}')


def send_request_to_storage_cluster(headers, request_http_address, method='head'):
    assert method in ['get', 'head']

    stream = True if method == 'get' else False

    if settings.STORAGE_CLUSTER_SSL_CERTIFICATE_PATH != '':
        return getattr(requests, method)(
            request_http_address,
            headers=headers,
            verify=settings.STORAGE_CLUSTER_SSL_CERTIFICATE_PATH,
            stream=stream,
        )

    return getattr(requests, method)(
        request_http_address,
        headers=headers,
        stream=stream,
    )


def calculate_token_expiration_deadline(
    operation: FileTransferToken.Operation,
    report_computed_task: message.tasks.ReportComputedTask,
) -> int:
    if operation == FileTransferToken.Operation.upload:
        token_expiration_deadline = (
            int(report_computed_task.task_to_compute.compute_task_def['deadline']) +
            3 * settings.CONCENT_MESSAGING_TIME +
            2 * calculate_maximum_download_time(report_computed_task.size, settings.MINIMUM_UPLOAD_RATE)
        )

    elif operation == FileTransferToken.Operation.download:
        token_expiration_deadline = (
            int(report_computed_task.task_to_compute.compute_task_def['deadline']) +
            calculate_subtask_verification_time(report_computed_task)
        )
    return token_expiration_deadline
