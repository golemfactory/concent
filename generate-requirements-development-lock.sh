#!/bin/bash -e

virtualenv /tmp/generate-requirements-development-lock
source /tmp/generate-requirements-development-lock/bin/activate
pip install -r ${BASH_SOURCE%/*}/concent_api/requirements.lock
pip install -r ${BASH_SOURCE%/*}/requirements-development.txt
echo "--find-links https://builds.golem.network/simple/pyelliptic" > ${BASH_SOURCE%/*}/requirements-development.lock
pip freeze >> ${BASH_SOURCE%/*}/requirements-development.lock
deactivate
rm -rf /tmp/generate-requirements-development-lock
