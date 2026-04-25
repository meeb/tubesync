#!/usr/bin/env bash

# requires:
# - curl
# - python3

set -eu
HERE="$(dirname "$(realpath "$0")")"
source "${HERE}/download_gh_release.func.inc.sh"
source "${HERE}/verify_digest.func.inc.sh"
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

    TMPDIR="$(realpath .)" ./asfald -o 'tailwindcss' -p '${path}/sha256sums.txt' "https://github.com/${owner}/${repo}/releases/latest/download/${TW_BIN}" && \
        chmod -v a+rx tailwindcss
    local latest_version="$(get_tailwindcss_version ./tailwindcss)"
    test -n "${latest_version}" || return 1
    local url="https://github.com/${owner}/${repo}/releases/download/v${latest_version}/${TW_BIN}"
    local latest_digest="$(./asfald-latest --get-hash "${url}")"
    verify_digest "${latest_digest}" 'tailwindcss' || return 1
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

download_asfald
download_asfald latest

download_tailwindcss
install -v -t "${dest_dir}" tailwindcss

record_tailwindcss_version "${dest_dir}/tailwindcss"

