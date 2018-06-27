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

from .constants import UNPACK_CHUNK_SIZE


logger = logging.getLogger(__name__)


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
            "-t", "1",  # cpu_count
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
    with zipfile.ZipFile(os.path.join(settings.VERIFIER_STORAGE_PATH, file_path), 'r') as zf:
        infos = zf.infolist()
        for ix in range(0, min(UNPACK_CHUNK_SIZE, len(infos))):
            zf.extract(infos[ix], settings.VERIFIER_STORAGE_PATH)
        zf.close()


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
