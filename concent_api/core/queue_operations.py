from conductor.tasks import blender_verification_request
from utils.helpers import get_storage_result_file_path
from utils.helpers import get_storage_source_file_path


def send_blender_verification_request(compute_task_def):
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
    output_format = compute_task_def['extra_data']['output_format']
    scene_file = compute_task_def['extra_data']['scene_file']
    blender_verification_request.delay(
        subtask_id=subtask_id,
        source_package_path=source_package_path,
        result_package_path=result_package_path,
        output_format=output_format,
        scene_file=scene_file,
    )
