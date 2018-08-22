#!/usr/bin/env python3

from setuptools import setup

from version import get_version


setup(
    name='Middleman-Protocol',
    version=get_version(prefix='v'),
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
