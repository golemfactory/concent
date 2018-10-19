#!/bin/bash

printf "=================== DJANGO CONFIGURATION CHECKS ====================\n"
python3 concent_api/manage.py check

if [ $? != 0 ]; then
    echo 'Exiting because of System Check error'
    exit 1
fi
printf "\n"
printf "=============================== LINT ===============================\n"
./lint.sh
printf "\n"

printf "========================= MYPY STATIC TYPE CHECKER =================\n"
mypy --config-file=mypy.ini concent_api/
mypy --config-file=mypy.ini middleman_protocol/
mypy --config-file=mypy.ini signing_service/
printf "\n"

printf "========================= UNIT TESTS WITH COVERAGE =================\n"
# NOTE: 'manage.py test' does not find all tests unless we run it from within the app directory.
./run_tests.sh "$@"
printf "\n"
