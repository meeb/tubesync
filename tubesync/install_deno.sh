#!/usr/bin/env bash

# requires:
# - curl
# - sha256sum
# - unzip

download_deno() {
    local url
    url='https://github.com/denoland/deno/releases/latest/download'
    curl -sSLRJO "${url}/deno-$(uname -m)-unknown-linux-gnu.zip"{,.sha256sum} | sha256sum -wc
}

extract_deno() {
    command -v unzip > /dev/null || {
        apt-get update && apt-get install -y unzip ;
    }
    unzip -u -o -d /usr/local/bin "deno-$(uname -m)-unknown-linux-gnu.zip"
    chmod -c a+rx /usr/local/bin/deno
}

record_deno_version() {
    deno_version="$(/usr/local/bin/deno -V | awk -v 'ev=31' '1 == NR && "deno" == $1 { print $2; ev=0; } END { exit ev; }')"
    printf -- "deno_version = '%s'\n" "${deno_version}" >> /app/common/third_party_versions.py
}

set -eu
work_dir="$(mktemp -d)"
trap "rm -rf -- '${work_dir}'" EXIT
cd "${work_dir}"

download_deno
extract_deno
record_deno_version
