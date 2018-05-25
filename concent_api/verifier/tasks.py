from zipfile import BadZipFile
import logging
import os

from celery import shared_task
from mypy.types import Optional
from golem_messages import message
from requests import HTTPError

from django.conf import settings
from django.db import DatabaseError
from django.db import transaction

from conductor.models import BlenderSubtaskDefinition
from core.models import PendingResponse
from core.models import Subtask
from core.payments import base
from core.subtask_helpers import update_subtask_state
from core.transfer_operations import create_file_transfer_token_for_concent
from core.transfer_operations import send_request_to_storage_cluster
from core.transfer_operations import store_pending_message
from gatekeeper.constants import CLUSTER_DOWNLOAD_PATH
from utils.constants import ErrorCode
from utils.helpers import deserialize_message
from utils.helpers import get_current_utc_timestamp
from utils.helpers import parse_timestamp_to_utc_datetime
from .constants import VerificationResult
from .constants import CELERY_LOCKED_SUBTASK_DELAY
from .constants import MAXIMUM_VERIFICATION_RESULT_TASK_RETRIES
from .constants import VERIFICATION_RESULT_SUBTASK_STATE_ACCEPTED_LOG_MESSAGE
from .constants import VERIFICATION_RESULT_SUBTASK_STATE_FAILED_LOG_MESSAGE
from .constants import VERIFICATION_RESULT_SUBTASK_STATE_UNEXPECTED_LOG_MESSAGE
from .utils import clean_directory
from .utils import prepare_storage_request_headers
from .utils import run_blender
from .utils import store_file_from_response_in_chunks
from .utils import unpack_archive


logger = logging.getLogger(__name__)


@shared_task
def blender_verification_order(
    subtask_id: str,
    source_package_path: str,
    result_package_path: str,
    output_format: BlenderSubtaskDefinition.OutputFormat,  # pylint: disable=unused-argument
    scene_file: str,  # pylint: disable=unused-argument
    report_computed_task: message.ReportComputedTask,
):
    assert source_package_path != result_package_path

    # Generate a FileTransferToken valid for a download of any file listed in the order.
    file_transfer_token = create_file_transfer_token_for_concent(
        report_computed_task=report_computed_task,
        operation=message.FileTransferToken.Operation.download,
        should_add_source=True,
    )

    # Remove any files from VERIFIER_STORAGE_PATH.
    clean_directory(settings.VERIFIER_STORAGE_PATH)

    # Download all the files listed in the message from the storage server to local storage.
    for file_path in (source_package_path, result_package_path):
        try:
            file_transfer_token.sig = None
            cluster_response = send_request_to_storage_cluster(
                prepare_storage_request_headers(file_transfer_token),
                settings.STORAGE_CLUSTER_ADDRESS + CLUSTER_DOWNLOAD_PATH + file_path,
                method='get',
            )
            store_file_from_response_in_chunks(
                cluster_response,
                os.path.join(
                    settings.VERIFIER_STORAGE_PATH,
                    os.path.split(file_path)[0],
                )
            )

        except (OSError, HTTPError) as exception:
            logger.info('blender_verification_order for SUBTASK_ID {subtask_id} failed with error {exception}.')
            verification_result.delay(
                subtask_id,
                VerificationResult.ERROR,
                str(exception),
                ErrorCode.VERIFIIER_FILE_DOWNLOAD_FAILED
            )
            return
        except Exception as exception:
            logger.info('blender_verification_order for SUBTASK_ID {subtask_id} failed with error {exception}.')
            verification_result.delay(
                subtask_id,
                VerificationResult.ERROR,
                str(exception),
                ErrorCode.VERIFIIER_FILE_DOWNLOAD_FAILED
            )
            raise

    # Verifier runs blender
    run_blender()

    # Verifier unpacks the archive with project source.
    for file_path in (source_package_path, result_package_path):
        try:
            unpack_archive(file_path)
        except (OSError, BadZipFile) as e:
            verification_result.delay(
                subtask_id,
                VerificationResult.ERROR,
                str(e),
                ErrorCode.VERIFIIER_UNPACKING_ARCHIVE_FAILED
            )
            return

    verification_result.delay(
        subtask_id,
        VerificationResult.MATCH,
    )


