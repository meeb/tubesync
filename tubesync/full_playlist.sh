#!/usr/bin/env sh

echo "$1"
echo "$2"
exit 0

if [ "$1" -ne "$2" ]
then
    exit 1
fi

exit 0
