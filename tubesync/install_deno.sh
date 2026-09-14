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

    [[ -n "${fn}" ]]

    # this should never do anything
    rm -v -f "./${fn}"*

    # fetch the much smaller manifest first
    download_gh_release "${owner}" "${repo}" "${fn}.sha256sum" 'latest'
    local latest_version="${resolved_version}"
    [[ -n "${latest_version}" ]]

    url="${releases_url}/download/${latest_version}/${fn}"

    download_gh_release "${owner}" "${repo}" "${fn%.zip}.sha256sum" "${latest_version}"
    mv -v -f "${fn%.zip}.sha256sum" 'deno.sha256sum'

    local latest_digest='' manifest_digest='' _attempt _tmpdir="$(realpath .)"
    for _attempt in {1..10}; do
        if [[ -z "${latest_digest}" ]]; then
            latest_digest="$(./asfald-latest --get-hash -- "${url}" || :)"
        fi
        if [[ -z "${manifest_digest}" ]]; then
            manifest_digest="$(./asfald-latest --get-hash -- "${url}.sha256sum" || :)"
        fi
        if ! TMPDIR="${_tmpdir}" ./asfald-latest --quiet --verbose -- "${url}"; then
            if ! TMPDIR="${_tmpdir}" ./asfald -q -w -o "${fn}" -p '${fullpath}.sha256sum' -- "${url}"; then
                download_gh_release "${owner}" "${repo}" "${fn}" "${latest_version}"
            fi
        fi
        if [[ -s "./${fn}" ]]; then break; else sleep "${_attempt}"; fi
    done

    [[ -z "${manifest_digest}" ]] || verify_digest "${manifest_digest}" "${fn}.sha256sum" || return 1
    [[ -z "${latest_digest}" ]] || verify_digest "${latest_digest}" "${fn}" || return 1
    "${HERE}/shasum.py" -a sha256 "./${fn}.sha256sum"
}

extract_deno() {
    local dest_dir
    dest_dir="${2:-.}"

    local fn
    fn="${1}"

    command -v unzip > /dev/null || install_unzip
    unzip -u -o -d "${dest_dir}" "${fn}" && chmod -c a+rx "${dest_dir}"/deno
    (cd "${dest_dir}" && "${HERE}/shasum.py" -a sha256 - || rm -v -rf "${dest_dir}"/deno) < './deno.sha256sum'
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
    for _attempt in {1..5}; do
        [[ -x ./asfald ]] || download_asfald
        download_asfald latest && break
        sleep "${_attempt}"
    done; unset -v _attempt ;

    download_deno "${deno_archive}"
    extract_deno "${deno_archive}" '/usr/local/bin'
    record_deno_version '/usr/local/bin/deno'
else
    record_deno_version "$(command -v deno)"
fi
