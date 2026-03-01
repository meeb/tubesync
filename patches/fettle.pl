#!/usr/bin/perl
# ======================================================================
# NAME: fettle.pl (Dynamic via $me)
# PURPOSE: A high-integrity utility for making exact, precise, and
#          repeatable changes to files using only perl-base.
# ======================================================================
use strict;
use warnings;
use Getopt::Long;
use File::Basename;

# Identify the script name dynamically for usage and error reporting
my $me = basename($0);

# --- 1. Global Constants & Indices ---
# Stat array indices for readability and easy maintenance
my $ST_SIZE  = 7;
my $ST_MTIME = 9;

# --- 2. Minimal Native Copy ---
# Performs a binary-safe copy without external dependencies.
# Used for creating temporary work files and original backups.
sub native_copy {
    my ($source_path, $destination_path) = @_;
    open(my $in,  '<', $source_path)      or die "$me: Could not read $source_path: $!";
    open(my $out, '>', $destination_path) or die "$me: Could not write $destination_path: $!";
    binmode($in);
    binmode($out);
    print $out $_ while <$in>;
    close($in);
    close($out);
}

# --- 3. Hashing Helpers ---
# Internal helper to get a file's fingerprint using the system 'cksum' utility.
sub _get_digest {
    my ($file_path, $algo) = @_;
    return "" unless -f $file_path;
    # Executes system cksum with specified algorithm (e.g., sha1, sha512).
    # Safely open a pipe without invoking a shell
    open(my $pipe, "-|", "/usr/bin/cksum", "-a", $algo, $file_path) or return "";
    my $cksum_output = <$pipe>;
    close($pipe);
    chomp($cksum_output);
    return "" unless $cksum_output;
    # Extract only the hex fingerprint from the tool's output.
    my ($fingerprint) = $cksum_output =~ /=\s+([a-f0-9]+)/i;
    return $fingerprint || "";
}

# Specific aliases for readability: sha1 for patch ID, sha512 for file integrity.
sub get_patch_id { return _get_digest(shift, "sha1"); }
sub get_file_fingerprint { return _get_digest(shift, "sha512"); }

# --- 4. Configuration & Globals ---
# Default fuzz_range allows the patcher to look 25 lines up/down for a match.
my ($dry_run, $revert, $clean, $fuzz_range) = (0, 0, 0, 25);
GetOptions(
    "dry-run" => \$dry_run,    # Pre-calculates offsets and validates files
    "fuzz=i"  => \$fuzz_range, # User-adjustable search range for line drifts
    "revert"  => \$revert,     # Restore files from .orig backups
    "clean"   => \$clean       # Delete .orig backups
);

my $patch_file = $ARGV[0] or die "Usage: $me [--dry-run|--revert|--clean] <patch_file>\n";
my $patch_hash = get_patch_id($patch_file);
die "$me: Could not generate ID for patch file.\n" unless $patch_hash;

# Locate a writable directory for state tracking, preferring /cache if on a tmpfs mount.
my $state_directory;
if (open(my $mount_fh, '<', '/proc/mounts')) {
    while (my $mount_line = <$mount_fh>) {
        if ($mount_line =~ /^\S+\s+\/cache\s+tmpfs\s+/) {
            $state_directory = "/cache" if -w "/cache";
            last;
        }
    }
    close($mount_fh);
}
$state_directory ||= ($ENV{TMPDIR} && -d $ENV{TMPDIR} && -w _) ? $ENV{TMPDIR} : ".";

my $state_file = "$state_directory/.${me}_state_${patch_hash}";
my $temp_suffix = substr($patch_hash, 0, 11);

# --- 5. Patch Parsing ---
# Scans the patch file to build a map of files to be modified and their hunks.
open(my $patch_fh, '<', $patch_file) or die "$me: Cannot open patch: $!\n";
binmode($patch_fh);
read($patch_fh, my $buffer, 2);
close($patch_fh);
if (defined $buffer && $buffer eq "\x1f\x8b") {
    open($patch_fh, "-|", "/usr/bin/gzip", "-dc", "--", $patch_file) or die "$me: Cannot open patch using zcat: $!";
} else {
    open($patch_fh, '<', $patch_file) or die "$me: Cannot open patch: $!\n";
}
my %patches;
my $current_file;
my $is_git_format = 0;

