#!/usr/bin/env bash

playlist_id="${1}"
total_entries="${2}"

downloaded_entries="$( find / \
    -path '*/infojson/playlist/postprocessor_*_temp\.info\.json' \
    -name "postprocessor_[[]${playlist_id}[]]_*_${total_entries}_temp\.info\.json" \
    -exec basename '{}' ';' | \
    sed -e 's/^postprocessor_[[].*[]]_//;s/_temp.*\.json$//;' | \
    cut -d '_' -f 1 )"

find / \
    -path '*/infojson/playlist/postprocessor_*_temp\.info\.json' \
    -name "postprocessor_[[]${playlist_id}[]]_*_temp\.info\.json" \
    -type f -delete

if  [ 'NA' != "${downloaded_entries:=${3:-NA}}" ] &&
    [ 'NA' != "${total_entries:-NA}" ] &&
    [ "${downloaded_entries}" != "${total_entries}" ]
then
    exit 1
fi

exit 0
