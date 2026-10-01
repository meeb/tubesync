#!/usr/bin/env bash

verify_digest() {
    local digest="${1}"
    local filename="${2}"

    local algo="${digest%%:*}"
    local checksum="${digest##*:}"
    printf -- '%s (%s) = %s\n' "${algo^^}" "${filename}" "${checksum,,}" | "${HERE}/shasum.py" -a "${algo,,}" -
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
            local _tmpdir="$(realpath .)"
            download_gh_release "${owner}" "${repo}" 'checksums.txt' 'latest'
            local latest_version="${resolved_version}"
            [[ -n "${latest_version}" ]]

            local download_url="https://github.com/${owner}/${repo}/releases/download"

            local url="${download_url}/${latest_version}/asfald-${arch}-${os}"

            TMPDIR="${_tmpdir}" \
                ./asfald -q -w -- "${url}" && \
                "${HERE}/shasum.py" -a 'sha256' 'checksums.txt' && \
                rm -f 'checksums.txt' && \
                chmod 'a+rx' "asfald-${arch}-${os}" && \
                mv -v -f -T "asfald-${arch}-${os}" 'asfald-latest'
            local latest_digest="$(./asfald-latest --get-hash -- "${url}")"
            verify_digest "${latest_digest}" 'asfald-latest' || { rm -f './asfald-latest' ; return 1; }

            url="${download_url}/${tag}/asfald-${arch}-${os}"
            local tag_digest="$(./asfald-latest --get-hash -- "${url}")"
            verify_digest "${tag_digest}" 'asfald' || { rm -f './asfald' && TMPDIR="${_tmpdir}" ./asfald-latest -qv -o 'asfald' -- "${url}" && chmod 'a+rx' 'asfald' ; }
            ;;
        (*)
            curl -fsSLo '.mirrored-checksums.txt' -- "${sums_url}"
            download_gh_release "${owner}" "${repo}" 'checksums.txt' "${tag}"

            download_gh_release "${owner}" "${repo}" "asfald-${arch}-${os}" "${tag}" && \
                cat '.mirrored-checksums.txt' 'checksums.txt' | "${HERE}/shasum.py" -a sha256 - && \
                rm -f '.mirrored-checksums.txt' 'checksums.txt' && \
                chmod 'a+rx' "asfald-${arch}-${os}" && \
                mv -v -f -T "asfald-${arch}-${os}" 'asfald'
            ;;
    esac

}
