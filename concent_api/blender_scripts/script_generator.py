import os
from typing import Any
from typing import Dict
from common.constants import BLENDER_CROP_TEMPLATE_DIR
from common.constants import BLENDER_CROP_TEMPLATE_NAME
from common.helpers import get_concent_path


def generate_blender_script_src(
    meta_parameters: Dict[str, Any]
) -> str:
    with open(
        os.path.join(
            get_concent_path(),
            BLENDER_CROP_TEMPLATE_DIR,
            BLENDER_CROP_TEMPLATE_NAME,
        )
    ) as file:
        contents = file.read()

    contents %= {
        'resolution_x': meta_parameters['resolution'][0],
        'resolution_y': meta_parameters['resolution'][1],
        'border_min_x': meta_parameters['borders_x'][0],
        'border_max_x': meta_parameters['borders_x'][1],
        'border_min_y': meta_parameters['borders_y'][0],
        'border_max_y': meta_parameters['borders_y'][1],
        'use_compositing': meta_parameters['use_compositing'],
        'samples': meta_parameters['samples'],
    }

    return contents
