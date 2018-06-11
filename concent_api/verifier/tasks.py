from zipfile import BadZipFile
from subprocess import SubprocessError
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
import core.payments.base
from core.models import PendingResponse
from core.models import Subtask
from core.subtask_helpers import update_subtask_state
from core.transfer_operations import create_file_transfer_token_for_concent
from core.transfer_operations import send_request_to_storage_cluster
from core.transfer_operations import store_pending_message
from gatekeeper.constants import CLUSTER_DOWNLOAD_PATH
from utils.constants import ErrorCode
from utils.decorators import provides_concent_feature
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
from .utils import delete_file
from .utils import get_files_list_from_archive
from .utils import prepare_storage_request_headers
from .utils import run_blender
from .utils import store_file_from_response_in_chunks
from .utils import unpack_archive


logger = logging.getLogger(__name__)


@shared_task
@provides_concent_feature('verifier')
def blender_verification_order(
    subtask_id: str,
    source_package_path: str,
    source_size: int,
    source_package_hash: str,
    result_package_path: str,
    result_size: int,
    result_package_hash: str,
    output_format: str,
    scene_file: str,  # pylint: disable=unused-argument
):
    assert output_format in BlenderSubtaskDefinition.OutputFormat.__members__.keys()
    assert source_package_path != result_package_path
    assert source_package_hash != result_package_hash
    assert (source_size and source_package_hash and source_package_path) and (result_size and result_package_hash and result_package_path)
    assert isinstance(subtask_id, str)

    # this is a temporary hack - dummy verification which's result depends on subtask_id only
    if settings.MOCK_VERIFICATION_ENABLED:
        if subtask_id[-1] == 'm':
            verification_result.delay(
                subtask_id,
                VerificationResult.MATCH.name,
            )
        else:
            verification_result.delay(
                subtask_id,
                VerificationResult.MISMATCH.name,
            )
        return

    # Generate a FileTransferToken valid for a download of any file listed in the order.
    file_transfer_token = create_file_transfer_token_for_concent(
        subtask_id=subtask_id,
        source_package_path=source_package_path,
        source_size=source_size,
        source_package_hash=source_package_hash,
        result_package_path=result_package_path,
        result_size=result_size,
        result_package_hash=result_package_hash,
        operation=message.FileTransferToken.Operation.download,
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
                    os.path.basename(file_path),
                )
            )

        except (OSError, HTTPError) as exception:
            logger.info(f'blender_verification_order for SUBTASK_ID {subtask_id} failed with error {exception}.')
            verification_result.delay(
                subtask_id,
                VerificationResult.ERROR.name,
                str(exception),
                ErrorCode.VERIFIIER_FILE_DOWNLOAD_FAILED.name
            )
            return
        except Exception as exception:
            logger.info(f'blender_verification_order for SUBTASK_ID {subtask_id} failed with error {exception}.')
            verification_result.delay(
                subtask_id,
                VerificationResult.ERROR.name,
                str(exception),
                ErrorCode.VERIFIIER_FILE_DOWNLOAD_FAILED.name
            )
            raise

    # Verifier unpacks the archive with project source.
    for file_path in (source_package_path, result_package_path):
        try:
            unpack_archive(
                os.path.basename(file_path)
            )
        except (OSError, BadZipFile) as e:
            verification_result.delay(
                subtask_id,
                VerificationResult.ERROR.name,
                str(e),
                ErrorCode.VERIFIIER_UNPACKING_ARCHIVE_FAILED.name
            )
            return

    # Verifier runs blender process.
    try:
        completed_process = run_blender(
            scene_file,
            output_format,
        )
        logger.info(f'Blender process std_out: {completed_process.stdout}')
        logger.info(f'Blender process std_err: {completed_process.stdout}')

        # If Blender finishes with errors, verification ends here
        # Verification_result informing about the error is sent to the work queue.
        if completed_process.returncode != 0:
            verification_result.delay(
                subtask_id,
                VerificationResult.ERROR,
                str(completed_process.stderr),
                'verifier.blender_verification_order.running_blender'
            )
            return
    except SubprocessError as e:
        verification_result.delay(
            subtask_id,
            VerificationResult.ERROR,
            str(e),
            'verifier.blender_verification_order.running_blender'
        )
        return

    # Verifier deletes source files of the Blender project from its storage.
    # At this point there must be source files in VERIFIER_STORAGE_PATH otherwise verification should fail before.
    source_files_list = get_files_list_from_archive(
        os.path.join(settings.VERIFIER_STORAGE_PATH, source_package_path)
    )
    for file_path in source_files_list + [source_package_path]:
        delete_file(file_path)

    verification_result.delay(
        subtask_id,
        VerificationResult.MATCH.name,
    )


@shared_task(bind=True)
@provides_concent_feature('concent-worker')
@transaction.atomic(using='control')
def verification_result(
    self,
    subtask_id: str,
    result: str,
    error_message: Optional[str] = None,
    error_code: Optional[str] = None,
):
    logger.info(f'verification_result_task starts with: SUBTASK_ID {subtask_id} -- RESULT {result}')

    assert isinstance(subtask_id, str)
    assert isinstance(result, str)
    assert result in VerificationResult.__members__.keys()
    assert isinstance(error_message, (str, type(None)))
    assert isinstance(error_code, (str, type(None)))

    result_enum = VerificationResult[result]

    assert result_enum != VerificationResult.ERROR or all([error_message, error_code])

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
        core.payments.base.make_force_payment_to_provider(  # pylint: disable=no-value-for-parameter
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

    if result_enum == VerificationResult.MISMATCH:
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

    elif result_enum in (VerificationResult.MATCH, VerificationResult.ERROR):
        # Worker logs the error code and message
        if result_enum == VerificationResult.ERROR:
            logger.info(
                f'verification_result_task processing error result with: '
                f'SUBTASK_ID {subtask_id} -- RESULT {result_enum.name} -- ERROR MESSAGE {error_message} -- ERROR CODE {error_code}'
            )

        task_to_compute = deserialize_message(subtask.task_to_compute.data.tobytes())

        # Worker makes a payment from requestor's deposit just like in the forced acceptance use case.
        core.payments.base.make_force_payment_to_provider(  # pylint: disable=no-value-for-parameter
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

    logger.info(f'verification_result_task ends with: SUBTASK_ID {subtask_id} -- RESULT {result_enum.name}')
