#!/usr/bin/env sh

_dir='/run/service'
svc_path() (
    cd "${_dir}" &&
    realpath -e -s "$@"
)

_services="$(/command/s6-rc-db atomics user user2)"
is_a_longrun() {
    if [ 'longrun' = "$(/command/s6-rc-db type "$1")" ]
    then
        return 0
    fi
    return 1
}
only_longruns() {
    local service
    for service in "$@"
    do
        if is_a_longrun "${service}"
        then
            printf -- '%s\n' "${service}"
        fi
    done
}
_longruns="$(only_longruns ${_services})"

if [ 0 -eq $# ]
then
    set -- $(/command/s6-rc -e -a list)
fi

for arg in "$@"
do
    _svcs="$(/command/s6-rc -e list "${arg}")"
    for service in $(svc_path $(only_longruns ${_svcs}))
    do
        printf -- 'Restarting %-28s' "${service#${_dir}/}..."
        _began="$( date '+%s' )"
        /command/s6-svc -wr -r "${service}"
        _ended="$( date '+%s' )"
        printf -- '\tcompleted (in %2.1d seconds).\n' \
            "$( expr "${_ended}" - "${_began}" )"
    done
done
unset -v _began _ended _svcs arg service
unset -v _dir _longruns _services
