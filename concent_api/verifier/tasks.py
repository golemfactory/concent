import logging
import os

from celery import shared_task
from golem_messages import message

from django.conf import settings

from conductor.models import BlenderSubtaskDefinition
from core.constants import VerificationResult
from core.tasks import verification_result
from core.transfer_operations import create_file_transfer_token_for_concent
from common.decorators import log_task_errors
from common.decorators import provides_concent_feature
from common.logging import log_string_message
from verifier.decorators import handle_verification_errors
from verifier.utils import compare_images
from verifier.utils import delete_source_files
from verifier.utils import download_archives_from_storage
from verifier.utils import load_images
from verifier.utils import render_image
from verifier.utils import try_to_upload_blender_output_file
from verifier.utils import unpack_archives
from verifier.utils import validate_downloaded_archives
from .utils import are_image_sizes_and_color_channels_equal
from .utils import generate_full_blender_output_file_name

logger = logging.getLogger(__name__)


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
    verification_deadline: int,
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
    assert isinstance(verification_deadline, int)

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
    render_image(frame_number, output_format, scene_file, subtask_id, verification_deadline)

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
