#!/usr/bin/env bash

pip3() {
    local pip_runner pip_whl run_whl

    # pipenv
    pip_runner='/usr/lib/python3/dist-packages/pipenv/patched/pip/__pip-runner__.py'

    # python3-pip-whl
    pip_whl="$(ls -1r /usr/share/python-wheels/pip-*-py3-none-any.whl | head -n 1)"
    run_whl="${pip_whl}/pip"

    python3 "${pip_runner}" "$@"
}

pip3 install --upgrade --break-system-packages yt-dlp

