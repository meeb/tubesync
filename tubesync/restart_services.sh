#!/usr/bin/env sh

_dir='/run/service'
svc_path() (
    cd "${_dir}" &&
    realpath -e -s "$@"
)

_bundles="$(/command/s6-rc-db list bundles)"
is_a_bundle() {
    local bundle
    for bundle in ${_bundles}
    do
        if [ "$1" = "${bundle}" ]
        then
            return 0
        fi
    done
    return 1
}

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
    set -- $(only_longruns $(/command/s6-rc -a list))
fi

for arg in "$@"
do
    _svcs="${arg}"
    if is_a_bundle "${arg}"
    then
        _svcs="$(only_longruns $(/command/s6-rc list "${arg}"))"
    fi
    for service in $(svc_path ${_svcs})
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
unset -v _bundles _dir _longruns _services
