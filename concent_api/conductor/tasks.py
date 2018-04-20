from enum import Enum

from celery import shared_task


@shared_task
def blender_verification_request(
    subtask_id:             str,  # pylint: disable=unused-argument
    source_package_path:    str,  # pylint: disable=unused-argument
    result_package_path:    str,  # pylint: disable=unused-argument
    output_format:          Enum,  # pylint: disable=unused-argument
    scene_file:             str,  # pylint: disable=unused-argument
):
    pass
