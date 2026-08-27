#!/usr/bin/env sh

stdout() {
    printf -- '%s\n' "${@}"
}

stderr() {
    printf -- '%s\n' "${@}"
} 1>&2

get_location_header() {
    url="${1}"; shift
    # First-match (head -n 1) is preferred as HTTP allows only one Location header
    location_header="$(curl -sSI -- "${url}" | grep -ie '^Location: ' | head -n 1)"
    # Remove \r from \r\n line-endings
    stdout "${location_header%$(printf '\r')}"
}

# Usage: download_gh_release owner repo template [version] [args...]
download_gh_release() {
    owner="${1}"; shift
    repo="${1}"; shift
    template="${1}"; shift

    _base_url="https://github.com/${owner}/${repo}/releases"

    # Optional: do not shift too far
    _target_version="${1:-latest}"
    [ 0 -ge $# ] || shift

    # Determine the version
    case "${_target_version}" in
        ('latest')
            resolved_version="$(get_location_header "${_base_url}/latest" | cut -d / -f 8)"
            case "${resolved_version:-/}" in
                ('/')
                    stderr \
                    "Error: Could not determine the latest release version for ${owner}/${repo}"
                    return 1
                    ;;
            esac
            ;;
        *)
            resolved_version="${_target_version}"
            ;;
    esac
    unset -v _target_version

    # Generate the filename using printf
    filename=$(printf -- "${template}" "${resolved_version}" "${@}")

    # Construct the download URL
    dl_url="${_base_url}/download/${resolved_version}/${filename}"
    unset -v _base_url

    stdout "Fetching from ${owner}/${repo}: ${filename}"

    curl --progress-bar --fail --location --remote-name --remote-time "${dl_url}"
}