while (my $line = <$patch_fh>) {
    # Detects git-style diff headers to properly handle additions/deletions.
    if ($line =~ /^diff --git\s+a\/.+?\s+b\/.+$/) {
        undef $current_file; # Reset context for high-integrity parsing
        $is_git_format = 1; next;
    }
    elsif ($is_git_format && $line =~ /^deleted file mode/) {
        $patches{$current_file}{deleted} = 1 if $current_file; next;
    }
    # Parse source ('---') and destination ('+++') file paths.
    elsif ($line =~ /^--- (?:a\/)?(.+)$/) {
        my $path = $1; $path =~ s/(?:\t.*|\s+)$//;
        $current_file = $path unless $path eq '/dev/null';
    }
    elsif ($line =~ /^\+\+\+ (?:b\/)?(.+)$/) {
        my $path = $1; $path =~ s/(?:\t.*|\s+)$//;
        if ($path eq '/dev/null') { $patches{$current_file}{deleted} = 1; }
        else { $current_file = $path; $patches{$current_file}{deleted} = 0; }
    }
    # Capture hunk headers: @@ -old_start,len +new_start,len @@
    # Handle hunk header with optional counts (default to 1)
    elsif ($current_file && $line =~ /^@@ \-(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@/) {
        push @{$patches{$current_file}{hunks}}, {
            old_start      => $1,
            old_count      => $2 // 1, # Default to 1 if count is missing
            new_start      => $3,
            new_count      => $4 // 1, # Default to 1 if count is missing
            lines          => [],
            no_eof_newline => 0
        };
    }
    # Accumulate hunk content (context lines, additions, or deletions).
    elsif ($current_file && @{$patches{$current_file}{hunks}}) {
        if ($line =~ /^\\ No newline at end of file/) {
            $patches{$current_file}{hunks}[-1]{no_eof_newline} = 1;
        }
        else {
            push @{$patches{$current_file}{hunks}[-1]{lines}}, $line if $line =~ /^[ \+\-]/;

        }
    }
}
close($patch_fh);

# --- 6. Clean and Revert ---
# Logic for cleaning up or rolling back previously applied patches using the state file.
my %state_metadata;
if (-e $state_file) {
    open(my $sf_fh, '<', $state_file); <$sf_fh>; # Skip header
    while (<$sf_fh>) {
        chomp;
        my ($filename, $mtime, $size, $offsets, $status, $source_hash) = split(/\|/);
        $state_metadata{$filename} = { status => $status, hash => $source_hash };
    }
    close($sf_fh);
}

if ($clean || $revert) {
    print(($clean ? "Cleaning backups...\n" : "Reverting to original state...\n"));
    my $errors = 0;
    foreach my $target (keys %patches) {
        my $backup = "$target.orig";
        if ($clean && -e $backup) {
            unlink($backup) or (warn("$me: Skip delete $backup: $!\n"), $errors++);
        }
        elsif ($revert && -e $backup) {
            # If the file was created by the patch, remove it entirely.
            if ($state_metadata{$target} && $state_metadata{$target}{status} eq "NEW") {
                # If the patch created it, delete it
                (unlink($target) or $errors++) if -e $target;
                unlink($backup) or $errors++;
                print "  Removed created file: $target\n";
            } else {
                # Restore existing files from their .orig backup.
                # Attempt restoration of all files regardless of individual failures
                rename($backup, $target) or (warn("$me: Failed to restore $target: $!\n"), $errors++);
                print "  Restored: $target\n";
            }
        }
    }

    unlink($state_file) if -e $state_file && $errors == 0;

    # Exit with non-zero status if any part of the operation failed
    exit($errors > 0 ? 1 : 0);
}

# --- 7. Hunk Matching Engine ---
# Finds the correct line index in a file to apply a hunk, accounting for line drifts.
sub find_hunk_index {
    my ($file_content, $hunk_lines, $start_pos) = @_;
    # Only use ' ' (context) and '-' (to-be-removed) lines for matching.
    my @match_search = grep { /^[ -]/ } @$hunk_lines;

    # Try exact match first.
    return $start_pos if verify_context($file_content, \@match_search, $start_pos);

    # Search within the 'fuzz' range for a shifted match.
    for (my $offset = 1; $offset <= $fuzz_range; $offset++) {
        return ($start_pos - $offset) if verify_context($file_content, \@match_search, $start_pos - $offset);
        return ($start_pos + $offset) if verify_context($file_content, \@match_search, $start_pos + $offset);
    }
    return undef; # Hunk does not apply (context mismatch).
}

# Helper to verify if the hunk's context matches the actual file content at a given index.
sub verify_context {
    my ($lines, $search, $idx) = @_;
    my $search_size = scalar @$search;
    return 0 if $idx < 0 || ($idx + $search_size) > scalar @$lines;
    for (my $i = 0; $i < $search_size; $i++) {
        my $f_text = $lines->[$idx + $i]; $f_text =~ s/[\r]?$//;
        my $h_text = substr($search->[$i], 1); $h_text =~ s/[\r]?$//;
        return 0 if $f_text ne $h_text;
    }
    return 1;
}

# --- 8. Dry Run ---
# Pre-validation phase: Checks if all hunks can be matched and records offsets.
if ($dry_run) {
    open(my $sf_out, '>', $state_file) or die "$me: Cannot create state file: $!\n";
    print $sf_out "CKSUM:$patch_hash\n";
    foreach my $f (sort keys %patches) {
        if ($patches{$f}{deleted}) { print "DELETE: $f\n"; next; }
        if (-f $f) {
            my @stats = stat($f);
            my $file_hash = get_file_fingerprint($f);
            open(my $fh, '<', $f); my @content = <$fh>; close($fh);
            my (@offsets, $failed) = ((), 0);
            foreach my $h (@{$patches{$f}{hunks}}) {
                my $idx = find_hunk_index(\@content, $h->{lines}, $h->{old_start} - 1);
                if (defined $idx) {
                    push @offsets, ($idx - ($h->{old_start} - 1));
                } else { $failed = 1; }
            }
            # Save metadata to ensure the file hasn't changed between dry-run and apply.
            print $sf_out "$f|$stats[$ST_MTIME]|$stats[$ST_SIZE]|" . join(",", @offsets) . "|EXISTING|$file_hash\n" unless $failed;
            print(($failed ? "FAIL:   " : "READY:  ") . "$f\n");
        } elsif (!-e $f) {
            print $sf_out "$f|0|0||NEW|\n"; print "CREATE: $f\n";
        }
    }
    close($sf_out); exit 0;
}

# --- 9. Execution ---
# Load offsets/hashes generated during the Dry Run to ensure consistent application.
my %stabilized_data;
if (-e $state_file) {
    open(my $sf_in, '<', $state_file); <$sf_in>;
    while (<$sf_in>) {
        chomp; my ($f, $m, $s, $o, $st, $shash) = split(/\|/);
        @{$stabilized_data{$f}} = (split(",", $o), $st, $shash);
    }
    close($sf_in);
}

my @processed_files;
my @deferred_unlinks;

# Use eval to handle errors gracefully and trigger a rollback if any file fails.
eval {
    foreach my $target (keys %patches) {
        my $temp_work_file = "${target}.tmp_${temp_suffix}";
        unlink($temp_work_file) if -e $temp_work_file;
        my $backup_file = "$target.orig";
        my $expected_hash = defined $stabilized_data{$target} ? $stabilized_data{$target}[-1] : "";

        # Step A: Safe Backup Sequence
        # Creates a backup before any modification. rename() is used to ensure atomicity.
        if (-e $target && !-e $backup_file) {
            my $current_disk_hash = get_file_fingerprint($target);
            die "State Conflict: $target drift detected!\n" if $expected_hash ne $current_disk_hash;

            native_copy($target, $temp_work_file);
            rename($target, $backup_file) or die "Renaming backup failed: $target\n";
            rename($temp_work_file, $target) or die "Activating working copy failed: $target\n";

            # Validate that the file hasn't been corrupted during the copy/move process.
            my $work_hash = get_file_fingerprint($target);
            die "Integrity Check Failed: $target corruption!\n" if $expected_hash ne $work_hash;

            push @processed_files, $target;
            push @deferred_unlinks, $target if $patches{$target}{deleted};
        }
        elsif (!-e $target && !-e $backup_file) {
            # For new files, create a marker backup so rollback knows to delete them.
            open(my $marker_fh, '>', $backup_file); close($marker_fh);
            push @processed_files, $target;
        }

        next if $patches{$target}{deleted};

        # Step B: Application Logic
        # Builds the directory structure if it doesn't exist.
        my $target_dir = dirname($target);
        if (!-d $target_dir) {
            my $path_acc = "";
            foreach my $seg (split(/\//, $target_dir)) {
                next if $seg eq ""; $path_acc .= "/$seg";
                mkdir($path_acc, 0755) if !-d $path_acc;
            }
        }

        my @file_lines = (-e $target) ? do { open(my $fh, '<', $target); <$fh> } : ();
        my @hunks   = @{$patches{$target}{hunks} // []};
        # Accessing metadata status/hash relative to the end of the stored list
        my @offsets = defined $stabilized_data{$target} ? @{$stabilized_data{$target}}[0..$#{$stabilized_data{$target}}-2] : ();
        my $suppress_final_newline = 0;

        # Apply hunks in reverse order to keep line indices stable for earlier hunks.
        for (my $i = $#hunks; $i >= 0; $i--) {
            my $h = $hunks[$i];
            my $zi_ln = $h->{old_start} - 1;
            my $match_idx = (@file_lines) ? (defined $offsets[$i] ? ($zi_ln+$offsets[$i]) : find_hunk_index(\@file_lines, $h->{lines}, $zi_ln)) : 0;
            die "Match failed during apply: $target\n" unless defined $match_idx;

            $suppress_final_newline = 1 if $i == $#hunks && $h->{no_eof_newline};

            my ($removed_count, @transformed) = (0, ());
            foreach my $line (@{$h->{lines}}) {
                my $ind  = substr($line, 0, 1);
                my $text = (length($line) > 1) ? substr($line, 1) : "";
                $text =~ s/\r?[\n]+$//;
                $text = ($text . "\n");
                # '-' lines are not added to the list
                # '+' lines do not increment the removal count
                if ('-' eq $ind || ' ' eq $ind) {
                    $removed_count++;
                    push @transformed, $text if ' ' eq $ind;
                }
                elsif ('+' eq $ind) { push @transformed, $text; }
            }
            # Use splice to replace the matched block with the new transformed lines.
            splice(@file_lines, $match_idx, $removed_count, @transformed);
        }

        # Step C: Final Atomic Commit
        # Writes the fully patched result to a temp file, then swaps it with the target.
        open(my $out_fh, '>', $temp_work_file) or die "Write temp failed: $target\n";
        for (my $i = 0; $i <= $#file_lines; $i++) {
            my $l = $file_lines[$i]; $l =~ s/\r?[\n]+$//;
            print $out_fh ($i == $#file_lines && $suppress_final_newline) ? $l : $l . "\n";
        }
        close($out_fh);
        rename($temp_work_file, $target) or die "Commit failed: $target\n";
    }

    # Clean up files marked for deletion after successful application.
    foreach my $f_to_del (@deferred_unlinks) {
        unlink($f_to_del) or warn "$me: Unlink failed: $f_to_del: $!\n";
    }
};

# Rollback Logic: Restores files to their state before the script began if an error occurred.
if ($@) {
    warn "$me: Application Error: $@. Rolling back changes...\n";
    foreach my $f (@processed_files) {
        my $orig = "$f.orig";
        if (-e $orig) {
            # Accessing metadata status relative to the end of the stored list
            my $status = defined $stabilized_data{$f} ? $stabilized_data{$f}[-2] : "EXISTING";
            if ($status eq "NEW") { unlink($f) if -e $f; unlink($orig); }
            else { rename($orig, $f); }
        }
    }
    exit 1;
}

unlink($state_file) if -e $state_file;
print "Success.\n";

