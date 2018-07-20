#!/bin/bash -e

TEST_RUNNER_EXTRA_ARGUMENTS=""

display_usage(){
    printf "Usage:\n"
    printf " run_tests [-p || --pattern =<tests pattern>] [-n || --multicore =<number of cores to use>]\n"
}

PATTERN=.
MODULE=.

for argument in "$@"
do
    if [[ ( $argument == "--help") ||  $argument == "-h" ]]; then
        display_usage
        exit 0
    fi
    case $argument in
        -p=*|--pattern=*)
            PATTERN="${argument#*=}"
            MODULE=${PATTERN%%::*}      # remove ::* (node specification)
            MODULE=${MODULE/\/tests/}   # substitute "/tests" with ""
            MODULE=${MODULE/test_/}     # substitute "test_" with ""
            MODULE=${MODULE/.py/}       # substitute ".py" with ""
            MODULE=${MODULE/\//.}       # substitute each  "/" with "."
        ;;
        -n=*|--multicore=*)
            NUMBER_OF_CORES="${argument#*=}"
            TEST_RUNNER_EXTRA_ARGUMENTS+=" -n $NUMBER_OF_CORES"
        ;;
        *)
            display_usage
            exit 1
        ;;
    esac
done

cd concent_api/
pytest                              \
    --cov-report term-missing       \
    --cov-config ../coverage-config \
    --cov=$MODULE $PATTERN          \
    ${TEST_RUNNER_EXTRA_ARGUMENTS}
rm .coverage
cd ..

cd middleman_protocol/
pytest -p no:django                 \
    --cov-report term-missing       \
    --cov-config ../coverage-config \
    --cov=$MODULE $PATTERN          \
    ${TEST_RUNNER_EXTRA_ARGUMENTS}
rm .coverage
cd ..

cd signing_service/
pytest -p no:django                 \
    --cov-report term-missing       \
    --cov-config ../coverage-config \
    --cov=$MODULE $PATTERN          \
    ${TEST_RUNNER_EXTRA_ARGUMENTS}
rm .coverage
cd ..
