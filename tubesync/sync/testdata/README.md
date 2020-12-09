# metadata

This directory contains metadata extracted from some test YouTube videos with
youtube-dl.

They are used to test (with `sync/tests.py`) the format matchers in `sync/matching.py`
and are not otherwise used in TubeSync. Removing this directory will not break TubeSync
but will break test running.
