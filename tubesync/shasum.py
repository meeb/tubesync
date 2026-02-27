#!/usr/bin/env python3

import argparse
import difflib
import hashlib
import platform
import re
import sys
from pathlib import Path

# Buffer size to match common coreutils I/O block size
CHUNK_SIZE = (1024) * 32 # KiB

# Script name without extension
PROG_NAME = Path(__file__).stem

# Versioning
VERSION = (1, 0, 1)
VERSION_STR = "v" + ".".join(map(str, VERSION))

def parse_args():
    """Configures and returns command line arguments."""
    parser = argparse.ArgumentParser(
        prog=PROG_NAME,
        description="Verify file checksums, enforcing strict line formatting and skipping missing files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"Example:\n  python3 {PROG_NAME}.py -a sha256 sums.txt\n  cat sha256sums.txt | python3 {PROG_NAME}.py"
    )
    parser.add_argument("-a", "--algorithm", default="sha256",
                        help="checksum algorithm to use (default: sha256)")
    parser.add_argument("file", nargs="?", default="-",
                        help="checksum file to read (default: '-' for stdin)")
    parser.add_argument("-v", "--version", action="version",
                        version=f"%(prog)s {VERSION_STR}")
    return parser.parse_args()

def get_algo_suggestion(word, available):
    """Encapsulates the ranking and matching logic."""

    def get_stable_matches(word, possibilities, *, n = 3, cutoff = 0.6, lookup = None):
        size = len(possibilities)
        if lookup is None:
            lookup = {name: i for i, name in enumerate(possibilities)}
        matches = difflib.get_close_matches(word, possibilities, n=size, cutoff=cutoff)
        def score_and_priority(name):
            score = difflib.SequenceMatcher(None, word, name).ratio()
            word_nums = re.findall(r'\d+', word)
            name_nums = re.findall(r'\d+', name)
            struct_boost = (cutoff / 2) if word_nums and all(num in name_nums for num in word_nums) else 0
            weighted_score = struct_boost + score
            bucket = int(10 * weighted_score)
            return (-bucket, lookup.get(name, size), -weighted_score)
        return sorted(matches, key=score_and_priority)[:n]

    def algo_priority_key(name):
        nums = re.findall(r'\d+', name)
        # Use the first number found (e.g., 3 for sha3_512)
        size = int(nums[0]) if nums else 0
        # Use the second number found (e.g., 512 for sha3_512)
        sub_size = int(nums[1]) if 1 < len(nums) else 0

        # Ranking Logic
        if not name.startswith('sha'):
            return (4, -size, -sub_size)
        elif 'sha1' == name: # lowest priority sha
            rank = 3
        elif 'sha384' == name: # disambiguation
            rank = 2
        elif name.startswith('sha3'): # match sha-3
            rank = 0
        elif name.startswith('shake'):
            rank = 1
        else:
            rank = 2

        # Primary bit-depth proximity to 256-bit
        dist_256 = abs(size - 256)
        # Secondary bit-depth proximity to 256-bit
        dist_sub_256 = abs(sub_size - 256) if sub_size else 0

        # Sort by: Family Rank (asc), then proximity to 256-bit (asc)
        return (rank, dist_256, dist_sub_256)

    algo_sorted = sorted(available, key=algo_priority_key)
    algo_lookup = {name: i for i, name in enumerate(algo_sorted)}
    matches = get_stable_matches(word, algo_sorted, lookup=algo_lookup, n=1)
    return matches[0] if matches else None

def validate_algo(algo_name):
    """Checks if the algorithm is supported; suggests matches with custom family priority."""
    available = hashlib.algorithms_available
    algo_lower = algo_name.lower()

    if algo_lower not in available:
        suggestion = get_algo_suggestion(algo_lower, available)

        error_msg = f"{PROG_NAME}: Error: Unsupported algorithm '{algo_name}'"
        if suggestion:
            error_msg += f". Did you mean '{suggestion}?'"

        print(error_msg, file=sys.stderr)
        sys.exit(1)
    return algo_lower

