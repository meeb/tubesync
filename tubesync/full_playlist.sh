#!/usr/bin/env bash

playlist_id="${1}"
total_entries="${2}"

if [[ "${playlist_id}" == UUSH* ]]; then
    exit 0
fi

# select YOUTUBE_*DIR settings
# convert None to ''
# convert PosixPath('VALUE') to 'VALUE'
# assign a shell variable with the setting name and value
_awk_prog='$2 == "=" && $1 ~ /^YOUTUBE_/ && $1 ~ /DIR$/ {
    sub(/^None$/, "'\'\''", $3);
    r = sub(/^PosixPath[(]/, "", $3);
    NF--;
    if(r) {sub(/[)]$/, "", $NF);};
    $3=$1 $2 $3; $1=$2=""; sub("^" OFS "+", "");
    print;
    }'
. <(python3 /app/manage.py diffsettings --output hash | awk "${_awk_prog}")
WHERE="${YOUTUBE_DL_CACHEDIR:-/dev/shm}"

downloaded_entries="$( find /dev/shm "${WHERE}" \
    -path '*/infojson/playlist/postprocessor_*_temp\.info\.json' \
    -name "postprocessor_[[]${playlist_id}[]]_*_${total_entries}_temp\.info\.json" \
    -exec basename '{}' ';' | \
    sed -e 's/^postprocessor_[[].*[]]_//;s/_temp.*\.json$//;' | \
    cut -d '_' -f 1 )"

if ! [[ "${total_entries}" =~ ^[0-9]+$ ]] || [ "${total_entries}" -le 0 ]; then
    exit 0
fi

if [ -z "${downloaded_entries}" ]; then
    exit 0
fi

find /dev/shm "${WHERE}" \
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
