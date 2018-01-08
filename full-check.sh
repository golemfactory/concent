#!/bin/bash

printf "=================== DJANGO CONFIGURATION CHECKS ====================\n"
python3 concent_api/manage.py check
printf "\n"

printf "=============================== LINT ===============================\n"
./lint.sh
printf "\n"

printf "========================= MYPY STATIC TYPE CHECKER =================\n"
mypy --config-file=mypy.ini concent_api/
printf "\n"

printf "========================= UNIT TESTS WITH COVERAGE =================\n"
# NOTE: 'manage.py test' does not find all tests unless we run it from within the app directory.
rm -rf contrib/coverage/coverage_html
cd concent_api/
coverage run --rcfile=../coverage-config --source='.' manage.py test
coverage html --rcfile=../coverage-config
coverage report -m
cd ..
