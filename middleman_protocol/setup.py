#!/usr/bin/env python3
from os import path
from pathlib import Path
from setuptools import setup


def generate_version() -> str:
    here = path.abspath(path.dirname(__file__))
    version_file = Path(path.join(here, "RELEASE-VERSION"))
    if version_file.is_file():
        return open(version_file, "r").read()
    else:
        from version import get_version
        return get_version(prefix='v')


setup(
    name='Middleman-Protocol',
    version=generate_version(),
    url='https://github.com/golemfactory/concent',
    maintainer='Code Poets',
    maintainer_email='contact@codepoets.it',
    packages=[
        'middleman_protocol',
        'middleman_protocol.concent_golem_messages',
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
