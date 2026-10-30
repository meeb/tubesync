#!/usr/bin/env python3
import sys
import base64
import binascii
import os
import argparse

# --- EXTERNAL DEPENDENCY ---
# Install via: pip install requests
import requests
# ---------------------------

# Script Metadata
NAME = "htagsum"
VERSION = "1.0.1"
USER_AGENT = f"{NAME}/{VERSION}"
TIMEOUT = 30  # Base timeout in seconds

def htagsum():
    # 1. Setup CLI Arguments
    parser = argparse.ArgumentParser(
        description="Extract tag-format sums from HTTP headers."
    )
    parser.add_argument("url", nargs="?", help="The URL of the file")
    parser.add_argument("-d", "--download", "--fetch", action="store_true", dest="fetch",
                        help="Download and save the file to disk")
    parser.add_argument("-v", "--verbose", action="store_true", help="Print raw headers to stderr")
    parser.add_argument("-V", "--version", action="version", version=f"{NAME} {VERSION}")

    args = parser.parse_args()

    if not args.url:
        parser.print_usage(sys.stderr)
        sys.exit(1)

    # 2. Paranoid stdout trapping
    real_stdout = sys.stdout
    sys.stdout = sys.stderr

    # 3. Request Setup
    headers = {"User-Agent": USER_AGENT}

    try:
        if args.fetch:
            # Full GET request for downloading
            response = requests.get(args.url, headers=headers, allow_redirects=True,
                                    stream=True, timeout=TIMEOUT)
        else:
            # HEAD request uses half the timeout (integer division)
            response = requests.head(args.url, headers=headers, allow_redirects=True,
                                     timeout=TIMEOUT // 2)

        response.raise_for_status()
        h = response.headers

        if args.verbose:
            sys.stderr.write("--- Raw Headers ---\n")
            for k, v in h.items():
                sys.stderr.write(f"{k}: {v}\n")
            sys.stderr.write("-------------------\n")

    except Exception as e:
        sys.stderr.write(f"Error: Request failed ({e})\n")
        sys.exit(1)

    # 4. Determine Filename
    cd = h.get('Content-Disposition', '')
    if 'filename=' in cd:
        filename = cd.split('filename=')[-1].strip('"; ')
    else:
        filename = os.path.basename(args.url.split('?')[0])

    # 5. Handle File Download (4 KiB Chunks)
    if args.fetch:
        try:
            with open(filename, 'wb') as f:
                for chunk in response.iter_content(chunk_size=4096):
                    if chunk:
                        f.write(chunk)
            sys.stderr.write(f"Successfully fetched: {filename}\n")
        except Exception as e:
            sys.stderr.write(f"Error: Write failed for {filename} ({e})\n")
            sys.exit(1)

    # 6. Extract and Format Hashes
    hash_map = {
        "MD5": ["x-ms-blob-content-md5", "Content-MD5"],
        "SHA256": ["x-ms-blob-content-sha256", "X-SHA256", "Content-SHA256"],
        "SHA512": ["x-ms-blob-content-sha512", "X-SHA512", "Content-SHA512"]
    }

    found_any = False
    for algo, header_keys in hash_map.items():
        b64_val = next((h[k] for k in header_keys if k in h), None)

        if b64_val:
            try:
                hex_val = binascii.hexlify(base64.b64decode(b64_val)).decode('utf-8')
                # ONLY this write touches the real stdout
                real_stdout.write(f"{algo} ({filename}) = {hex_val}\n")
                found_any = True
            except Exception as e:
                sys.stderr.write(f"Error: Decoding {algo} failed ({e})\n")

    if not found_any:
        sys.stderr.write(f"Error: No supported hash headers found for {filename}\n")
        sys.exit(1)

    real_stdout.flush()
    sys.exit(0)

if __name__ == "__main__":
    htagsum()
