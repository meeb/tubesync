#!/usr/bin/env sh

# For setting single line variables in the environment or output
set_sl_var() { local f='%s=%s\n' ; printf -- "${f}" "$@" ; } ;

# Used together to set multiple line variables in the environment or output
mk_delim() { printf -- '"%s_EOF_%d_"' "$1" "${RANDOM}" ; } ;
open_ml_var() { local f=''\%'s<<'\%'s\n' ; printf -- "${f}" "$2" "$1" ; } ;
close_ml_var() { local f='%s\n' ; printf -- "${f}" "$1" ; } ;
        
