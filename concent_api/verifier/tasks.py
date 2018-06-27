from subprocess import SubprocessError
from typing import Optional  # noqa flake8 F401 issue  # pylint: disable=unused-import
from zipfile import BadZipFile
import hashlib
import logging
import os

from celery import shared_task
from golem_messages import message
from skimage.measure import compare_ssim

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
from verifier.decorators import handle_verification_errors
from .exceptions import VerificationError
from .utils import are_image_sizes_and_color_channels_equal
from .utils import clean_directory
from .utils import delete_file
from .utils import generate_full_blender_output_file_name
from .utils import generate_upload_file_path
from .utils import generate_verifier_storage_file_path
from .utils import get_files_list_from_archive
from .utils import prepare_storage_request_headers
from .utils import run_blender
from .utils import store_file_from_response_in_chunks
from .utils import unpack_archive


crash_logger = logging.getLogger('concent.crash')
logger = logging.getLogger(__name__)


def import_cv2():
    import cv2
    return cv2


@shared_task
@provides_concent_feature('verifier')
@handle_verification_errors
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

    package_paths_to_downloaded_archive_names = {
        source_package_path: f'source_{os.path.basename(source_package_path)}',
        result_package_path: f'result_{os.path.basename(result_package_path)}',
    }

    download_archives_from_storage(
        file_transfer_token,
        subtask_id,
        package_paths_to_downloaded_archive_names
    )

    validate_downloaded_archives(subtask_id, package_paths_to_downloaded_archive_names.values())

    unpack_archives(package_paths_to_downloaded_archive_names.values(), subtask_id)

    frame_number = 1
    render_image(frame_number, output_format, scene_file, subtask_id)

    delete_source_files(package_paths_to_downloaded_archive_names[source_package_path])

    blender_output_file_name = generate_full_blender_output_file_name(scene_file, frame_number, output_format.lower())
    try_to_upload_blender_output_file(blender_output_file_name, output_format, subtask_id)

    image_1, image_2 = load_images(
        blender_output_file_name,
        package_paths_to_downloaded_archive_names[result_package_path],
        subtask_id
    )
    if not are_image_sizes_and_color_channels_equal(image_1, image_2):
        log_string_message(
            logger,
            f'Blender verification failed. Sizes in pixels of images are not equal. SUBTASK_ID: {subtask_id}.'
            f'VerificationResult: {VerificationResult.MISMATCH.name}'
        )
        verification_result.delay(
            subtask_id,
            VerificationResult.MISMATCH.name,
        )
        return

    compare_images(image_1, image_2, subtask_id)


def compare_images(image_1, image_2, subtask_id):
    # Compute SSIM for the image pair.
    try:
        ssim = compare_ssim(image_1, image_2)
    except ValueError as exception:
        logger.info(f'Computing SSIM fails with: {exception}')
        raise VerificationError(
            str(exception),
            ErrorCode.VERIFIER_COMPUTING_SSIM_FAILED,
            subtask_id,
        )
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


def load_images(blender_output_file_name, result_archive_name, subtask_id):
    # Read both files with OpenCV.
    cv2 = import_cv2()
    try:
        result_files_list = get_files_list_from_archive(
            generate_verifier_storage_file_path(result_archive_name)
        )
        image_1 = cv2.imread(  # pylint: disable=no-member
            generate_verifier_storage_file_path(blender_output_file_name)
        )

        result_file_path_from_archive = generate_verifier_storage_file_path(result_files_list[0])  # TODO: What if list is longer?
        image_2 = cv2.imread(  # pylint: disable=no-member
            result_file_path_from_archive
        )
    except MemoryError as exception:
        logger.info(f'Loading result files into memory exceeded available memory and failed with: {exception}')
        raise VerificationError(
            str(exception),
            ErrorCode.VERIFIER_LOADING_FILES_INTO_MEMORY_FAILED,
            subtask_id,
        )
    # If loading fails because of wrong path, cv2.imread does not raise any error but returns None.
    if image_1 is None or image_2 is None:
        logger.info('Loading files using OpenCV fails.')
        raise VerificationError(
            'Loading files using OpenCV fails.',
            ErrorCode.VERIFIER_LOADING_FILES_WITH_OPENCV_FAILED,
            subtask_id,
        )
    return image_1, image_2


