"""
This script uses golem_messages version generator to generate Concent version.
It has to be run on environment with golem_messages installed.
"""


import os

import golem_messages


def generate_version():
    golem_messages_directory = os.path.dirname(golem_messages.__file__)
    version_script_path      = os.path.join(
        golem_messages_directory,
        '..',
        'version.py',
    )

    if not os.path.exists(version_script_path):
        exit('Script for generating version not found, used path: {}.'.format(
            version_script_path
        ))

    os.system('python {}'.format(
        version_script_path
    ))


if __name__ == "__main__":
    generate_version()
