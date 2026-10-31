#!/usr/bin/env python3
"""Extract tag-format checksums from HTTP response headers."""

import base64
import binascii
import re
import sys

from argparse import ArgumentParser
from enum import Enum
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, unquote

import requests


# --- Metadata ---
NAME = 'htagsum'
VERSION = '1.0.2'
USER_AGENT = f'{NAME}/{VERSION}'
TIMEOUT = 30


# --- Exception Classes ---
class HashExtractionError(Exception):
    """Failed to extract or decode hash value."""

class DownloadError(Exception):
    """Failed to download or save file."""

# --- Enumerations ---
class HashAlgorithm(Enum):
    """Supported hash algorithms and their header names."""
    MD5 = ['x-ms-blob-content-md5', 'Content-MD5']
    SHA256 = ['x-ms-blob-content-sha256', 'X-SHA256', 'Content-SHA256']
    SHA512 = ['x-ms-blob-content-sha512', 'X-SHA512', 'Content-SHA512']

# --- Hashing ---
class MultiHasher:
    """Compute multiple hash algorithms simultaneously."""

    def __init__(self):
        self._hashers = {
            algo: hashlib.new(algo.name.lower())
            for algo in HashAlgorithm
        }

    def update(self, chunk: bytes) -> None:
        """Update all hash objects with chunk."""
        for hasher in self._hashers.values():
            hasher.update(chunk)

    def hexdigest(self) -> dict[str, str]:
        """Return dictionary of algorithm name to hex digest."""
        return {
            algo.name: hasher.hexdigest()
            for algo, hasher in self._hashers.items()
        }

# --- Helper Functions ---
def extract_filename(content_disposition: str, fallback: str) -> str:
    """Extract filename from Content-Disposition header with RFC 6266 support."""
    # Match both filename and filename*
    match = re.search(r'filename\*?=(?:"([^"]*)"|([^;,\s]*))', content_disposition)
    if match:
        filename = match.group(1) or match.group(2)
        return unquote(filename).strip()
    return fallback

def get_filename_from_url(url: str) -> str:
    """Extract filename from URL path."""
    parsed = urlparse(url)
    filename = unquote(Path(parsed.path).name)
    return filename if filename else 'download'

def fetch_response(url: str, use_get: bool = False) -> requests.Response:
    """Fetch HTTP response with appropriate method."""
    headers = {'User-Agent': USER_AGENT}
    method = requests.get if use_get else requests.head
    timeout = TIMEOUT if use_get else TIMEOUT // 2

    response = method(
        url,
        headers=headers,
        allow_redirects=True,
        timeout=timeout,
        stream=use_get
    )
    response.raise_for_status()
    return response

def decode_hash(algo_name: str, b64_value: str) -> str:
    """Decode base64-encoded hash to hex string."""
    try:
        return binascii.hexlify(base64.b64decode(b64_value)).decode('utf-8')
    except (binascii.Error, ValueError) as e:
        raise HashExtractionError(f'Failed to decode {algo_name}: {e}') from e

def save_file(filename: str, response: requests.Response) -> None:
    """Download and save file in 4 KiB chunks."""
    chunk_size=4096
    hasher = MultiHasher()

    try:
        with open(filename, 'wb') as f:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    f.write(chunk)
                    hasher.update(chunk)
    except OSError as e:
        raise DownloadError(f'Failed to write {filename}: {e}') from e
    else:
        sys.stderr.write(f'Successfully fetched: {filename}\n')
        return hasher.hexdigest()

def print_headers_verbose(headers: dict) -> None:
    """Print raw HTTP headers to stderr."""
    sys.stderr.write('--- Raw Headers ---\n')
    for key, value in headers.items():
        sys.stderr.write(f'{key}: {value}\n')
    sys.stderr.write('-------------------\n')

def extract_hashes(
    headers: dict,
    filename: str
) -> dict[str, str]:
    """Extract and decode all available hashes from headers."""
    hashes = {}

    for algo in HashAlgorithm:
        header_value = next(
            (headers.get(key) for key in algo.value if key in headers),
            None
        )

        if header_value:
            try:
                hex_value = decode_hash(algo.name, header_value)
                hashes[algo.name] = hex_value
            except HashExtractionError as e:
                sys.stderr.write(f'Error: {e}\n')

    return hashes

def main(argv: Optional[list[str]] = None) -> int:
    """Main entry point."""
    # Parse arguments
    parser = ArgumentParser(description='Extract tag-format checksums from HTTP headers.')
    parser.add_argument('url', nargs='?', help='The URL to fetch')
    parser.add_argument(
        '-d', '--download', '--fetch',
        action='store_true',
        dest='fetch',
        help='Download and save the file to disk'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Print raw HTTP headers to stderr'
    )
    parser.add_argument(
        '-V', '--version',
        action='version',
        version=f'{NAME} {VERSION}'
    )

    args = parser.parse_args(argv)

    if not args.url:
        parser.print_usage(sys.stderr)
        return 1

    try:
        # Fetch HTTP response
        response = fetch_response(args.url, use_get=args.fetch)
        headers = response.headers

        # Optionally print headers
        if args.verbose:
            print_headers_verbose(headers)

        # Determine filename
        cd = headers.get('Content-Disposition', '')
        filename = extract_filename(cd, get_filename_from_url(args.url))

        # Download file if requested
        if args.fetch:
            computed_hashes = save_file(filename, response)
        else:
            computed_hashes = dict()

        # Extract and print hashes
        header_hashes = extract_hashes(headers, filename)
        hashes = computed_hashes | header_hashes

        for algo, hex_value in hashes.items():
            sys.stdout.write(f'{algo} ({filename}) = {hex_value}\n')

        if not header_hashes:
            sys.stderr.write(f'Error: No supported hash headers found for {filename}\n')
            return 1

        return 0

    except requests.RequestException as e:
        sys.stderr.write(f'Error: Request failed ({e})\n')
        return 1
    except (DownloadError, HashExtractionError) as e:
        sys.stderr.write(f'Error: {e}\n')
        return 1
    except Exception as e:
        sys.stderr.write(f'Error: Unexpected error ({e})\n')
        return 1

if '__main__' == __name__:
    sys.exit(main(sys.argv[1:]))
