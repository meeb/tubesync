#!/usr/bin/env sh

dir='/run/service'
svc_path() (
    cd "${dir}"
    realpath -e -s "$@"
)

if [ 0 -eq $# ]
then
    set -- \
        $( cd "${dir}" && svc_path tubesync*-worker ) \
        "$( svc_path gunicorn )" \
        "$( svc_path nginx )"
fi

for service in $( svc_path "$@" )
do
    printf -- 'Restarting %-28s' "${service#${dir}/}..."
    _began="$( date '+%s' )"
    /command/s6-svc -wr -r "${service}"
    _ended="$( date '+%s' )"
    printf -- '\tcompleted (in %2.1d seconds).\n' \
        "$( expr "${_ended}" - "${_began}" )"
done
unset -v _began _ended service
