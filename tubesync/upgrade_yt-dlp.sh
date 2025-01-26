#!/usr/bin/env bash

warning_message() {
    cat <<EOM
Please report any issues that you have encountered before updating yt-dlp.

This is a tool to assist developers with debugging YouTube issues.
It should not be used as an alternative to updating container images!
EOM
} 1>&2

pip3() {
    local pip_runner pip_whl run_whl

    # pipenv
    pip_runner='/usr/lib/python3/dist-packages/pipenv/patched/pip/__pip-runner__.py'
    test -s "${pip_runner}" || pip_runner=''

    # python3-pip-whl
    pip_whl="$(ls -1r /usr/share/python-wheels/pip-*-py3-none-any.whl | head -n 1)"
    run_whl="${pip_whl}/pip"

    python3 "${pip_runner:-"${run_whl}"}" "$@"
}

warning_message
test -n "${TUBESYNC_DEBUG}" || exit 1

# Use the flag added in 23.0.1, if possible.
# https://github.com/pypa/pip/pull/11780
break_system_packages='--break-system-packages'
pip_version="$(pip3 --version | awk '$1 = "pip" { print $2; exit; }')"
if [[ "${pip_version}" < "23.0.1" ]]; then
    break_system_packages=''
fi

pip3 install --upgrade ${break_system_packages} yt-dlp

