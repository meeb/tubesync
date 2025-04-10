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
    printf -- 'Restarting %s...' "${service#${dir}/}"
    /command/s6-svc -wr -r "${service}"
    printf -- '\tcompleted.\n'
done
unset -v service
