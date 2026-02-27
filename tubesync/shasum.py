#!/usr/bin/env python3

import argparse
import difflib
import hashlib
import platform
import queue
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# Buffer size to match common coreutils I/O block size
CHUNK_SIZE = (1024) * 32 # KiB

# Script name without extension
PROG_NAME = Path(__file__).stem

# Versioning
VERSION = (1, 1, 1)
VERSION_STR = "v" + ".".join(map(str, VERSION))

def _std_base(*args, **kwargs):
    try:
        print(*args, **kwargs)
    except BrokenPipeError:
        # Python's recommended way to handle SIGPIPE silently
        # 128 + 13 (SIGPIPE) = 141
        sys.exit(141)

def stdout(*args, **kwargs):
    """Prints strictly to sys.stdout, ignoring any 'file' keyword argument."""
    kwargs.pop('file', None)
    _std_base(*args, file=sys.stdout, **kwargs)

def stderr(*args, **kwargs):
    """Prints strictly to sys.stderr, ignoring any 'file' keyword argument."""
    kwargs.pop('file', None)
    _std_base(*args, file=sys.stderr, **kwargs)

def parse_args():
    """Configures and returns command line arguments."""
    parser = argparse.ArgumentParser(
        prog=PROG_NAME,
        description="Verify file checksums, enforcing strict line formatting and skipping missing files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Examples:
  Standard (sha256sum style):
    python3 {PROG_NAME}.py sums.txt

  BSD Tag style (md5 -r style):
    python3 {PROG_NAME}.py -a md5 sums.txt

  Piped input (strict UTF-8, no BOM):
    cat sha256sums.txt | python3 {PROG_NAME}.py

Notes:
  - Missing files are skipped (non-fatal).
  - Uses all available CPU cores for hashing.
  - Rejects UTF-16 manifests to ensure audit integrity.
"""
    )
    parser.add_argument("-a", "--algorithm", default="sha256",
                        help="checksum algorithm to use (default: sha256)")
    parser.add_argument("file", nargs="?", default="-",
                        help="checksum file to read (default: '-' for stdin)")
    parser.add_argument("-v", "--version", action="version",
                        version=f"%(prog)s {VERSION_STR} (Python {platform.python_version()})")
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
        # PEP 634: Structural Pattern Matching
        match name:
            case n if not n.startswith('sha'):
                return (4, -size, -sub_size)
            case 'sha1': # lowest priority sha
                rank = 3
            case 'sha384': # disambiguation
                rank = 2
            case n if n.startswith('sha3'): # match sha-3
                rank = 0
            case n if n.startswith('shake'):
                rank = 1
            case _:
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

        stderr(error_msg)
        sys.exit(1)
    return algo_lower

def get_input_and_format(file_arg):
    """Verifies argument is a file, handles stdin, and determines format."""
    def error_exit(message, /, label):
        stderr(f"{PROG_NAME}: error: {label}: {message}")
        sys.exit(1)

    if "-" == file_arg:
        label = "stdin"
        raw_data = sys.stdin.buffer.read()

        if raw_data.startswith(b'\xef\xbb\xbf'):
            error_exit("UTF-8 BOM detected; please provide a clean stream", label)
        if raw_data.startswith((b'\xff\xfe', b'\xfe\xff')):
            error_exit("UTF-16 BOM detected; only UTF-8 (without BOM) is supported", label)

        try:
            lines = raw_data.decode('utf-8').splitlines()
        except UnicodeDecodeError:
            error_exit("invalid UTF-8 encoding", label)
    else:
        label = file_arg
        p = Path(file_arg)
        if not p.exists():
            error_exit("No such file or directory")
        if not p.is_file():
            error_exit("Is not a regular file")
        with p.open('rb') as f:
            raw_data = f.read(2)
            if raw_data.startswith((b'\xff\xfe', b'\xfe\xff')):
                error_exit("UTF-16 manifest detected; only UTF-8 (with/without BOM) is supported", label)

        lines = p.read_text(encoding='utf-8-sig').splitlines()

    # Standard: Starts with hex (min 32 chars for MD5) followed by space/asterisk
    std_prefix = re.compile(r'^[a-fA-F0-9]{32,}\s+[\ \*]')
    # Tag: Starts with Alpha-numeric, ends with '=' and hex
    tag_suffix = re.compile(r'^[a-zA-Z0-9]+\s+\(.+\)\s+=\s+[a-fA-F0-9]+$')
    line_data = { 'counts': {}, }
    def record_line(n, line, key, /, value = None, *, set_format = False):
        if n not in line_data:
            line_data[n] = {'value': line, 'skipped': False}
        line_data[n][key] = True if value is None else value
        if set_format:
            line_data[n]['format'] = key
        line_data['counts'][key] = 1 + line_data['counts'].get(key, 0)

    for n, line in enumerate(lines):
        clean = line.strip()
        if not clean or clean.startswith('#'):
            record_line(n, line, 'skipped')
            if clean:
                record_line(n, line, 'comment')
            continue

        if std_prefix.match(clean):
            record_line(n, line, 'standard', set_format=True)
        elif tag_suffix.match(clean):
            record_line(n, line, 'tag', set_format=True)
        else:
            record_line(n, line, 'unknown', set_format=True)

    is_tag = line_data['counts'].get('tag', 0) > line_data['counts'].get('standard', 0)

    return line_data, is_tag, label

def verify_checksums(line_data, is_tag, label, algorithm):
    """Performs strict verification of hashes against local files."""
    abs_cwd = Path().resolve(strict=True)
    checksum_failures = 0
    exit_code = 0
    file_buffers = 32
    file_buffer_size = (1024 * 1024) * 1 # MiB
    file_buffer_pool = queue.Queue()
    files_verified = 0
    format_errors = 0
    hexdigest_args = []
    is_windows = "Windows" == platform.system()
    max_pending_tasks = 50_000
    semaphore = threading.Semaphore(max_pending_tasks)
    tasks = []

    if is_tag:
        pattern = re.compile(rf'^{algorithm.upper()} \((.+)\) = ([a-fA-F0-9]+)$')
        algo_extractor = re.compile(r'^([a-zA-Z0-9]+) \(')
    else:
        pattern = re.compile(r'^([a-fA-F0-9]+) ([ \*])(.+)$')

    def fill_buffer(target_path, /, stat = None, pool = file_buffer_pool, max_size = file_buffer_size):
        """Attempts to grab a buffer from the pool and fill it with file content."""
        try:
            if stat is None:
                stat = target_path.stat()
            if stat.st_size > max_size:
                return None, 0
            buf = pool.get_nowait()
            with target_path.open('rb') as f:
                actual_read = f.readinto(buf)
            return buf, actual_read
        except (queue.Empty, IOError, OSError):
            return None, 0

    def return_buffer(buffer, /, pool = file_buffer_pool):
        pool.put(buffer)

    for _ in range(file_buffers):
        return_buffer(bytearray(file_buffer_size))

    for line_no, data in line_data.items():
        line = data.get('value')
        if 'counts' == line_no or data.get('skipped'):
            continue
        else:
            line_no += 1 # 0-indexed to 1-indexed
        if isinstance(line, str):
            line = line.strip()

        match = pattern.match(line)
        if not match:
            msg = f"{label}:{line_no}: WARNING: improperly formatted line"
            if is_tag:
                found_match = algo_extractor.match(line)
                if found_match:
                    msg += f" (found {found_match.group(1)})"
            stderr(msg)
            format_errors += 1
            exit_code = 1
            continue

        if is_tag:
            filename_str, expected_hash = match.groups()
        else:
            expected_hash, mode_char, filename_str = match.groups()
            if is_windows and ' ' == mode_char:
                msg = f"{label}:{line_no}: {filename_str}: WARNING: text conversion is not supported; hashing as binary"
                stderr(msg)

        if '#' in filename_str:
            msg = (
                f"{label}:{line_no}: WARNING: filename contained a "
                "'#' character; inline comments are not supported and "
                "this will be treated as part of the literal filename."
            )
            stderr(msg)

        target_path = Path(filename_str)

        # Security: Prevent Path Traversal
        # Skip files outside the directory to prevent traversal attacks
        # Resolve to absolute path and check if it's within CWD
        msg = f"{label}:{line_no}: WARNING: "
        try:
            abs_target = target_path.resolve(strict=False)
            if abs_cwd not in abs_target.parents and abs_target != abs_cwd:
                msg += "skipping path that is outside the current directory"
                stderr(msg)
                continue
        except (OSError, RuntimeError) as e:
            msg += f"skipping path that could not be resolved: {e}"
            stderr(msg)
            continue

        if not (target_path.exists() and target_path.is_file()):
            continue

        stat = target_path.stat()
        tasks.append((
            stat.st_size, # sorting key
            target_path, stat, expected_hash,
            *(fill_buffer(target_path, stat=stat)),
        ))

    def perform_hash(algorithm, target_path, expected_hash, buffer=None, actual_len=0, stat = None):
        def check_file_integrity(target_path, original_stat):
            """Checks if file metadata matches the original scan."""
            if original_stat is None:
                return None
            try:
                current = target_path.stat()
                changed = (
                    current.st_mtime != original_stat.st_mtime or
                    current.st_size  != original_stat.st_size  or
                    current.st_ino   != original_stat.st_ino   or
                    current.st_ctime != original_stat.st_ctime
                )
                return "File modified during processing" if changed else None
            except (OSError, RuntimeError):
                return "Metadata access failed"

        try:
            # Pre-hash integrity check
            if err := check_file_integrity(target_path, stat):
                if 'File modified' in err:
                    err = "File modified since scan"
                return target_path, False, err

            hasher = hashlib.new(algorithm)
            if buffer is not None:
                hasher.update(buffer[:actual_len])
                return_buffer(buffer)
                buffer = None
            else:
                with target_path.open('rb') as fb:
                    if sys.version_info >= (3, 11):
                        hasher = hashlib.file_digest(fb, algorithm)
                    else:
                        for chunk in iter(lambda: fb.read(CHUNK_SIZE), b""):
                            hasher.update(chunk)

            # Post-hash integrity check
            if err := check_file_integrity(target_path, stat):
                return target_path, False, err

            hexdigest_args.clear()
            if algorithm.startswith('shake'):
                hexdigest_args.append(len(expected_hash) // 2)
            is_ok = hasher.hexdigest(*hexdigest_args) == expected_hash.lower()
            return target_path, is_ok, None
        except (IOError, OSError) as e:
            return target_path, False, str(e)
        finally:
            if buffer is not None:
                return_buffer(buffer)

    def harvest(future, path):
        nonlocal files_verified, checksum_failures, exit_code
        # Release semaphore slot so a new task can be submitted.
        semaphore.release()
        try:
            _, ok, err = future.result()
            msg = f"{path}: "
            if ok:
                msg += "OK"
                files_verified += 1
            else:
                msg += "FAILED"
                if err:
                    msg += f" (Error: {err})"
                checksum_failures += 1
                exit_code = 1
            stdout(msg)
        except Exception as e:
            checksum_failures += 1
            exit_code = 1
            stdout(f"{path}: FAILED (Unexpected Error: {e!r})")

    tasks.sort(key=lambda x: x[0], reverse=True)
    with ThreadPoolExecutor() as executor:
        while tasks:
            semaphore.acquire()

            _, target_path, stat, expected_hash, buffer, blen = tasks.pop()
            if buffer is None:
                assigned_buffer, actual_read = fill_buffer(target_path, stat=stat)
                if assigned_buffer and actual_read:
                    buffer = assigned_buffer
                    blen = actual_read
                elif assigned_buffer:
                    return_buffer(assigned_buffer)

            future = executor.submit(
                perform_hash,
                algorithm,
                target_path,
                expected_hash,
                buffer,
                blen,
                stat,
            )
            harvester = lambda f, p=target_path: harvest(f, p)
            future.add_done_callback(harvester)

    def warning(msg, singular, plural, /, count):
        if 0 < count:
            alt = plural if 1 < count else singular
            prefix = f"{PROG_NAME}: WARNING: {count} "
            stderr(prefix + msg.format(alt))
    warning("line{0} improperly formatted", " is", "s are", count=format_errors)
    warning("computed checksum{0} did NOT match", "", "s", count=checksum_failures)
    if 0 == files_verified:
        exit_code = 1
        msg = f"{PROG_NAME}: WARNING: {label}: no file was verified"
        stderr(msg)

    sys.exit(exit_code)

if __name__ == "__main__":
    args = parse_args()
    algo = validate_algo(args.algorithm)
    content, tag_mode, file_label = get_input_and_format(args.file)
    verify_checksums(content, tag_mode, file_label, algo)

