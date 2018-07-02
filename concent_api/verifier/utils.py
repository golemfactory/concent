import hashlib
from base64 import b64encode
import logging
import os
import subprocess
import zipfile

import requests

from django.conf import settings
from golem_messages import message
from golem_messages.shortcuts import dump
from numpy.core.records import ndarray
from skimage.measure import compare_ssim


from common.constants import ErrorCode
from common.helpers import upload_file_to_storage_cluster
from common.logging import log_string_message
from core.constants import VerificationResult
from core.tasks import verification_result
from core.transfer_operations import create_file_transfer_token_for_concent, send_request_to_storage_cluster
from gatekeeper.constants import CLUSTER_DOWNLOAD_PATH
from verifier.exceptions import VerificationError

from .constants import UNPACK_CHUNK_SIZE


logger = logging.getLogger(__name__)
crash_logger = logging.getLogger('concent.crash')


def clean_directory(directory_path: str):
    """ Removes all files from given directory path. """
    for file in os.listdir(directory_path):
        file_path = os.path.join(directory_path, file)
        try:
            if os.path.isfile(file_path):
                os.unlink(file_path)
        except OSError as exception:
            logger.warning(f'File {file} in directory {directory_path} was not deleted, exception: {exception}')


def prepare_storage_request_headers(file_transfer_token: message.FileTransferToken) -> dict:
    """ Prepare headers for request to storage cluster. """
    dumped_file_transfer_token = dump(
        file_transfer_token,
        settings.CONCENT_PRIVATE_KEY,
        settings.CONCENT_PUBLIC_KEY,
    )
    headers = {
        'Authorization': 'Golem ' + b64encode(dumped_file_transfer_token).decode(),
        'Concent-Auth': b64encode(
            dump(
                message.concents.ClientAuthorization(
                    client_public_key=settings.CONCENT_PUBLIC_KEY,
                ),
                settings.CONCENT_PRIVATE_KEY,
                settings.CONCENT_PUBLIC_KEY
            ),
        ).decode(),
    }
    return headers


def store_file_from_response_in_chunks(response: requests.Response, file_path: str):
    with open(file_path, 'xb') as f:
        for chunk in response.iter_content():
            f.write(chunk)


def run_blender(scene_file, output_format, frame_number, script_file=''):
    output_format = adjust_format_name(output_format)
    return subprocess.run(
        [
            "blender",
            "-b", f"{generate_verifier_storage_file_path(scene_file)}",
            "-y",  # enable scripting by default
            "-P", f"{script_file}",
            "-o", f"{generate_base_blender_output_file_name(scene_file)}",
            "-noaudio",
            "-F", f"{output_format}",
            "-t", f"{settings.BLENDER_THREADS}",  # cpu_count
            "-f", f"{frame_number}",  # frame
        ],
        timeout=settings.BLENDER_MAX_RENDERING_TIME,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def adjust_format_name(output_format: str):
    """
    This function enforces the upper case for format name.
    For desired JPG format, the parameter for blender should be JPEG and the extension of result file is *.jpg.
    """
    if output_format.upper() == 'JPG':
        return 'JPEG'
    return output_format.upper()


def unpack_archive(file_path):
    """ Unpacks archive in chunks. """
    with zipfile.ZipFile(os.path.join(settings.VERIFIER_STORAGE_PATH, file_path), 'r') as zip_file:
        infos = zip_file.infolist()
        for ix in range(0, min(UNPACK_CHUNK_SIZE, len(infos))):
            zip_file.extract(infos[ix], settings.VERIFIER_STORAGE_PATH)
        zip_file.close()


def get_files_list_from_archive(file_path):
    """ Returns list of files from given zip archive. """
    return zipfile.ZipFile(file_path).namelist()


def delete_file(file_path):
    file_path = os.path.join(settings.VERIFIER_STORAGE_PATH, file_path)
    try:
        if os.path.isfile(file_path):
            os.unlink(file_path)
    except OSError as exception:
        logger.warning(f'File with path {file_path} was not deleted, exception: {exception}')


def generate_full_blender_output_file_name(scene_file, frame_number, output_format):
    base_blender_output_file_name = generate_base_blender_output_file_name(scene_file)
    return f'{base_blender_output_file_name}{frame_number:>04}.{output_format}'


def generate_base_blender_output_file_name(scene_file):
    return f'{settings.VERIFIER_STORAGE_PATH}/out_{scene_file}_'


def generate_upload_file_path(subtask_id, extension):
    return f'blender/verifier-output/{subtask_id}/{subtask_id}.{extension.lower()}'


def generate_verifier_storage_file_path(file_name):
    return os.path.join(settings.VERIFIER_STORAGE_PATH, file_name)


def are_image_sizes_and_color_channels_equal(image1: ndarray, image2: ndarray) -> bool:
    return image1.shape == image2.shape


def import_cv2():
    import cv2
    return cv2


def compare_images(image_1, image_2, subtask_id):
    # Compute SSIM for the image pair.
    try:
        ssim = compare_ssim(image_1, image_2, multichannel=True)
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
                settings.STORAGE_SERVER_INTERNAL_ADDRESS,
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
    except subprocess.SubprocessError as exception:
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
        except zipfile.BadZipFile as exception:
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
                settings.STORAGE_SERVER_INTERNAL_ADDRESS + CLUSTER_DOWNLOAD_PATH + file_path,
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
