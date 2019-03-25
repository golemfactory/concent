from typing import Dict
from typing import List
from typing import Union

from conductor.models import BlenderCropScriptParameters


def parse_blender_crop_script_parameters_to_dict_from_query(
        blender_crop_script_parameters: BlenderCropScriptParameters
) -> Dict[str, Union[int, List[str], bool]]:
    return dict(
        resolution=[
            blender_crop_script_parameters.resolution_x,
            blender_crop_script_parameters.resolution_y
        ],
        borders_x=[
            str(blender_crop_script_parameters.borders_x_min),
            str(blender_crop_script_parameters.borders_x_max),
        ],
        borders_y=[
            str(blender_crop_script_parameters.borders_y_min),
            str(blender_crop_script_parameters.borders_y_max),
        ],
        use_compositing=blender_crop_script_parameters.use_compositing,
        samples=blender_crop_script_parameters.samples,
    )
