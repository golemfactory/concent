from base64 import b64encode
import logging
import os
import subprocess
import zipfile

from django.conf                import settings

from celery import shared_task
from golem_messages             import message
from golem_messages.shortcuts   import dump

from core.transfer_operations   import send_request_to_cluster_storage
from gatekeeper.constants       import CLUSTER_DOWNLOAD_PATH
from utils.helpers              import get_current_utc_timestamp
from .constants                 import VerificationResult


logger = logging.getLogger(__name__)


@shared_task
def verification_order_task(
    subtask_id:             str,
    src_code:               str,
    extra_data:             str,
    short_description:      str,
    working_directory:      str,
    performance:            str,
    docker_images:          str,
    source_file:            str,
    result_file:            str,
):
    # Generate a FileTransferToken valid for a download of any file listed in the order.
    file_transfer_tokens = {}
    for file_name in (source_file, result_file):
        file_transfer_token = message.concents.FileTransferToken(
            token_expiration_deadline       = get_current_utc_timestamp() + settings.TOKEN_EXPIRATION_TIME,
            storage_cluster_address         = settings.STORAGE_CLUSTER_ADDRESS,
            authorized_client_public_key    = b64encode(settings.CONCENT_PUBLIC_KEY),
            operation                       = 'download',
        )

        file_transfer_token.files = [message.concents.FileTransferToken.FileInfo()]
        file_transfer_token.files[0]['path']      = settings.STORAGE_CLUSTER_ADDRESS + file_name
        file_transfer_token.files[0]['checksum']  = ''  # TODO: How to set this ?
        file_transfer_token.files[0]['size']      = ''  # TODO: How to set this ?

        file_transfer_tokens[file_name] = file_transfer_token

    # Remove any files from VERIFIER_STORAGE_PATH.
    for file in os.listdir(settings.VERIFIER_STORAGE_PATH):
        file_path = os.path.join(settings.VERIFIER_STORAGE_PATH, file)
        try:
            if os.path.isfile(file_path):
                os.unlink(file_path)
        except OSError:
            pass

    # Download all the files listed in the message from the storage server to local storage.
    for file_name, file_transfer_token in file_transfer_tokens.items():
        dumped_file_transfer_token = dump(
            file_transfer_token,
            settings.CONCENT_PRIVATE_KEY,
            settings.CONCENT_PUBLIC_KEY,
        )
        headers = {
            'Authorization':                'Golem ' + b64encode(dumped_file_transfer_token).decode(),
            'Concent-Client-Public-Key':    b64encode(settings.CONCENT_PUBLIC_KEY).decode(),
        }
        request_http_address = settings.STORAGE_CLUSTER_ADDRESS + CLUSTER_DOWNLOAD_PATH + file_transfer_token.files[0]['path']

        try:
            cluster_response = send_request_to_cluster_storage(
                headers,
                request_http_address,
                method = 'get',
            )

            with open(os.path.join(settings.VERIFIER_STORAGE_PATH, file_name), 'wb') as f:
                for chunk in cluster_response.iter_content():
                    f.write(chunk)

        except Exception as e:  # TODO: What exceptions can happen here ?
            verification_result_task.delay(
                subtask_id,
                VerificationResult.ERROR,
                str(e),
                # TODO: How to determine error_code ?
            )
            return

    # Verifier unpacks the archive with project source.
    unpacked_source_files = zipfile.ZipFile.namelist(os.path.join(settings.VERIFIER_STORAGE_PATH, file_name))
    for file_name in (source_file, result_file):
        try:
            with zipfile.ZipFile(
                os.path.join(settings.VERIFIER_STORAGE_PATH, file_name),
                'r'
            ) as zf:
                infos = zf.infolist()
                for ix in range(max(0, 0), min(50, len(infos))):
                    zf.extract(infos[ix], settings.VERIFIER_STORAGE_PATH)
                zf.close()
        except OSError as e:  # TODO: What other exceptions can happen here ?
            verification_result_task.delay(
                subtask_id,
                VerificationResult.ERROR,
                str(e),
                # TODO: How to determine error_code ?
            )
            return

    # Verifier starts blender process.
    try:
        completed_process = subprocess.run(
            ["ls", "-l", "/dev/null"],
            timeout = settings.BLENDER_MAX_RENDERING_TIME,
            stdout  = subprocess.PIPE,
            stderr  = subprocess.PIPE,
        )
        logger.info('Blender proces std_out: {}'.format(completed_process.stdout))
        logger.info('Blender proces std_err: {}'.format(completed_process.stderr))
        if completed_process.returncode != 0:
            verification_result_task.delay(
                subtask_id,
                VerificationResult.ERROR,
                str(completed_process.stder),
                # TODO: How to determine error_code ?
            )
    except subprocess.SubprocessError as e:
        verification_result_task.delay(
            subtask_id,
            VerificationResult.ERROR,
            str(e),
            # TODO: How to determine error_code ?
        )

    # Verifier deletes source files of the Blender project from its storage.
    # At this point there must be source files in VERIFIER_STORAGE_PATH otherwise verification should fail before.
    for file in unpacked_source_files + [source_file]:
        file_path = os.path.join(settings.VERIFIER_STORAGE_PATH, file)
        try:
            if os.path.isfile(file_path):
                os.unlink(file_path)
        except OSError:
            pass

    verification_result_task.delay(

    )


@shared_task
def verification_result_task(
    subtask_id:         str,
    result:             VerificationResult,
    error_message:      str,
    error_code:         str,
):
    logger.info('verification_result_task starts with: SUBTASK_ID {} -- RESULT {}'.format(
        subtask_id,
        result,
    ))

    assert isinstance(subtask_id,       str)
    assert isinstance(error_message,    str)
    assert isinstance(error_code,       str)
    assert result in VerificationResult
    assert all([error_message, error_code]) if result == VerificationResult.ERROR else True

    logger.info('verification_result_task ends with: SUBTASK_ID {} -- RESULT {}'.format(
        subtask_id,
        result,
    ))
