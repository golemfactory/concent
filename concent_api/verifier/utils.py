import hashlib
from base64 import b64encode
from typing import Dict
from typing import List
import logging
import os
import re
import subprocess
import zipfile

from django.conf import settings
from golem_messages import message
from golem_messages.shortcuts import dump
from mypy.types import Optional
from numpy.core.records import ndarray
from skimage.measure import compare_ssim
import requests

from common.constants import ErrorCode
from common.helpers import get_current_utc_timestamp
from common.helpers import upload_file_to_storage_cluster
from common.logging import log_string_message
from conductor.models import BlenderSubtaskDefinition
from core.constants import VerificationResult
from core.tasks import verification_result
from core.transfer_operations import create_file_transfer_token_for_concent, send_request_to_storage_cluster
from gatekeeper.constants import CLUSTER_DOWNLOAD_PATH
from verifier.exceptions import VerificationError
from verifier.exceptions import VerificationMismatch
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


def run_blender(
    scene_file: str,
    output_format: str,
    frame_number: int,
    verification_deadline: int,
    script_file: Optional[str],
) -> subprocess.CompletedProcess:
    output_format = adjust_format_name(output_format)

    blender_command = [
        "blender",
        "-b", f"{generate_verifier_storage_file_path(scene_file)}",
    ]

    if script_file is not None:
        blender_command += [
            "-y",  # enable scripting by default
            "-P", f"{generate_verifier_storage_file_path(script_file)}",
        ]

    blender_command += [
        "-o", f"{generate_base_blender_output_file_name(scene_file)}",
        "-noaudio",
        "-F", f"{output_format}",
        "-t", f"{settings.BLENDER_THREADS}",  # cpu_count
        "-f", f"{frame_number}",  # frame
    ]
    return subprocess.run(
        blender_command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=(verification_deadline - get_current_utc_timestamp()),
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
    return os.path.join(settings.VERIFIER_STORAGE_PATH, f'out_{scene_file}_')


def generate_upload_file_path(subtask_id, extension, frame_number):
    return f'blender/verifier-output/{subtask_id}/{subtask_id}_{frame_number:>04}.{extension.lower()}'


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
    return ssim


def compare_minimum_ssim_with_results(ssim_list, subtask_id):
    # Compare SSIM with VERIFIER_MIN_SSIM.
    if settings.VERIFIER_MIN_SSIM < min(ssim_list):
        verification_result.delay(
            subtask_id,
            VerificationResult.MATCH.name,
        )
        return
    else:
        raise VerificationMismatch(subtask_id=subtask_id)


def load_images(blender_output_file_name, result_file, subtask_id):
    # Read both files with OpenCV.
    cv2 = import_cv2()
    try:
        image_1 = cv2.imread(  # pylint: disable=no-member
            generate_verifier_storage_file_path(blender_output_file_name)
        )

        image_2 = cv2.imread(  # pylint: disable=no-member
            result_file
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


def try_to_upload_blender_output_file(blender_output_file_name, output_format, subtask_id, frame_number):
    upload_file_path = generate_upload_file_path(subtask_id, output_format, frame_number)
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


def render_image(frame_number, output_format, scene_file, subtask_id, verification_deadline, blender_crop_script=None):
    # Verifier stores Blender crop script to a file.
    if blender_crop_script is not None:
        blender_script_file_name = store_blender_script_file(subtask_id, blender_crop_script)
    else:
        blender_script_file_name = None

    # Verifier runs blender process.
    try:
        completed_process = run_blender(
            scene_file,
            output_format,
            frame_number,
            verification_deadline,
            blender_script_file_name,
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


def parse_result_files_with_frames(frames: List[int], result_files_list: List[str], output_format: str):
    frames_to_result_files_map = {}  # type: Dict[int, List[str]]
    for frame_number in frames:
        for result_file_name in result_files_list:
            if (
                re.search(f'_{frame_number:>04}.{output_format.lower()}$', result_file_name) is not None and
                result_file_name not in frames_to_result_files_map.values()
            ):
                frames_to_result_files_map[frame_number] = [generate_verifier_storage_file_path(result_file_name)]
    return frames_to_result_files_map


def render_images_by_frames(
    parsed_files_to_compare: Dict[int, List[str]],
    frames: List[int],
    output_format: BlenderSubtaskDefinition.OutputFormat,
    scene_file: str,
    subtask_id: str,
    verification_deadline: int,
    blender_crop_script: Optional[str],
):
    blender_output_file_name_list = []
    for frame_number in frames:
        render_image(frame_number, output_format.name, scene_file, subtask_id, verification_deadline, blender_crop_script)
        blender_out_file_name = generate_full_blender_output_file_name(scene_file, frame_number, output_format.name.lower())
        blender_output_file_name_list.append(blender_out_file_name)
        parsed_files_to_compare[frame_number].append(blender_out_file_name)
    return (blender_output_file_name_list, parsed_files_to_compare)


def upload_blender_output_file(
    frames: List[int],
    blender_output_file_name_list: List[str],
    output_format: BlenderSubtaskDefinition.OutputFormat,
    subtask_id: str
):
    for (frame_number, blender_output_file_name) in zip(frames, blender_output_file_name_list):
        try_to_upload_blender_output_file(blender_output_file_name, output_format.name, subtask_id, frame_number)


def ensure_enough_result_files_provided(frames: List[int], result_files_list: List[str], subtask_id: str):
    if len(frames) > len(result_files_list):
        raise VerificationMismatch(subtask_id=subtask_id)

    elif len(frames) < len(result_files_list):
        logger.warning(f'There is more result files than frames to render')


def ensure_frames_have_related_files_to_compare(frames: List[int], parsed_files_to_compare: Dict[int, List[str]], subtask_id: str):
    if len(frames) != len(parsed_files_to_compare):
        raise VerificationMismatch(subtask_id=subtask_id)


def compare_all_rendered_images_with_user_results_files(parsed_files_to_compare: Dict[int, List[str]], subtask_id: str):
    ssim_list = []
    for (result_file, blender_output_file_name) in parsed_files_to_compare.values():
        image_1, image_2 = load_images(
            blender_output_file_name,
            result_file,
            subtask_id
        )
        if not are_image_sizes_and_color_channels_equal(image_1, image_2):
            log_string_message(
                logger,
                f'Blender verification failed. Sizes in pixels of images are not equal. SUBTASK_ID: {subtask_id}.'
                f'VerificationResult: {VerificationResult.MISMATCH.name}'
            )
            raise VerificationMismatch(subtask_id=subtask_id)

        ssim_list.append(compare_images(image_1, image_2, subtask_id))
    return ssim_list


def store_blender_script_file(subtask_id, blender_crop_script):
    """ Writes content of the Blender crop script to python script file. """
    blender_script_file_name = f'blender_crop_script_{subtask_id}.py'
    with open(generate_verifier_storage_file_path(blender_script_file_name), 'x') as blender_script_file:
        blender_script_file.write(blender_crop_script)

    return blender_script_file_name
