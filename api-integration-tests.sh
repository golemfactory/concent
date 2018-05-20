#!/bin/bash

printf "=================== RUNNING API INTEGRATION TESTS ====================\n"
python3 concent_api/api-integration-force-accept-or-reject-results-test.py $1
python3 concent_api/api-integration-force-get-task-result-test.py $1
python3 concent_api/api-integration-force-payment.py $1
python3 concent_api/api-integration-force-report-computed-task-test.py $1
python3 concent_api/api-integration-additional-verification-test.py $1
