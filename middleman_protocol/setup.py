#!/usr/bin/env python3

import os
from setuptools import setup


def get_version():
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'RELEASE-VERSION',
    )
    with open(path, 'r') as version_file:
        return version_file.read()


setup(
    name='Middleman-Protocol',
    version=get_version(),
    url='https://github.com/golemfactory/concent',
    maintainer='Code Poets',
    maintainer_email='contact@codepoets.it',
    packages=[
        'middleman_protocol',
    ],
    package_data={},
    python_requires='>=3.6',
    install_requires=[
        'construct',
        'golem_messages',
        'mypy',
    ],
    tests_require=[
        'mock',
        'pytest',
        'pytest-xdist',
    ],
)
