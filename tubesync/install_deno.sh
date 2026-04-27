#!/usr/bin/env bash

# requires:
# - curl
# - python3
# - unzip

HERE="$(dirname "$(realpath "$0")")"
source "${HERE}/download_gh_release.func.inc.sh"
source "${HERE}/download_asfald.func.inc.sh"

download_deno() {
    local owner='denoland' repo='deno'
    local fn
    fn="${1}"

    local releases_url="https://github.com/${owner}/${repo}/releases"
    local url="${releases_url}/latest/download/${fn}"

    test -n "${fn}"
    rm -v -f "./${fn}"* # this should never do anything

    download_gh_release "${owner}" "${repo}" "${fn}" 'latest'
    local latest_version="${resolved_version}"
    test -n "${latest_version}"

    url="${releases_url}/download/${latest_version}/${fn}"
    local latest_digest="$(./asfald-latest --get-hash "${url}")"
    verify_digest "${latest_digest}" "${fn}" || return 1

    download_gh_release "${owner}" "${repo}" "${fn}.sha256sum" "${latest_version}"
    "${HERE}/shasum.py" -a sha256 "./${fn}.sha256sum"
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
_cleanup() {
    rm -v -rf -- "${work_dir}"
}
trap '_cleanup' EXIT
cd "${work_dir}"

if [ '--only-record-version' != "${1-unset}" ]; then
    download_asfald
    download_asfald latest

    download_deno "${deno_archive}"
    extract_deno "${deno_archive}" '/usr/local/bin'
    record_deno_version '/usr/local/bin/deno'
else
    record_deno_version "$(command -v deno)"
fi
