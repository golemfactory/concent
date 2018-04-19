from base64 import b64encode
import logging
import os
import requests

from django.conf import settings

from golem_messages import message
from golem_messages.shortcuts import dump


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
    with open(file_path, 'wb') as f:
        for chunk in response.iter_content():
            f.write(chunk)
