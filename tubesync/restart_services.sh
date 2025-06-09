#!/usr/bin/env sh

_dir='/run/service'
svc_path() (
    cd "${_dir}" &&
    realpath -e -s "$@"
)

_bundles="$(
    find '/etc/s6-overlay/s6-rc.d' -mindepth 2 -maxdepth 2 \
        -name 'type' \
        -execdir grep -F -q -e bundle '{}' ';' \
        -printf '%P\n' | \
        sed -e 's,/type$,,' ;
)"
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

if [ 0 -eq $# ]
then
    set -- $(/command/s6-rc list user | grep -v -e '-init$')
fi

for arg in "$@"
do
    _svcs="${arg}"
    if is_a_bundle "${arg}"
    then
        _svcs="$(/command/s6-rc list "${arg}" | grep -v -e '-init$')"
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
unset -v _bundles _dir
