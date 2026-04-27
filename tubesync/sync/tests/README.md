# tests

This directory contains TubeSync's Django test modules.

The tests were split from the old `sync/tests.py` into smaller files to make
failures easier to locate and debug.

Notable files include:

- `test_format_matching.py` for format matcher tests
- `test_filepath.py` for media filepath and filename tests
- `test_media.py` for media model tests
- `test_response_filtering.py` for response filtering tests
- `test_tasks.py` for task-related tests
- `test_frontend.py` for frontend and view tests
- `fixtures.py` for shared test metadata loading