def get_input_and_format(file_arg):
    """Verifies argument is a file, handles stdin, and determines format."""
    if "-" == file_arg:
        label = "stdin"
        lines = sys.stdin.read().splitlines()
    else:
        def error_exit(message, /):
            print(f"{PROG_NAME}: {file_arg}: {message}", file=sys.stderr)
            sys.exit(1)

        label = file_arg
        p = Path(file_arg)
        if not p.exists():
            error_exit("No such file or directory")
        if not p.is_file():
            error_exit("Is not a regular file")

        lines = p.read_text(encoding='utf-8').splitlines()

    is_tag = False
    for line in lines:
        clean = line.strip()
        if not clean or clean.startswith('#'):
            continue
        if ' = ' in clean and '(' in clean and ')' in clean:
            is_tag = True
            break

    return lines, is_tag, label

def verify_checksums(lines, is_tag, label, algorithm):
    """Performs strict verification of hashes against local files."""
    exit_code = 0
    files_verified = 0
    format_errors = 0
    checksum_failures = 0
    is_windows = "Windows" == platform.system()
    hexdigest_args = []

    if is_tag:
        pattern = re.compile(rf'^{algorithm.upper()} \((.+)\) = ([a-fA-F0-9]+)$')
        algo_extractor = re.compile(r'^([a-zA-Z0-9]+) \(')
    else:
        pattern = re.compile(r'^([a-fA-F0-9]+) ([ \*])(.+)$')

    for line_no, line in enumerate(lines, 1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue

        match = pattern.match(line)
        if not match:
            msg = f"{label}:{line_no}: WARNING: improperly formatted line"
            if is_tag:
                found_match = algo_extractor.match(line)
                if found_match:
                    msg += f" (found {found_match.group(1)})"
            print(msg, file=sys.stderr)
            format_errors += 1
            exit_code = 1
            continue

        if is_tag:
            filename_str, expected_hash = match.groups()
        else:
            expected_hash, mode_char, filename_str = match.groups()
            if is_windows and ' ' == mode_char:
                msg = f"{filename_str}: WARNING: text conversion is not supported; hashing as binary"
                print(msg, file=sys.stderr)

        target_path = Path(filename_str)
        if not target_path.exists():
            continue

        try:
            hasher = hashlib.new(algorithm)
            with target_path.open('rb') as fb:
                for chunk in iter(lambda: fb.read(CHUNK_SIZE), b""):
                    hasher.update(chunk)

            hexdigest_args.clear()
            if algorithm.startswith('shake'):
                hexdigest_args.append(32)
            if hasher.hexdigest(*hexdigest_args) == expected_hash.lower():
                files_verified += 1
                print(f"{target_path}: OK")
            else:
                print(f"{target_path}: FAILED")
                checksum_failures += 1
                exit_code = 1
        except (IOError, OSError) as e:
            print(f"{target_path}: FAILED (Error: {e})")
            checksum_failures += 1
            exit_code = 1

    def warning(msg, singular, plural, /, count):
        if 0 < count:
            alt = plural if 1 < count else singular
            prefix = f"{PROG_NAME}: WARNING: {count} "
            print(prefix + msg.format(alt), file=sys.stderr)
    warning("line{0} improperly formatted", " is", "s are", count=format_errors)
    warning("computed checksum{0} did NOT match", "", "s", count=checksum_failures)
    if 0 == files_verified:
        exit_code = 1
        msg = f"{PROG_NAME}: WARNING: {label}: no file was verified"
        print(msg, file=sys.stderr)

    sys.exit(exit_code)

if __name__ == "__main__":
    args = parse_args()
    algo = validate_algo(args.algorithm)
    content, tag_mode, file_label = get_input_and_format(args.file)
    verify_checksums(content, tag_mode, file_label, algo)

