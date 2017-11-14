#!/bin/bash

printf "=================== DJANGO CONFIGURATION CHECKS ====================\n"
python3 concent_api/manage.py check
printf "\n"

printf "=============================== LINT ===============================\n"
./lint.sh
printf "\n"

printf "============================ UNIT TESTS ============================\n"
# NOTE: 'manage.py test' does not find all tests unless we run it from within the app directory.
cd concent_api/
python3 manage.py test
cd ..
