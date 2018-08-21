#!/usr/bin/env python3

import os
from setuptools import setup

from version import get_version


setup(
    name='Signing-Service',
    version=get_version(prefix='v'),
    url='https://github.com/golemfactory/concent',
    maintainer='Code Poets',
    maintainer_email='contact@codepoets.it',
    packages=[
        'signing_service',
    ],
    package_data={},
    python_requires='>=3.6',
)
