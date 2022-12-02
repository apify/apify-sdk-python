#!/usr/bin/env bash

cd "$( dirname "${BASH_SOURCE[0]}" )"


mv ../docs.md ../old_docs.md
OLD_MD5=$(md5sum ../old_docs.md | cut -f 1 -d " ")

./build.sh
BUILD_STATUS=$?

NEW_MD5=$(md5sum ../docs.md | cut -f 1 -d " ")
mv ../old_docs.md ../docs.md


if [[ ${BUILD_STATUS} -ne 0 ]]; then
    echo "Building docs failed!" >&2
    exit 1
fi

if [[ "${OLD_MD5}" != "${NEW_MD5}" ]]; then
    echo "The docs.md file is not up to date!" >&2
    exit 1
fi
