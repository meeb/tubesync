from django.conf import settings

def read_testdata(arg_dict, *, testdata_path=None):
    if testdata_path is None:
        testdata_path = settings.BASE_DIR / "sync" / "testdata"
    results = {}
    for k, filename in arg_dict.items():
        with open(testdata_path / filename, "rt") as file:
            results[k] = file.read()
    return results


_TESTDATA_FILES = {
    "boring": "metadata.json",
    "hdr": "metadata_hdr.json",
    "60fps": "metadata_60fps.json",
    "60fps+hdr": "metadata_60fps_hdr.json",
    "20230629": "metadata_2023-06-29.json",
    "issue499_1080p50": "metadata_issue_499_1080p50.json",
    "issue499_premium": "metadata_issue_499_premium.json",
    "expected_nfo": "expected_nfo.xml",
    "minimal": "minimal_metadata.json",
}

all_test_metadata = read_testdata(_TESTDATA_FILES)
