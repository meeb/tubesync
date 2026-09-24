#!/usr/bin/env bash

# requires:
# - curl
# - gpg
# - python3
# - unzip

HERE="$(dirname "$(realpath "$0")")"
source "${HERE}/download_gh_release.func.inc.sh"
source "${HERE}/download_asfald.func.inc.sh"

download_bun() {
    local owner='oven-sh' repo='bun'
    local fn
    fn="${1}"

    local releases_url="https://github.com/${owner}/${repo}/releases"
    local url="${releases_url}/latest/download/${fn}"

    [[ -n "${fn}" ]]

    # this should never do anything
    rm -v -f "./${fn}"*

    # fetch the much smaller manifest first
    download_gh_release "${owner}" "${repo}" 'SHASUMS256.txt.asc' 'bun-v1.3.14'
    local latest_version="${resolved_version}"
    [[ -n "${latest_version}" ]]

    local uname_m="$(uname -m)"
    case "${uname_m}" in
        (x86_64) fn='bun-linux-x64-baseline.zip' ;;
        (*) fn="bun-linux-${uname_m}.zip" ;;
    esac
    bun_archive="${fn:-"${bun_archive}"}"

    url="${releases_url}/download/${latest_version}/${fn}"

    local latest_digest='' manifest_digest='' _attempt _tmpdir="$(realpath .)"
    manifest_digest='sha256:f7dae34eb12b0752232f284a517457d9e7de44db90c8b8cfd6a494fcee410c9e'
    for _attempt in {1..10}; do
        if [[ -z "${latest_digest}" ]]; then
            latest_digest="$(./asfald-latest --get-hash -- "${url}" || :)"
        fi
        if [[ -z "${manifest_digest}" ]]; then
            manifest_digest="$(./asfald-latest --get-hash -- "${url%/*}/SHASUMS256.txt.asc" || :)"
        fi
        if ! TMPDIR="${_tmpdir}" ./asfald-latest --quiet --verbose -- "${url}"; then
            if ! TMPDIR="${_tmpdir}" ./asfald -q -w -o "${fn}" -p '${fullpath}.sha256sum' -- "${url}"; then
                download_gh_release "${owner}" "${repo}" "${fn}" "${latest_version}"
            fi
        fi
        if [[ -s "./${fn}" ]]; then break; else sleep "${_attempt}"; fi
    done

    [[ -z "${manifest_digest}" ]] || verify_digest "${manifest_digest}" 'SHASUMS256.txt.asc' || return 1
    [[ -z "${latest_digest}" ]] || verify_digest "${latest_digest}" "${fn}" || return 1
    grep -e '\.zip$' 'SHASUMS256.txt.asc' | "${HERE}/shasum.py" -a sha256 -
}

extract_bun() {
    local dest_dir
    dest_dir="${2:-.}"

    local fn
    fn="${1}"

    command -v unzip > /dev/null || install_unzip
    local _staged="$(mktemp -u "${dest_dir}"/.bun.XXXXXXXX)"
    _cleanup_list+=("${_staged}")
    unzip -u -o -d './.bun' "${fn}" &&
        install -v -T ./.bun/bun-linux-*/bun "${_staged}" &&
        { # bun spawning unzip hangs for an unknown reason fairly often
            local _force=1 ; 
            local _attempt ; for _attempt in {1..5} ; do
                if [[ 1 < "${_attempt}" ]]; then
                    _force=0
                fi
                INSTALL_BUN_FORCE_ERROR="${_force}" \
                INSTALL_BUN_ATTEMPT="${_attempt}" \
                "${_staged}" run "${HERE}/verify_bun.ts" --release 'bun-v1.3.14' --asset "${fn}" --install-dir "${dest_dir}" &&
                    break || sleep "${_attempt}"
            done ;
            [[ -x "${dest_dir}/bun" ]]
        }
}

install_unzip() {
    apt-get update && apt-get install -y unzip
}

record_bun_version() {
    local bun_bin
    bun_bin="${1:-./bun}"

    # --revision has the version with `+` and some extra tacked onto the end
    # --version has the clean number
    bun_version="$("${bun_bin}" --version | awk -v 'ev=31' '1 == NR { print $0; ev=0; } END { exit ev; }')"
    test -n "${bun_version}"
    printf -- "bun_version = '%s'\n" "${bun_version}" >> /app/common/third_party_versions.py
}

set -euo pipefail

declare -a _cleanup_list
work_dir="$(mktemp -d)"
_cleanup_list+=("${work_dir}")
_cleanup() {
    rm -v -rf -- "${_cleanup_list[@]}"
}
trap '_cleanup' EXIT
cd "${work_dir}"

if [ '--only-record-version' != "${1-unset}" ]; then
    for _attempt in {1..5}; do
        [[ -x ./asfald ]] || download_asfald
        download_asfald latest && break
        sleep "${_attempt}"
    done; unset -v _attempt ;

    bun_archive='bun-linux-'
    download_bun "${bun_archive}"
    extract_bun "${bun_archive}" '/usr/local/bin'
    record_bun_version '/usr/local/bin/bun'
else
    record_deno_version "$(command -v bun)"
fi
