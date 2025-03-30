#!/usr/bin/env sh

echo "$1"
echo "$2"
exit 0

if [ 'NA' != "$2" ] && [ "$1" != "$2" ]
then
    exit 1
fi

exit 0
