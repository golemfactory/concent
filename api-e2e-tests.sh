#!/bin/bash -e

if [ $# -gt 0 ]; then
    target=$1
else
    target="http://127.0.0.1:8000"
fi

printf "=================== RUNNING API INTEGRATION TESTS ====================\n"
python3 concent_api/api-e2e-force-accept-or-reject-results-test.py $target
python3 concent_api/api-e2e-force-get-task-result-test.py $target
python3 concent_api/api-e2e-force-payment.py $target
python3 concent_api/api-e2e-force-report-computed-task-test.py $target
python3 concent_api/api-e2e-additional-verification-test.py $target
