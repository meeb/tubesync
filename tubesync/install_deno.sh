#!/usr/bin/env bash

# requires:
# - curl
# - sha256sum
# - unzip

download_deno() {
    local fn
    fn="${1}"

    local url
    url='https://github.com/denoland/deno/releases/latest/download'

    test -n "${fn}"
    rm -v -f "./${fn}"* # this should never do anything
    curl -sSJLR --remote-name-all "${url}/${fn}{,.sha256sum}"
    sha256sum -wc "./${fn}.sha256sum"
}

extract_deno() {
    local dest_dir
    dest_dir="${2:-.}"

    local fn
    fn="${1}"

    command -v unzip > /dev/null || install_unzip
    unzip -u -o -d "${dest_dir}" "${fn}" && chmod -c a+rx "${dest_dir}"/deno
}

install_unzip() {
    apt-get update && apt-get install -y unzip
}

record_deno_version() {
    local deno_bin
    deno_bin="${1:-./deno}"

    deno_version="$("${deno_bin}" -V | awk -v 'ev=31' '1 == NR && "deno" == $1 { print $2; ev=0; } END { exit ev; }')"
    test -n "${deno_version}"
    printf -- "deno_version = '%s'\n" "${deno_version}" >> /app/common/third_party_versions.py
}

set -eu
deno_archive="deno-$(uname -m)-unknown-linux-gnu.zip"
work_dir="$(mktemp -d)"
trap "rm -rf -- '${work_dir}'" EXIT
cd "${work_dir}"

if [ '--only-record-version' != "${1-unset}" ]; then
    download_deno "${deno_archive}"
    extract_deno "${deno_archive}" '/usr/local/bin'
fi
record_deno_version '/usr/local/bin/deno'
