#!/bin/bash -e

printf "=================== INSTALL CONCENT_API REQUIREMENTS ====================\n"
pip install -r concent_api/requirements.lock

printf "=================== INSTALL MIDDLEMAN_PROTOCOL REQUIREMENTS ====================\n"
cd middleman_protocol
python setup.py develop
cd ..

printf "=================== INSTALL SIGNING_SERVICE REQUIREMENTS ====================\n"
cd signing_service
python setup.py develop
cd ..

printf "=================== INSTALL REQUIREMENTS DEVELOPMENT ====================\n"
pip install -r requirements-development.lock
printf "\n"
