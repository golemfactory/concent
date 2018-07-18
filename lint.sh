#!/bin/bash

printf "[FLAKE8: concent_api, signing_service]\n"
flake8                          \
    --exclude=local_settings.py \
    --jobs=4                    \
    --ignore=E124,E126,E128,E131,E156,E201,E221,E222,E225,E241,E251,E265,E271,E272,E501,E701,F405
printf "\n"

printf "[PYLINT: concent_api, signing_service]\n"
# Find all subdirectories of our python apps and use xargs to pass them as arguments to pylint

find concent_api/ -maxdepth 1 -mindepth 1 -type d \
    | xargs pylint --rcfile=pylintrc
printf "\n"

find signing_service/ -maxdepth 1 -mindepth 1 -type d \
    | xargs pylint --rcfile=pylintrc
printf "\n"
