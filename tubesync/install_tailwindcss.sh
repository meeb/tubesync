#!/usr/bin/env bash

# requires:
# - curl
# - python3

set -eu
HERE="$(dirname "$(realpath "$0")")"
source "${HERE}/download_gh_release.func.inc.sh"

bin_directory() {
    local dir="${1:-/usr/local/bin}"

    if [ -d "${dir}" ]
    then
        printf -- '%s\n' "${dir}"
    else
        printf -- '%s\n' "$(dirname "${dir}")"
    fi
}

download_asfald() {
    local owner='asfaload' repo='asfald' tag='v0.6.0'
    local asfald_uri="${owner}/${repo}/releases/download/${tag}/checksums.txt"
    local sums_url="https://gh.checksums.asfaload.com/github.com/${asfald_uri}"

    local os
    case "$(uname -s)" in
        (Darwin) os='apple-darwin' ;;
        (Linux) os='unknown-linux-musl' ;;
    esac
    local arch
    case "$(uname -m)" in
        (aarch64|arm64) arch='aarch64' ;;
        (x86_64) arch='x86_64' ;;
    esac

    case "${1-}" in
        (latest)
            TMPDIR="$(realpath .)" \
                ./asfald -o 'asfald-latest' -w -p '${path}/checksums.txt' -- "https://github.com/${owner}/${repo}/releases/latest/download/asfald-${arch}-${os}" && \
                chmod -v a+rx asfald-latest
            local latest_version="$(./asfald-latest --version)"
            test -n "${latest_version}" || return 1
            local latest_digest="$(./asfald-latest --get-hash "https://github.com/${owner}/${repo}/releases/download/v${latest_version#asfald }/asfald-${arch}-${os}")"
            verify_digest "${latest_digest}" 'asfald-latest' || return 1
            ;;
        (*)
            download_gh_release "${owner}" "${repo}" "asfald-${arch}-${os}" "${tag}" && \
                curl -sSL -- "${sums_url}" | "${HERE}/shasum.py" -a sha256 - && \
                chmod -v a+rx "asfald-${arch}-${os}" && \
                mv -v "asfald-${arch}-${os}" asfald
            ;;
    esac

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

verify_digest() {
    local digest="${1}"
    local filename="${2}"

    local algo="${digest%%:*}"
    local checksum="${digest##*:}"
    printf -- '%s (%s) = %s\n' "${algo^^}" "${filename}" "${checksum,,}" | "${HERE}/shasum.py" -a "${algo,,}" -
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