@shared_task(bind=True)
@transaction.atomic(using='control')
def verification_result(
    self,
    subtask_id: str,
    result: VerificationResult,
    error_message: Optional[str] = None,
    error_code: Optional[ErrorCode] = None,
):
    logger.info(f'verification_result_task starts with: SUBTASK_ID {subtask_id} -- RESULT {result}')

    assert isinstance(subtask_id, str)
    assert isinstance(result, VerificationResult)
    assert isinstance(error_message, (str, type(None)))
    assert isinstance(error_code, (ErrorCode, type(None)))
    assert all([error_message, error_code]) if result == VerificationResult.ERROR else True

    # Worker locks database row corresponding to the subtask in the subtask table.
    try:
        subtask = Subtask.objects.select_for_update(nowait=True).get(subtask_id=subtask_id)
    except DatabaseError:
        logging.warning(
            f'Subtask object with ID {subtask_id} database row is locked, '
            f'retrying task {self.request.retries}/{self.max_retries}'
        )
        # If the row is already locked, task fails so that Celery can retry later.
        self.retry(
            countdown=CELERY_LOCKED_SUBTASK_DELAY,
            max_retries=MAXIMUM_VERIFICATION_RESULT_TASK_RETRIES,
            throw=False,
        )
        return

    if subtask.state_enum == Subtask.SubtaskState.ACCEPTED:
        logger.warning(VERIFICATION_RESULT_SUBTASK_STATE_ACCEPTED_LOG_MESSAGE.format(subtask_id))
        return

    elif subtask.state_enum == Subtask.SubtaskState.FAILED:
        logger.warning(VERIFICATION_RESULT_SUBTASK_STATE_FAILED_LOG_MESSAGE.format(subtask_id))
        return

    elif subtask.state_enum != Subtask.SubtaskState.ADDITIONAL_VERIFICATION:
        logger.error(VERIFICATION_RESULT_SUBTASK_STATE_UNEXPECTED_LOG_MESSAGE.format(subtask_id, subtask.state))
        return

    # If the time is already past next_deadline for the subtask (SubtaskResultsRejected.timestamp + AVCT)
    # worker ignores worker's message and processes the timeout.
    if subtask.next_deadline < parse_timestamp_to_utc_datetime(get_current_utc_timestamp()):
        task_to_compute = deserialize_message(subtask.task_to_compute.data.tobytes())
        # Worker makes a payment from requestor's deposit just like in the forced acceptance use case.
        base.make_force_payment_to_provider(  # pylint: disable=no-value-for-parameter
            requestor_eth_address=task_to_compute.requestor_ethereum_address,
            provider_eth_address=task_to_compute.provider_ethereum_address,
            value=task_to_compute.price,
            payment_ts=get_current_utc_timestamp(),
        )

        update_subtask_state(
            subtask=subtask,
            state=Subtask.SubtaskState.ACCEPTED.name,  # pylint: disable=no-member
        )
        for public_key in [subtask.provider.public_key_bytes, subtask.requestor.public_key_bytes]:
            store_pending_message(
                response_type=PendingResponse.ResponseType.SubtaskResultsSettled,
                client_public_key=public_key,
                queue=PendingResponse.Queue.ReceiveOutOfBand,
                subtask=subtask,
            )
        return

    if result == VerificationResult.MISMATCH:
        # Worker adds SubtaskResultsRejected to provider's and requestor's receive queues (both out-of-band)
        for public_key in [subtask.provider.public_key_bytes, subtask.requestor.public_key_bytes]:
            store_pending_message(
                response_type=PendingResponse.ResponseType.SubtaskResultsRejected,
                client_public_key=public_key,
                queue=PendingResponse.Queue.ReceiveOutOfBand,
                subtask=subtask,
            )

        # Worker changes subtask state to FAILED
        subtask.state = Subtask.SubtaskState.FAILED.name  # pylint: disable=no-member
        subtask.next_deadline = None
        subtask.full_clean()
        subtask.save()

    elif result in (VerificationResult.MATCH, VerificationResult.ERROR):
        # Worker logs the error code and message
        if result == VerificationResult.ERROR:
            logger.info(
                f'verification_result_task processing error result with: '
                f'SUBTASK_ID {subtask_id} -- RESULT {result} -- ERROR MESSAGE {error_message} -- ERROR CODE {error_code}'
            )

        task_to_compute = deserialize_message(subtask.task_to_compute.data.tobytes())

        # Worker makes a payment from requestor's deposit just like in the forced acceptance use case.
        base.make_force_payment_to_provider(  # pylint: disable=no-value-for-parameter
            requestor_eth_address=task_to_compute.requestor_ethereum_address,
            provider_eth_address=task_to_compute.provider_ethereum_address,
            value=task_to_compute.price,
            payment_ts=get_current_utc_timestamp(),
        )

        # Worker adds SubtaskResultsSettled to provider's and requestor's receive queues (both out-of-band)
        for public_key in [subtask.provider.public_key_bytes, subtask.requestor.public_key_bytes]:
            store_pending_message(
                response_type=PendingResponse.ResponseType.SubtaskResultsSettled,
                client_public_key=public_key,
                queue=PendingResponse.Queue.ReceiveOutOfBand,
                subtask=subtask,
            )

        # Worker changes subtask state to ACCEPTED
        update_subtask_state(
            subtask=subtask,
            state=Subtask.SubtaskState.ACCEPTED.name,  # pylint: disable=no-member
        )

    logger.info(f'verification_result_task ends with: SUBTASK_ID {subtask_id} -- RESULT {result}')
