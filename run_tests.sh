#!/bin/bash

CMD="coverage run --rcfile=../coverage-config --source='.' manage.py test --settings=concent_api.settings.testing"

display_usage(){
    printf "Usage:\n run_tests [-p || --pattern <tests pattern>] [-n || --multicore <number of cores to use>]\n"
}

for i in "$@"
do
    if [[ ( $i == "--help") ||  $i == "-h" ]]
        then
            display_usage
            exit 0
    fi
    case $i in
        -p=*|--pattern=*)
        PATTERN="${i#*=}"
        CMD+=" --pattern=\"$PATTERN\""
        ;;
        -n=*|--multicore=*)
        NUMBER_OF_CORES="${i#*=}"
        CMD+=" --parallel $NUMBER_OF_CORES"
        ;;
        *)
              # ignore unknown
        ;;
    esac
done
cd concent_api/                 || exit 1
printf "executing: $CMD\n\n"    || exit 1
eval "$CMD"                     || exit 1
coverage report --show-missing  || exit 1
cd ..
