#!/bin/bash -e

if [[ "$VIRTUAL_ENV" != "" ]]
then
    echo "--find-links https://builds.golem.network/simple/pyelliptic" > ${BASH_SOURCE%/*}/requirements.lock
    pip freeze >> ${BASH_SOURCE%/*}/requirements.lock
    echo "Done"
else
    echo "Script should be run within virtual environment"
    exit 1
fi
