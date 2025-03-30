#!/usr/bin/env sh

echo "$1"
echo "$2"
playlist_id="${1}"
total_entries="${2}"
set -x

time find / -path '*/infojson/playlist/*' \
    -name "postprocessor_[${playlist_id}]_*_${total_entries}_temp.info.json"

exit 0
downloaded_entries=0

if [ 'NA' != "${total_entries}" ] && [ "${downloaded_entries}" != "${total_entries}" ]
then
    exit 1
fi

exit 0
