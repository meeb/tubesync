#!/usr/bin/env bash

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
