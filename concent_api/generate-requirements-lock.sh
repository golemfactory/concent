#!/bin/bash -e

file_name="$1"


display_help() {
    echo "This script must be run within virtual environment"
    echo "Script accepts exactly one parameter (requirements file)"
    echo "Usage example: ./generate-requirements-lock.sh requirements.lock"
}


if [[ "$file_name" == "--help" || "$file_name" == "-h" || "$#" != 1 ]]
then
	display_help
	exit 0
fi

if [[ "$VIRTUAL_ENV" != "" ]]
then
    if [ -s "$file_name" ] && [[ "$file_name" == *.lock ]]
    then
        additional_lines=$(cat $file_name | grep "^--find-links")
        echo $additional_lines > $file_name
        pip freeze >> $file_name
        echo "Done"
    else
        echo "$file_name must be a python packages requirements .lock file"
        exit 1
    fi
else
    display_help
    exit 1
fi