def try_to_upload_blender_output_file(blender_output_file_name, output_format, subtask_id):
    upload_file_path = generate_upload_file_path(subtask_id, output_format)
    # Read Blender output file.
    try:
        with open(generate_verifier_storage_file_path(blender_output_file_name), 'rb') as upload_file:
            upload_file_content = upload_file.read()  # type: Optional[bytes]
            upload_file_checksum = 'sha1:' + hashlib.sha1(upload_file_content).hexdigest()

            # Generate a FileTransferToken valid for an upload of the image generated by blender.
            upload_file_transfer_token = create_file_transfer_token_for_concent(
                subtask_id=subtask_id,
                result_package_path=upload_file_path,
                result_size=len(upload_file_content),
                result_package_hash=upload_file_checksum,
                operation=message.FileTransferToken.Operation.upload,
            )

            # Upload the image.
            upload_file_to_storage_cluster(
                upload_file_content,
                upload_file_path,
                upload_file_transfer_token,
                settings.CONCENT_PRIVATE_KEY,
                settings.CONCENT_PUBLIC_KEY,
                settings.CONCENT_PUBLIC_KEY,
                settings.STORAGE_CLUSTER_ADDRESS,
            )
    except OSError as exception:
        crash_logger.error(str(exception))
    except MemoryError as exception:
        logger.error(f'Loading result files into memory failed with: {exception}')
        raise VerificationError(
            str(exception),
            ErrorCode.VERIFIER_LOADING_FILES_INTO_MEMORY_FAILED,
            subtask_id,
        )


def delete_source_files(source_archive_name):
    # Verifier deletes source files of the Blender project from its storage.
    # At this point there must be source files in VERIFIER_STORAGE_PATH otherwise verification should fail before.
    source_files_list = get_files_list_from_archive(
        generate_verifier_storage_file_path(
            source_archive_name
        )
    )
    for file_path in source_files_list + [source_archive_name]:
        delete_file(file_path)


def render_image(frame_number, output_format, scene_file, subtask_id):
    # Verifier runs blender process.
    try:
        completed_process = run_blender(
            scene_file,
            output_format,
            frame_number,
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
            raise VerificationError(
                str(completed_process.stderr),
                ErrorCode.VERIFIER_RUNNING_BLENDER_FAILED,
                subtask_id,
            )
    except SubprocessError as exception:
        log_string_message(logger, f'Blender finished with errors. Error: {exception} SUBTASK_ID {subtask_id}')
        raise VerificationError(
            str(exception),
            ErrorCode.VERIFIER_RUNNING_BLENDER_FAILED,
            subtask_id,
        )


def unpack_archives(file_paths, subtask_id):
    # Verifier unpacks the archive with project source.
    for archive_file_path in file_paths:
        try:
            unpack_archive(
                os.path.basename(archive_file_path)
            )
        except BadZipFile as exception:
            log_string_message(
                logger,
                f'Verifier failed to unpack the archive with project source with error {exception} '
                f'SUBTASK_ID {subtask_id}. '
                f'ErrorCode: {ErrorCode.VERIFIER_UNPACKING_ARCHIVE_FAILED.name}'
            )
            raise VerificationError(
                str(exception),
                ErrorCode.VERIFIER_UNPACKING_ARCHIVE_FAILED,
                subtask_id,
            )


def validate_downloaded_archives(subtask_id, archives_list):
    # If any file which is supposed to be unpacked from archives already exists, finish with error and raise exception.

    for package_file_path in archives_list:
        package_files_list = get_files_list_from_archive(
            generate_verifier_storage_file_path(package_file_path)
        )
        if list(set(os.listdir(settings.VERIFIER_STORAGE_PATH)).intersection(package_files_list)):
            raise VerificationError(  # TODO: write a test for this case
                f'One of the files which are supposed to be unpacked from {package_file_path} already exists.',
                ErrorCode.ErrorCode.VERIFIER_UNPACKING_ARCHIVE_FAILED,
                subtask_id,
            )


def download_archives_from_storage(file_transfer_token, subtask_id, package_paths_to_downloaded_file_names):
    # Remove any files from VERIFIER_STORAGE_PATH.
    clean_directory(settings.VERIFIER_STORAGE_PATH)

    # Download all the files listed in the message from the storage server to local storage.
    for file_path, download_file_name in package_paths_to_downloaded_file_names.items():
        try:
            file_transfer_token.sig = None
            cluster_response = send_request_to_storage_cluster(
                prepare_storage_request_headers(file_transfer_token),
                settings.STORAGE_CLUSTER_ADDRESS + CLUSTER_DOWNLOAD_PATH + file_path,
                method='get',
            )
            path_to_store = os.path.join(settings.VERIFIER_STORAGE_PATH, download_file_name)
            store_file_from_response_in_chunks(
                cluster_response,
                path_to_store
            )
        except Exception as exception:
            log_string_message(
                logger,
                f'blender_verification_order for SUBTASK_ID {subtask_id} failed with error {exception}.'
                f'ErrorCode: {ErrorCode.VERIFIER_FILE_DOWNLOAD_FAILED.name}'
            )
            raise VerificationError(
                str(exception),
                ErrorCode.VERIFIER_FILE_DOWNLOAD_FAILED,
                subtask_id=subtask_id,
            )
