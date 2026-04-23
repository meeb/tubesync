#!/usr/bin/env bash

# This script identifies which Font Awesome files are required based on your
# source code. It requires 'git' to be installed and run from a git repository.
# It uses git-grep to recursively search all tracked files regardless of nesting.

set -eu

# Helper to write to stdout with flag termination
stdout() {
    printf -- '%s\n' "$@"
}

# Helper to write to stderr with flag termination
stderr() {
    printf >&2 -- '%s\n' "$@"
}

# 1. Fail fast if git is not installed or the directory is not a repo
if ! command -v git &> /dev/null; then
    stderr 'Error: git is not installed or not in PATH.'
    exit 1
fi

if ! git rev-parse --is-inside-work-tree &> /dev/null; then
    stderr 'Error: This script must be run inside a git repository.'
    exit 1
fi

# Function to count occurrences using "$@" to preserve individual pathspecs
count_icons() {
    local pattern="$1"
    shift # Remove the pattern, leaving only pathspecs
    
    # We use -E for Extended Regex and -i for case-insensitivity
    git grep -Ei "$pattern" -- "$@" 2>/dev/null | wc -l
}

# Print header as a single call with multiple arguments
stdout \
    '--- Font Awesome Dependency Analysis ---' \
    'Foundations: fontawesome.min.css (Always Required)'

# 2. Analyze project source code for Font Awesome style prefixes
# Pathspecs are passed as individual single-quoted arguments
HAS_SOLID=$(count_icons 'fa-solid|fas fa-' '*.html' '*.js' '*.css')
HAS_BRANDS=$(count_icons 'fa-brands|fab fa-' '*.html' '*.js' '*.css')
HAS_REGULAR=$(count_icons 'fa-regular|far fa-' '*.html' '*.js' '*.css')
HAS_LIGHT=$(count_icons 'fa-light|fal fa-' '*.html' '*.js' '*.css')
HAS_THIN=$(count_icons 'fa-thin|fat fa-' '*.html' '*.js' '*.css')

# 3. Map findings to the specific self-hosted files required
if [ "${HAS_SOLID}" -gt 0 ]; then
    stdout 'Solid:     keep css/solid.min.css         and webfonts/fa-solid-900.woff2'
fi

if [ "${HAS_BRANDS}" -gt 0 ]; then
    stdout 'Brands:    keep css/brands.min.css        and webfonts/fa-brands-400.woff2'
fi

if [ "${HAS_REGULAR}" -gt 0 ]; then
    stdout 'Regular:   keep css/regular.min.css       and webfonts/fa-regular-400.woff2'
fi

if [ "${HAS_LIGHT}" -gt 0 ]; then
    stdout 'Light:     keep css/light.min.css         and webfonts/fa-light-300.woff2'
fi

if [ "${HAS_THIN}" -gt 0 ]; then
    stdout 'Thin:      keep css/thin.min.css          and webfonts/fa-thin-100.woff2'
fi

stdout '----------------------------------------'
