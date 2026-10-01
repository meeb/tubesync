#!/usr/bin/env bash

# requires:
# - curl
# - python3

set -eu
HERE="$(dirname "$(realpath "$0")")"
source "${HERE}/download_gh_release.func.inc.sh"
source "${HERE}/download_asfald.func.inc.sh"

bin_directory() {
    local dir="${1:-/usr/local/bin}"

    if [ -d "${dir}" ]
    then
        printf -- '%s\n' "${dir}"
    else
        printf -- '%s\n' "$(dirname "${dir}")"
    fi
}

download_tailwindcss() {
    local owner='tailwindlabs' repo='tailwindcss'

    local ARCH="$(uname -m)"
    case "${ARCH}" in
        (aarch64|arm64) ARCH='arm64' ;;
        (x86_64) ARCH='x64' ;;
    esac

    local OS="$(uname -s)"
    case "${OS}" in
        (Darwin) OS='macos' ;;
        (Linux) OS='linux' ;;
    esac

    local TW_BIN=''
    case "${OS}-${ARCH}" in
        (linux-arm64|linux-x64|macos-arm64|macos-x64)
            TW_BIN="tailwindcss-${OS}-${ARCH}"
            ;;
        (*)
            stderr "The tailwindcss CLI binary is unavailable for: ${OS}-${ARCH}"
            return 1
            ;;
    esac

    local fn="${TW_BIN}"
    local releases_url="https://github.com/${owner}/${repo}/releases"
    local url="${releases_url}/latest/download/${fn}"

    [[ -n "${fn}" ]]

    # this should never do anything
    rm -v -f './sha256sums.txt' "./${fn}"*

    # fetch the much smaller manifest first
    download_gh_release "${owner}" "${repo}" 'sha256sums.txt' 'latest'
    local latest_version="${resolved_version}"
    [[ -n "${latest_version}" ]]

    url="${releases_url}/download/${latest_version}/${fn}"

    local latest_digest='' manifest_digest='' _attempt _tmpdir="$(realpath .)"
    for _attempt in {1..10}; do
        if [[ -z "${latest_digest}" ]]; then
            latest_digest="$(./asfald-latest --get-hash -- "${url}" || :)"
        fi
        if [[ -z "${manifest_digest}" ]]; then
            manifest_digest="$(./asfald-latest --get-hash -- "${releases_url}/download/${latest_version}/sha256sums.txt" || :)"
        fi
        if ! TMPDIR="${_tmpdir}" ./asfald-latest --quiet --verbose -- "${url}"; then
            if ! TMPDIR="${_tmpdir}" ./asfald -q -w -o "${fn}" -p '${path}/sha256sums.txt' -- "${url}"; then
                download_gh_release "${owner}" "${repo}" "${fn}" "${latest_version}"
            fi
        fi
        if [[ -s "./${fn}" ]]; then break; else sleep "${_attempt}"; fi
    done

    [[ -z "${manifest_digest}" ]] || verify_digest "${manifest_digest}" 'sha256sums.txt' || return 1
    [[ -z "${latest_digest}" ]] || verify_digest "${latest_digest}" "${fn}" || return 1
    "${HERE}/shasum.py" -a sha256 './sha256sums.txt' && \
        chmod 'a+rx' "${fn}" && \
        mv -v "${fn}" 'tailwindcss'
}

get_tailwindcss_version() {
    local tailwindcss_bin
    tailwindcss_bin="${1:-./tailwindcss}"

    local help_output="$(NO_COLOR=1 "${tailwindcss_bin}" --help)"
    local first_line="${help_output%%$'\n'*}"
    test -n "${first_line}" || return 1
    local version="${first_line##*tailwindcss*v}"
    version="${version%%[^0-9.]*}"
    test -n "${version}" || return 1
    printf -- '%s\n' "${version}"
}

record_tailwindcss_version() {
    test -s /app/common/third_party_versions.py || return 0

    local version="$(get_tailwindcss_version "$@")"

    printf -- "tailwindcss_version = '%s'\n" "${version}" >> /app/common/third_party_versions.py
}

dest_dir="$(bin_directory "$@")"
work_dir="$(mktemp -d)"
_cleanup() {
    rm -v -rf -- "${work_dir}"
}
trap '_cleanup' EXIT
cd "${work_dir}"

for _attempt in {1..5}; do
    [[ -x ./asfald ]] || download_asfald
    download_asfald latest && break
    sleep "${_attempt}"
done; unset -v _attempt ;

download_tailwindcss
install -v -t "${dest_dir}" tailwindcss

record_tailwindcss_version "${dest_dir}/tailwindcss"

