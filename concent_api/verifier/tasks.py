from subprocess import SubprocessError
from zipfile import BadZipFile
import hashlib
import logging
import os

from celery import shared_task
from golem_messages import message
from requests import HTTPError
from skimage.measure import compare_ssim
import cv2

from django.conf import settings

from conductor.models import BlenderSubtaskDefinition
from core.constants import VerificationResult
from core.tasks import verification_result
from core.transfer_operations import create_file_transfer_token_for_concent
from core.transfer_operations import send_request_to_storage_cluster
from gatekeeper.constants import CLUSTER_DOWNLOAD_PATH
from common.constants import ErrorCode
from common.decorators import log_task_errors
from common.decorators import provides_concent_feature
from common.logging import log_string_message
from common.helpers import upload_file_to_storage_cluster
from .exceptions import VerificationError
from .utils import clean_directory
from .utils import delete_file
from .utils import generate_blender_output_file_name
from .utils import generate_upload_file_name
from .utils import generate_verifier_storage_file_path
from .utils import get_files_list_from_archive
from .utils import prepare_storage_request_headers
from .utils import run_blender
from .utils import store_file_from_response_in_chunks
from .utils import unpack_archive


crash_logger = logging.getLogger('concent.crash')
logger = logging.getLogger(__name__)


@shared_task
@provides_concent_feature('verifier')
@log_task_errors
def blender_verification_order(
    subtask_id: str,
    source_package_path: str,
    source_size: int,
    source_package_hash: str,
    result_package_path: str,
    result_size: int,
    result_package_hash: str,
    output_format: str,
    scene_file: str,
):
    log_string_message(
        logger,
        f'Blender_verification_order_starts. SUBTASK_ID: {subtask_id}.',
        f'Source_package_path: {source_package_path}.',
        f'Source_size: {source_size}.',
        f'Source_package_hash: {source_package_hash}.',
        f'Result_package_path: {result_package_path}.',
        f'Result_size: {result_size}.',
        f'Result_package_hash: {result_package_hash}.',
        f'Output_format: {output_format}.',
        f'Scene_file: {scene_file}.'
    )

    assert output_format in BlenderSubtaskDefinition.OutputFormat.__members__.keys()
    assert source_package_path != result_package_path
    assert source_package_hash != result_package_hash
    assert (source_size and source_package_hash and source_package_path) and (result_size and result_package_hash and result_package_path)
    assert isinstance(subtask_id, str)

    # this is a temporary hack - dummy verification which's result depends on subtask_id only

    if settings.MOCK_VERIFICATION_ENABLED:
        result = VerificationResult.MATCH.name if subtask_id[-1] == 'm' else VerificationResult.MISMATCH.name
        if subtask_id[-1] == 'm':
            verification_result.delay(
                subtask_id,
                result,
            )
        log_string_message(
            logger,
            f'Temporary hack, verification result depends on subtask_id only - SUBTASK_ID: {subtask_id}. Result: {result}'
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

    package_paths_to_downloaded_file_names = {
        source_package_path: f'source_{os.path.basename(source_package_path)}',
        result_package_path: f'result_{os.path.basename(result_package_path)}',
    }

    # Download all the files listed in the message from the storage server to local storage.
    for file_path, download_file_name in package_paths_to_downloaded_file_names.items():
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
                    download_file_name,
                )
            )
        except (OSError, HTTPError) as exception:
            log_string_message(
                logger,
                f'blender_verification_order for SUBTASK_ID {subtask_id} failed with error {exception}.'
                f'ErrorCode: {ErrorCode.VERIFIER_FILE_DOWNLOAD_FAILED.name}'
            )
            verification_result.delay(
                subtask_id,
                VerificationResult.ERROR.name,
                str(exception),
                ErrorCode.VERIFIER_FILE_DOWNLOAD_FAILED.name
            )
            return
        except Exception as exception:
            log_string_message(
                logger,
                f'blender_verification_order for SUBTASK_ID {subtask_id} failed with error {exception}.'
                f'ErrorCode: {ErrorCode.VERIFIER_FILE_DOWNLOAD_FAILED.name}'
            )
            verification_result.delay(
                subtask_id,
                VerificationResult.ERROR.name,
                str(exception),
                ErrorCode.VERIFIER_FILE_DOWNLOAD_FAILED.name
            )
            raise

    # If any file which is supposed to be unpacked from archives already exists, finish with error and raise exception.
    for package_file_path in (source_package_path, result_package_path):
        package_files_list = get_files_list_from_archive(
            generate_verifier_storage_file_path(package_file_path)
        )
        if list(set(os.listdir(settings.VERIFIER_STORAGE_PATH)).intersection(package_files_list)):
            verification_result.delay(
                subtask_id,
                VerificationResult.ERROR.name,
                f'One of the files which are supposed to be unpacked from {package_file_path} already exists.',
                ErrorCode.VERIFIER_UNPACKING_ARCHIVE_FAILED.name
            )
            raise VerificationError(  # TODO: write a test for this case
                f'One of the files which are supposed to be unpacked from {package_file_path} already exists.',
                ErrorCode.VERIFIER_UNPACKING_ARCHIVE_FAILED.name,
            )

    # Verifier unpacks the archive with project source.
    for file_path, download_file_name in package_paths_to_downloaded_file_names.items():
        try:
            unpack_archive(
                os.path.basename(file_path)
            )
        except BadZipFile as exception:
            log_string_message(
                logger,
                f'Verifier failed to unpack the archive with project source with error {exception} '
                f'SUBTASK_ID {subtask_id}. '
                f'ErrorCode: {ErrorCode.VERIFIER_UNPACKING_ARCHIVE_FAILED.name}'
            )
            verification_result.delay(
                subtask_id,
                VerificationResult.ERROR.name,
                str(exception),
                ErrorCode.VERIFIER_UNPACKING_ARCHIVE_FAILED.name
            )
            return

    # Verifier runs blender process.
    try:
        completed_process = run_blender(
            scene_file,
            output_format,
        )
        # If Blender finishes with errors, verification ends here
        # Verification_result informing about the error is sent to the work queue.
        if completed_process.returncode != 0:
            log_string_message(
                logger,
                'Blender finished with errors',
                f'SUBTASK_ID: {subtask_id}.'
                f'Returncode: {str(completed_process.returncode)}.'
                f'stderr: {str(completed_process.stderr)}.'
                f'stdout: {str(completed_process.stdout)}.'
            )
            verification_result.delay(
                subtask_id,
                VerificationResult.ERROR.name,
                str(completed_process.stderr),
                ErrorCode.VERIFIER_RUNNING_BLENDER_FAILED.name
            )
            return
    except SubprocessError as exception:
        log_string_message(logger, f'Blender finished with errors. Error: {exception} SUBTASK_ID {subtask_id}')
        verification_result.delay(
            subtask_id,
            VerificationResult.ERROR.name,
            str(exception),
            ErrorCode.VERIFIER_RUNNING_BLENDER_FAILED.name
        )
        return

    # Verifier deletes source files of the Blender project from its storage.
    # At this point there must be source files in VERIFIER_STORAGE_PATH otherwise verification should fail before.
    source_files_list = get_files_list_from_archive(
        generate_verifier_storage_file_path(source_package_path)
    )
    for file_path in source_files_list + [package_paths_to_downloaded_file_names[source_package_path]]:
        delete_file(file_path)
    log_string_message(
        logger,
        f'Blender finished successfully. SUBTASK_ID: {subtask_id}.'
        f'VerificationResult: {VerificationResult.MATCH.name}'
    )

    blender_output_file_name = generate_blender_output_file_name(scene_file)
    upload_file_name = generate_upload_file_name(subtask_id, output_format)

    # Read Blender output file.
    try:
        with open(generate_verifier_storage_file_path(blender_output_file_name), 'r') as upload_file:
            upload_file_content = upload_file.read()
    except OSError as exception:
        upload_file_content = None
        crash_logger.error(str(exception))
    except MemoryError as exception:
        logger.error(f'Loading result files into memory failed with: {exception}')
        verification_result.delay(
            subtask_id,
            VerificationResult.ERROR.name,
            str(exception),
            ErrorCode.VERIFIER_LOADING_FILES_INTO_MEMORY_FAILED.name
        )
        return

    # If reading Blender output file has not failed, upload it to storage cluster.
    if upload_file_content is not None:
        upload_file_size = len(upload_file_content)
        upload_file_checksum = 'sha1:' + hashlib.sha1(upload_file_content.encode()).hexdigest()

        # Generate a FileTransferToken valid for an upload of the image generated by blender.
        upload_file_transfer_token = create_file_transfer_token_for_concent(
            subtask_id=subtask_id,
            result_package_path=upload_file_name,
            result_size=upload_file_size,
            result_package_hash=upload_file_checksum,
            operation=message.FileTransferToken.Operation.upload,
        )

        # Upload the image.
        upload_file_to_storage_cluster(
            upload_file_content,
            upload_file_name,
            upload_file_transfer_token,
            settings.CONCENT_PRIVATE_KEY,
            settings.CONCENT_PUBLIC_KEY,
            settings.CONCENT_PUBLIC_KEY,
            settings.STORAGE_CLUSTER_ADDRESS,
        )

    # Read both files with OpenCV.
    try:
        result_files_list = get_files_list_from_archive(
            generate_verifier_storage_file_path(result_package_path)
        )

        image_1 = cv2.imread(  # pylint: disable=no-member
            generate_verifier_storage_file_path(blender_output_file_name)
        )
        image_2 = cv2.imread(  # pylint: disable=no-member
            generate_verifier_storage_file_path(result_files_list[0])
        )
    except MemoryError as exception:
        logger.info(f'Loading result files into memory exceeded available memory and failed with: {exception}')
        verification_result.delay(
            subtask_id,
            VerificationResult.ERROR.name,
            str(exception),
            ErrorCode.VERIFIER_LOADING_FILES_INTO_MEMORY_FAILED.name
        )
        return

    # If loading fails because of wrong path, cv2.imread does not raise any error but returns None.
    if image_1 is None or image_2 is None:
        logger.info('Loading files using OpenCV fails.')
        verification_result.delay(
            subtask_id,
            VerificationResult.ERROR.name,
            'Loading files using OpenCV fails.',
            ErrorCode.VERIFIER_LOADING_FILES_WITH_OPENCV_FAILED.name
        )
        return

    # Compute SSIM for the image pair.
    try:
        ssim = compare_ssim(image_1, image_2)
    except ValueError as exception:
        logger.info(f'Computing SSIM fails with: {exception}')
        verification_result.delay(
            subtask_id,
            VerificationResult.ERROR.name,
            str(exception),
            ErrorCode.VERIFIER_COMPUTING_SSIM_FAILED.name
        )
        return

    assert isinstance(ssim, float)

    # Compare SSIM with VERIFIER_MIN_SSIM.
    if settings.VERIFIER_MIN_SSIM < ssim:
        verification_result.delay(
            subtask_id,
            VerificationResult.MATCH.name,
        )
    else:
        verification_result.delay(
            subtask_id,
            VerificationResult.MISMATCH.name,
        )

    # Remove any files left in VERIFIER_STORAGE_PATH.
    clean_directory(settings.VERIFIER_STORAGE_PATH)
