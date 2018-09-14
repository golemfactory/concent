#!/bin/bash -e
# Run this script only directly, without changing folders, because of relative paths
# ./install-development-requirements.sh - OK, ./concent/install-development-requirements.sh - incorrect

printf "=================== INSTALL CONCENT_API REQUIREMENTS ====================\n"
cd concent_api
pip install -r requirements.lock
cd ..

printf "=================== INSTALL MIDDLEMAN_PROTOCOL REQUIREMENTS ====================\n"
cd middleman_protocol
python setup.py develop
cd ..

printf "=================== INSTALL SIGNING_SERVICE REQUIREMENTS ====================\n"
cd signing_service
python setup.py develop
cd ..

printf "=================== INSTALL REQUIREMENTS DEVELOPMENT ====================\n"
pip install -r requirements-development.txt
printf "\n"
