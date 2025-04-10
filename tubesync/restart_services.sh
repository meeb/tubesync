#!/usr/bin/env sh

if [ 0 -eq $# ]
then
    set -- \
        /run/service/tubesync*-worker \
        /run/service/gunicorn \
        /run/service/nginx
fi

for service in "$@"
do
    printf 1>&2 -- 'Restarting %s... ' "${service}"
    /command/s6-svc -wr -r "${service}"
    printf 1>&2 -- 'completed.\n'
done
unset -v service
