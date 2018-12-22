from golem_messages.message.tasks import ComputeTaskDef

from conductor.tasks import blender_verification_request
from common.helpers import get_storage_result_file_path
from common.helpers import get_storage_source_file_path
from core.utils import adjust_format_name
from core.utils import extract_name_from_scene_file_path
from core.validation import validate_frames


def send_blender_verification_request(compute_task_def: ComputeTaskDef, verification_deadline: int) -> None:
    task_id = compute_task_def['task_id']
    subtask_id = compute_task_def['subtask_id']
    source_package_path = get_storage_source_file_path(
        subtask_id=subtask_id,
        task_id=task_id,
    )
    result_package_path = get_storage_result_file_path(
        subtask_id=subtask_id,
        task_id=task_id,
    )
    output_format = adjust_format_name(compute_task_def['extra_data']['output_format'])
    scene_file_path = compute_task_def['extra_data']['scene_file']
    frames = compute_task_def['extra_data']['frames']
    blender_crop_script = compute_task_def['extra_data'].get('script_src')

    # Verifier needs to get scene_file path without golem's resource directory prefix
    # Function below cuts off beginning prefix and pass to `blender_verification_request` scene_file without it.
    scene_file = extract_name_from_scene_file_path(scene_file_path)

    validate_frames(frames)
    assert scene_file is not None
    blender_verification_request.delay(
        subtask_id=subtask_id,
        source_package_path=source_package_path,
        result_package_path=result_package_path,
        output_format=output_format,
        scene_file=scene_file,
        verification_deadline=verification_deadline,
        frames=frames,
        blender_crop_script=blender_crop_script,
    )
