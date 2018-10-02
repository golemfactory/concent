#!/bin/bash

printf "=================== RUNNING API INTEGRATION TESTS ====================\n"
python3 concent_api/api-e2e-force-accept-or-reject-results-test.py $1
python3 concent_api/api-e2e-force-get-task-result-test.py $1
python3 concent_api/api-e2e-force-payment.py $1
python3 concent_api/api-e2e-force-report-computed-task-test.py $1
python3 concent_api/api-e2e-additional-verification-test.py $1
