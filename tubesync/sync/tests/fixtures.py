from django.conf import settings

metadata_filepath = settings.BASE_DIR / 'sync' / 'testdata' / 'metadata.json'
with open(metadata_filepath, 'rt') as file:
    metadata = file.read()
metadata_hdr_filepath = settings.BASE_DIR / 'sync' / 'testdata' / 'metadata_hdr.json'
with open(metadata_hdr_filepath, 'rt') as file:
    metadata_hdr = file.read()
metadata_60fps_filepath = settings.BASE_DIR / 'sync' / 'testdata' / 'metadata_60fps.json'
with open(metadata_60fps_filepath, 'rt') as file:
    metadata_60fps = file.read()
metadata_60fps_hdr_filepath = settings.BASE_DIR / 'sync' / 'testdata' / 'metadata_60fps_hdr.json'
with open(metadata_60fps_hdr_filepath, 'rt') as file:
    metadata_60fps_hdr = file.read()
metadata_20230629_filepath = settings.BASE_DIR / 'sync' / 'testdata' / 'metadata_2023-06-29.json'
with open(metadata_20230629_filepath, 'rt') as file:
    metadata_20230629 = file.read()
metadata_issue_499_1080p50_filepath = settings.BASE_DIR / 'sync' / 'testdata' / 'metadata_issue_499_1080p50.json'
with open(metadata_issue_499_1080p50_filepath, 'rt') as file:
    metadata_issue_499_1080p50 = file.read()

metadata_issue_499_premium_filepath = settings.BASE_DIR / 'sync' / 'testdata' / 'metadata_issue_499_premium.json'
with open(metadata_issue_499_premium_filepath, 'rt') as file:
    metadata_issue_499_premium = file.read()
all_test_metadata = {
    'boring': metadata,
    'hdr': metadata_hdr,
    '60fps': metadata_60fps,
    '60fps+hdr': metadata_60fps_hdr,
    '20230629': metadata_20230629,
    'issue499_1080p50': metadata_issue_499_1080p50,
    'issue499_premium': metadata_issue_499_premium,
}
