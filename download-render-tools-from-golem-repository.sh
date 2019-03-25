#!/bin/bash -e

default_download_path="concent_api/verifier/golem_render_tools"
default_version="develop"


function display_usage() {
    printf "Usage:\n"
    printf " download_render_tools_from_golem_repository
           [-r || --repository-tag=<name of tag or branch from where files should be downloaded (default: ${default_version})>]
           [-p || --full-path-to-store-files=<full path where downloaded files should be stored (default: ${default_download_path}>])\n"
}


organization_name="golemfactory"
repository_name="golem"
version=${default_version}
path_to_store_files=${default_download_path}
files_to_download=(
    "scenefileeditor.py"
    "templates/blendercrop.py.template"
)

download_url="https://raw.githubusercontent.com/${organization_name}/${repository_name}/${version}/apps/blender/resources/images/entrypoints/scripts/render_tools"


for argument in "$@"
do
    if [[ $argument == "--help" ||  $argument == "-h" ]]; then
        display_usage
        exit 0
    fi
    case $argument in
        -p=*|--full-path-to-store-files=*)
        path_to_store_files="${argument#*=}"
        ;;
        -r=*|--repository-tag=*)
        version="${argument#*=}"
    esac
done


if [ ! -d "${path_to_store_files}" ]
then
    mkdir -p "${path_to_store_files}/templates"
    echo "Created new directory in ${path_to_store_files}"
fi

for file in ${files_to_download[*]}
do
    curl "${download_url}/${file}" --output "${path_to_store_files}/${file}"
    echo "Downloaded ${file} and stored in ${path_to_store_files}/${file}"
done
