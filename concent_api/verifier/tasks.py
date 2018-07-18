import logging
import os
from typing import List

from celery import shared_task
from golem_messages import message
from mypy.types import Optional

from django.conf import settings

from conductor.models import BlenderSubtaskDefinition
from core.constants import VerificationResult
from core.tasks import verification_result
from core.transfer_operations import create_file_transfer_token_for_concent
from common.decorators import log_task_errors
from common.decorators import provides_concent_feature
from common.logging import log_string_message
from verifier.decorators import handle_verification_results
from verifier.utils import delete_source_files
from verifier.utils import download_archives_from_storage
from verifier.utils import unpack_archives
from verifier.utils import validate_downloaded_archives
from .utils import compare_all_rendered_images_with_user_results_files
from .utils import compare_minimum_ssim_with_results
from .utils import ensure_enough_result_files_provided
from .utils import ensure_frames_have_related_files_to_compare
from .utils import get_files_list_from_archive
from .utils import generate_verifier_storage_file_path
from .utils import parse_result_files_with_frames
from .utils import render_images_by_frames
from .utils import upload_blender_output_file


logger = logging.getLogger(__name__)


@shared_task
@provides_concent_feature('verifier')
@log_task_errors
@handle_verification_results
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
    frames: List[int],
    blender_crop_script: Optional[str],
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
        f'Scene_file: {scene_file}.',
        f'Frames: {frames}.'
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

    validate_downloaded_archives(subtask_id, package_paths_to_downloaded_archive_names.values(), scene_file)

    unpack_archives(package_paths_to_downloaded_archive_names.values(), subtask_id)

    result_files_list = get_files_list_from_archive(
        generate_verifier_storage_file_path(package_paths_to_downloaded_archive_names[result_package_path])
    )

    ensure_enough_result_files_provided(
        frames=frames,
        result_files_list=result_files_list,
        subtask_id=subtask_id,
    )

    parsed_files_to_compare = parse_result_files_with_frames(
        frames=frames,
        result_files_list=result_files_list,
        output_format=output_format,
    )

    ensure_frames_have_related_files_to_compare(
        frames=frames,
        parsed_files_to_compare=parsed_files_to_compare,
        subtask_id=subtask_id,
    )

    (blender_output_file_name_list, parsed_files_to_compare) = render_images_by_frames(
        parsed_files_to_compare=parsed_files_to_compare,
        frames=frames,
        output_format=output_format,
        scene_file=scene_file,
        subtask_id=subtask_id,
        verification_deadline=verification_deadline,
        blender_crop_script=blender_crop_script,
    )

    delete_source_files(package_paths_to_downloaded_archive_names[source_package_path])

    upload_blender_output_file(
        frames=frames,
        blender_output_file_name_list=blender_output_file_name_list,
        output_format=output_format,
        subtask_id=subtask_id,
    )

    ssim_list = compare_all_rendered_images_with_user_results_files(
        parsed_files_to_compare=parsed_files_to_compare,
        subtask_id=subtask_id,
    )

    compare_minimum_ssim_with_results(ssim_list, subtask_id)
