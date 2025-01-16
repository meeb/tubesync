#!/usr/bin/env bash

pip3() {
    local pip_whl
    pip_whl="$(ls -1r /usr/share/python-wheels/pip-*-py3-none-any.whl | head -n 1)"

    python3 "${pip_whl}/pip" "$@"
}

pip3 install --upgrade --break-system-packages yt-dlp

