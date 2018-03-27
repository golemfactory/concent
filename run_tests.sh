#!/bin/bash -e

COVERAGE_COMMAND="coverage run --rcfile=../coverage-config --source='.' manage.py test --settings=concent_api.settings.testing"
TEST_RUNNER_EXTRA_ARGUMENTS=""

display_usage(){
    printf "Usage:\n"
    printf " run_tests [-p || --pattern =<tests pattern>] [-n || --multicore =<number of cores to use>]\n"
}

for argument in "$@"
do
    if [[ ( $argument == "--help") ||  $argument == "-h" ]]; then
        display_usage
        exit 0
    fi
    case $argument in
        -p=*|--pattern=*)
            PATTERN="${argument#*=}"
            COVERAGE_COMMAND+=" --pattern=\"$PATTERN\""
            TEST_RUNNER_EXTRA_ARGUMENTS+=" --pattern=\"$PATTERN\""
        ;;
        -n=*|--multicore=*)
            NUMBER_OF_CORES="${argument#*=}"
            COVERAGE_COMMAND+=" --parallel=$NUMBER_OF_CORES"
            TEST_RUNNER_EXTRA_ARGUMENTS+=" --parallel=$NUMBER_OF_CORES"
        ;;
        *)
            display_usage
            exit 1
        ;;
    esac
done
cd concent_api/
printf "executing: $COVERAGE_COMMAND\n\n"
coverage run                                    \
    --rcfile ../coverage-config                 \
    --source '.'                                \
    manage.py test                              \
        --settings concent_api.settings.testing \
        ${TEST_RUNNER_EXTRA_ARGUMENTS}
coverage report --show-missing
cd ..
