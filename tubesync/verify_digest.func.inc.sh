#!/usr/bin/env bash

verify_digest() {
    local digest="${1}"
    local filename="${2}"

    local algo="${digest%%:*}"
    local checksum="${digest##*:}"
    printf -- '%s (%s) = %s\n' "${algo^^}" "${filename}" "${checksum,,}" | "${HERE}/shasum.py" -a "${algo,,}" -
}
