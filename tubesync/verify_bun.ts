import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
// constants unused?
import { constants, createReadStream, createWriteStream } from "node:fs";
import {
  chmod,
  copyFile, // unused?
  lstat,
  mkdir,
  mkdtemp,
  open,
  readFile,
  readdir,
  rename,
  rm,
  unlink,
  writeFile,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import {
  basename,
  dirname,
  isAbsolute, // unused?
  join,
  normalize,
  relative, // unused?
  resolve,
} from "node:path";
import { Readable, Transform, Writable } from "node:stream";
import { pipeline } from "node:stream/promises";

const OWNER = "oven-sh";
const REPOSITORY = "bun";
const GITHUB_API_VERSION = "2026-03-10";
// The rollout date when GitHub began automatically generating asset digest records
const GITHUB_AUTOMATIC_DIGEST_ROLLOUT = new Date("2025-06-05T00:00:00Z");

const KEY_URL = "https://github.com/robobun.gpg";
const TRUSTED_FINGERPRINT = "F3DCC08A8572C0749B3E18888EAB4D40A7B22B59";

const MAX_KEY_BYTES = 1 << 20; // 1 MiB
const MAX_MANIFEST_BYTES = 1 << 25; // 32 MiB
const MAX_ARCHIVE_BYTES = 1 << 30; // 1 GiB

const MAX_COMMAND_TIME = 60_000;

const TRUSTED_KEY = `-----BEGIN PGP PUBLIC KEY BLOCK-----

mDMEY9GQFhYJKwYBBAHaRw8BAQdAkppAqaXl0RkROz6NfdvlwYd2UuUVfHLk2NNY
IzEdnT+0GVJvYm9idW4gPHJvYm9idW5Ab3Zlbi5zaD6IkwQTFgoAOxYhBPPcwIqF
csB0mz4YiI6rTUCnsitZBQJj0ZAWAhsDBQsJCAcCAiICBhUKCQgLAgQWAgMBAh4H
AheAAAoJEI6rTUCnsitZ96UBAMvwCLD6Ud1RZkpvvnGUU+idHt2hcNmYU2d0XxDI
HQ0rAQCA9VFOtjZefQkfhDzgIgnEEdSFXaMiyY+D+LP8awNMCrg4BGPRkBYSCisG
AQQBl1UBBQEBB0BpfePYSOEx8PihYkNXjlK5YT89CGHjEK5etleaB9i6OwMBCAeI
eAQYFgoAIBYhBPPcwIqFcsB0mz4YiI6rTUCnsitZBQJj0ZAWAhsMAAoJEI6rTUCn
sitZvhAA/j4SQxOCLheRG86A2181WAP4qLS1qxSw+fCf28DgiPfbAQCL0kcel+M9
qbRIlMnwn6TwlQgN9w1qqlSnA9CbKXT9Aw==
=dGV6
-----END PGP PUBLIC KEY BLOCK-----

`;

const USER_AGENT = "bun-verify/1";

const expectedAlgorithmLengths = {
  sha256: 64,
  sha512: 128,
} as const;

type Algorithm = keyof typeof expectedAlgorithmLengths;

type Digest<A extends Algorithm = Algorithm> =
  `${A}:${string}` & {
    readonly __digestBrand: unique symbol;
  };

type Asset = {
  name: string;
  created_at: string;
  updated_at: string;
  browser_download_url: string;
  digest?: string | null;
};

type Release = {
  tag_name: string;
  created_at: string;
  draft: boolean;
  prerelease: boolean;
  assets: Asset[];
};

type DownloadHashes = {
  bytes: number;
  sha256: Digest<"sha256">;
  sha512: Digest<"sha512">;
};

type ManifestRecord = {
  algorithm: Algorithm;
  checksum: string;
  filename: string;
};

function getExpectedAlgorithmLength(algorithm: Algorithm): number {
  return expectedAlgorithmLengths[algorithm];
}

function getErrorMessage(err: unknown): string {
  if (err instanceof Error) return err.message;
  return String(err);
}

function fail(message: string): never {
  throw new Error(message);
}

function createDigest<A extends Algorithm>(
  algorithm: A,
  checksum: string,
): Digest<A> {
  const hexOnly = /^[0-9a-fA-F]+$/i.test(checksum);
  const expectedLength = getExpectedAlgorithmLength(algorithm);

  if (hexOnly && expectedLength === checksum.length) {
    return `${algorithm}:${checksum}` as Digest<A>;
  } else {
    fail(`Invalid ${algorithm} checksum`);
  }
}

function usage(): never {
  console.error(`
Usage:
  bun run verify_bun.ts [options]

Options:
  --release <tag>        Release tag, or latest
  --asset <name>         Exact archive name
  --out <path>           Download archive to this path
  --install-dir <dir>    Extract and install Bun in this directory
  --allow-prerelease     Allow prerelease releases
  --help
`);
  process.exit(2);
}

function parseArgs(args: string[]): {
  release: string;
  asset?: string;
  out?: string;
  installDir?: string;
  allowPrerelease: boolean;
} {
  let release = "latest";
  let asset: string | undefined;
  let out: string | undefined;
  let installDir: string | undefined;
  let allowPrerelease = false;

  const seen = new Set<string>();

  for (let i = 0; i < args.length; i++) {
    const arg = args[i];

    if (arg === "--help" || arg === "-h") usage();

    if (arg === "--allow-prerelease") {
      if (seen.has(arg)) fail(`Duplicate option: ${arg}`);
      seen.add(arg);
      allowPrerelease = true;
      continue;
    }

    if (
      arg.startsWith("--") &&
      arg !== "--release" &&
      arg !== "--asset" &&
      arg !== "--out" &&
      arg !== "--install-dir"
    ) {
      fail(`Unknown argument: ${arg}`);
    }

    if (seen.has(arg)) fail(`Duplicate option: ${arg}`);
    seen.add(arg);
    if (args.length === 1 + i) --i;

    const value = args[++i];

    if (!value || value.startsWith("-")) {
      fail(`Missing value for ${arg}`);
    }

    if (arg === "--out") out = value;
    else if (arg === "--asset") asset = value;
    else if (arg === "--install-dir") installDir = value;
    else release = value;
  }

  if (out && installDir) {
    fail("--out and --install-dir cannot be used together");
  }

  return {
    release,
    asset,
    out,
    installDir,
    allowPrerelease,
  };
}

function defaultAssetName(): string {
  const assets: Record<string, string> = {
    "linux:x64": "bun-linux-x64.zip",
    "linux:arm64": "bun-linux-aarch64.zip",
    "darwin:x64": "bun-darwin-x64.zip",
    "darwin:arm64": "bun-darwin-aarch64.zip",
    "win32:x64": "bun-windows-x64.zip",
    "win32:arm64": "bun-windows-aarch64.zip",
  };

  const result = assets[`${process.platform}:${process.arch}`];
  if (!result) {
    fail(
      "No default Bun archive is known for " +
        `${process.platform}/${process.arch}`,
    );
  }

  return result;
}

function safeFileName(name: string): boolean {
  return (
    name.length > 0 &&
    name.length <= 255 &&
    name !== "." &&
    name !== ".." &&
    !name.includes("\0") &&
    !name.includes("/") &&
    !name.includes("\\")
  );
}

function isGitHubDownloadUrl(value: string): boolean {
  try {
    const url = new URL(value);

    return (
      url.protocol === "https:" &&
      (url.hostname === "github.com" ||
        url.hostname.endsWith(".githubusercontent.com"))
    );
  } catch {
    return false;
  }
}

function isGitHubApiUrl(value: string): boolean {
  try {
    const url = new URL(value);

    return (
      url.protocol === "https:" &&
      url.hostname === "api.github.com"
    );
  } catch {
    return false;
  }
}

function githubApiHeaders(): Record<string, string> {
  const token =
    process.env.GH_TOKEN ??
    process.env.GITHUB_TOKEN;

  return {
    accept: "application/vnd.github+json",
    "user-agent": USER_AGENT,
    "x-github-api-version": GITHUB_API_VERSION,
    ...(token ? { authorization: `Bearer ${token}` } : {}),
  };
}

async function githubJson<T>(url: string): Promise<T> {
  if (!isGitHubApiUrl(url)) {
    fail(`Refusing API request to unexpected host: ${url}`);
  }

  const response = await fetch(url, {
    headers: githubApiHeaders(),
    redirect: "error",
  });

  if (!response.ok) {
    fail(`GitHub API request failed (${response.status}): ${url}`);
  }

  return (await response.json()) as T;
}

// Byte Counting and Limit Enforcement
function createByteCounter(maximumBytes: number) {
  let bytes = 0;

  return new Transform({
    transform(chunk, encoding, callback) {
      bytes += chunk.length;
      if (bytes > maximumBytes) {
        return callback(new Error(`Download exceeds ${maximumBytes} bytes`));
      }
      callback(null, chunk);
    },

    // Attach the final count to the stream object for retrieval later
    flush(callback) {
      this.totalBytes = bytes;
      callback();
    },
  }) as Transform & { totalBytes: number };
}

function createHashUpdatingTransform(hashes: ReturnType<typeof createHash>[]): Transform {
  return new Transform({
    transform(chunk, encoding, callback) {
      for (const hash of hashes) {
        hash.update(chunk);
      }
      callback(null, chunk);
    },
  });
}

function createFileWritingTransform(destination: string): Transform {
  const writer = createWriteStream(destination, {
    flags: "wx",
    mode: 0o600,
  });

  let fileTransform: Transform;

  fileTransform = new Transform({
    transform(chunk, _encoding, callback) {
      // Write to the archive first. Only forward the chunk after the
      // file write has completed.
      writer.write(chunk, (error) => {
        if (error) {
          callback(error);
        } else {
          callback(null, chunk);
        }
      });
    },

    flush(callback) {
      writer.end((error) => {
        callback(error ?? undefined);
      });
    },

    destroy(error, callback) {
      if (error) {
        writer.destroy(error);
      } else {
        writer.destroy();
      }

      callback(error);
    },
  });

  // Errors emitted directly by the underlying WriteStream must reach
  // the pipeline.
  writer.on("error", (error) => {
    fileTransform.destroy(error);
  });

  return fileTransform;
}

function createNullWriter(): Writable {
  return new Writable({
    write(_chunk, _encoding, callback) {
      callback();
    },
  });
}

async function downloadApproachA({
  response,
  hashes,
  destination,
  maximumBytes,
}: {
  response: ReturnType<typeof fetch>;
  hashes: ReturnType<typeof createHash>[];
  destination: string;
  maximumBytes: number;
}): Promise<number> {
  const byteCounter = createByteCounter(maximumBytes);
  const fileWriter = createFileWritingTransform(destination);
  const hashesUpdater = createHashUpdatingTransform(hashes);
  const nullWriter = createNullWriter();

  try {
    await pipeline(
      Readable.fromWeb(
        response.body as ReadableStream<Uint8Array>,
      ),
      byteCounter,
      fileWriter,
      hashesUpdater,
      nullWriter, // writes actually happen in fileWriter
    );
  } catch (err) {
    fail(getErrorMessage(err));
  }

  return byteCounter.totalBytes;
}

async function downloadApproachB({
  response,
  hashes,
  destination,
  maximumBytes,
}: {
  response: ReturnType<typeof fetch>;
  hashes: ReturnType<typeof createHash>[];
  destination: string;
  maximumBytes: number;
}): Promise<number> {
  let bytes = 0;
  const writer = createWriteStream(destination, { flags: "wx", mode: 0o600 });

  try {
    for await (const chunk of response.body as any) {
      bytes += chunk.length;
      if (bytes > maximumBytes) {
        fail(`Download exceeds ${maximumBytes} bytes`);
      }

      const writeBuffer = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
      if (!writer.write(writeBuffer)) {
        await new Promise((resolve) => writer.once("drain", resolve));
      }

      for (const hash of hashes) {
        hash.update(chunk);
      }
    }
  } finally {
    writer.end();
  }

  return bytes;
}

async function download(
  url: string,
  destination: string,
  maximumBytes: number,
): Promise<DownloadHashes> {
  if (url !== KEY_URL && !isGitHubDownloadUrl(url)) {
    fail(`Refusing download from unexpected URL: ${url}`);
  }

  const response = await fetch(url, {
    redirect: "follow",
    headers: {
      "user-agent": USER_AGENT,
    },
  });

  if (!response.ok || !response.body) {
    fail(`Download failed (${response.status}): ${url}`);
  }

  if (
    response.url !== KEY_URL &&
    !isGitHubDownloadUrl(response.url)
  ) {
    fail(`Refusing redirected download URL: ${response.url}`);
  }

  const sha256 = createHash("sha256");
  const sha512 = createHash("sha512");
  const hashes = [sha256, sha512];

  const bytes = await downloadApproachA({
    response,
    hashes,
    destination,
    maximumBytes,
  });

  return {
    bytes,
    sha256: createDigest("sha256", sha256.digest("hex")),
    sha512: createDigest("sha512", sha512.digest("hex")),
  };
}

async function writeEmbeddedKey(destination: string): Promise<void> {
  await writeFile(destination, TRUSTED_KEY, {
    encoding: "utf8",
    mode: 0o600,
    flag: "wx",
  });
}

async function appendFile(
  destination: string,
  source: string,
): Promise<void> {
  await pipeline(
    createReadStream(source),
    createWriteStream(destination, { flags: 'a' })
  );
}


async function hashFile(
  source: string,
  algorithm: "sha256" | "sha512",
): Promise<string> {
  const hash = createHash(algorithm);
  const sourceFile = await open(source, "r");

  try {
    for await (const chunk of sourceFile.createReadStream()) {
      hash.update(chunk);
    }
  } finally {
    await sourceFile.close().catch(() => {});
  }

  return hash.digest("hex");
}

async function syncFile(path: string): Promise<void> {
  try {
    const file = await open(path, "r+");

    try {
      await file.sync();
    } finally {
      await file.close();
    }
  } catch {
    // Best effort. Some platforms/filesystems do not support this reliably.
  }
}

async function syncDirectory(path: string): Promise<void> {
  try {
    const directory = await open(path, "r");

    try {
      await directory.sync();
    } finally {
      await directory.close();
    }
  } catch {
    // Best effort, especially for Windows.
  }
}

async function ensureAbsent(path: string): Promise<void> {
  try {
    await lstat(path);
    fail(`Refusing to overwrite existing path: ${path}`);
  } catch (error: any) {
    if (error?.code !== "ENOENT") throw error;
  }
}

async function exclusiveCopy(source: string, destination: string): Promise<void> {
  try {
    const content = await readFile(source);
    await writeFile(destination, content, { flag: "wx", mode: 0o600 });
    await syncFile(destination);
  } catch (error) {
    await unlink(destination).catch(() => {});
    throw error;
  }
}

async function moveOrCopyToStage(source: string, destination: string): Promise<void> {
  try {
    await rename(source, destination);
    return;
  } catch (error: any) {
    if (error?.code !== "EXDEV") throw error;
  }

  await exclusiveCopy(source, destination);
  await syncFile(destination);
}

function isRenameReplacementFailure(error: any): boolean {
  return (
    "win32" === process.platform &&
    ["EEXIST", "EPERM", "ENOTEMPTY", "EBUSY"].includes(error?.code)
  );
}

async function replaceDestination(stagedPath: string, destination: string): Promise<void> {
  try {
    await rename(stagedPath, destination);
    await syncDirectory(dirname(destination));
    return;
  } catch (error: any) {
    if (!isRenameReplacementFailure(error)) {
      throw error;
    }
  }

  const backup = join(
    dirname(destination),
    `.${basename(destination)}.old-${process.pid}-${Date.now()}`,
  );

  await ensureAbsent(backup);
  let oldMoved = false;

  try {
    try {
      await rename(destination, backup);
      oldMoved = true;
    } catch (error: any) {
      if (error?.code !== "ENOENT") throw error;
    }

    await rename(stagedPath, destination);
    await syncDirectory(dirname(destination));

    if (oldMoved) {
      await unlink(backup);
    }
  } catch (error) {
    if (oldMoved) {
      try { await unlink(destination); } catch {}
      try { await rename(backup, destination); } catch {}
    }
    throw error;
  }
}

function apiDigest(
  asset: Asset,
): {
  algorithm: Algorithm;
  checksum: string;
} | undefined {
  // Guard against assets completely missing a digest
  if (!asset.digest) {
    // Strict enforcement: Error if created AFTER automatic generation went live
    const createdAtDate = new Date(asset.created_at);
    if (createdAtDate > GITHUB_AUTOMATIC_DIGEST_ROLLOUT) {
      fail("Digest is required after the feature was introduced.");
    }

    // Gracefully skip verification for older legacy assets
    const updatedAtDate = new Date(asset.updated_at);
    if (updatedAtDate < GITHUB_AUTOMATIC_DIGEST_ROLLOUT) {
      return undefined;
    }

    // Generate a recognition sentinel for this odd case
    return { algorithm: "sha512" as Algorithm, checksum: "F".repeat(128) };
  }

  const match =
    /^([^:]+):([0-9a-fA-F]+)$/.exec(asset.digest);

  if (!match) {
    fail(
      `Unsupported API digest for ${asset.name}: ${asset.digest}`,
    );
  }

  const algorithm = match[1].toLowerCase() as Algorithm;
  const checksum = match[2].toLowerCase();

  if (checksum.length !== getExpectedAlgorithmLength(algorithm)) {
    fail(
      `Invalid ${algorithm} checksum length for ` +
        `${asset.name}: ${asset.digest}`,
    );
  }

  return { algorithm, checksum };
}

function validateApiDigest(asset: Asset, local: DownloadHashes): void {
  const apiResult = apiDigest(asset);
  if (!apiResult) return;

  const expected = createDigest(apiResult.algorithm, apiResult.checksum);
  if (expected !== local[apiResult.algorithm]) {
    fail(
      `${asset.name} failed GitHub API digest validation:\n` +
        `expected: ${expected}\n` +
        `actual:   ${local[apiResult.algorithm]}`,
    );
  }
}

function parseManifest(text: string, expectedFile: string): ManifestRecord[] {
  const records: ManifestRecord[] = [];

  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.replace(/\r$/, "");
    if (line === "" || line.startsWith("#")) continue;

    let algorithm: Algorithm;
    let checksum: string;
    let filename: string;

    const tagged = /^([^ \r\n]+) \(([^)\r\n]+)\) = ([0-9a-fA-F]+)$/.exec(line);

    if (tagged) {
      const label = tagged[1];
      filename = tagged[2];
      checksum = tagged[3].toLowerCase();

      if (checksum.length !== getExpectedAlgorithmLength(label.toLowerCase())) {
        fail(`Algorithm label disagrees with checksum length: ${JSON.stringify(line)}`);
      }

      algorithm = label.toLowerCase();
    } else {
      const untagged = /^([^ ]+) [ *](.*)$/.exec(line);
      if (!untagged) {
        fail(`Malformed checksum line: ${JSON.stringify(line)}`);
      }

      checksum = untagged[1].toLowerCase();
      filename = untagged[2];
    }

    if (filename !== expectedFile) continue;
    if (!safeFileName(filename)) {
      fail(`Unsafe manifest filename: ${filename}`);
    }
    if (!/^[0-9a-f]+$/.test(checksum)) {
      fail(`Malformed checksum line: ${JSON.stringify(line)}`);
    }

    const candidateAlgorithms = Object.entries(
      expectedAlgorithmLengths
    ).filter(
      ([, expectedLength]) => expectedLength === checksum.length
    ).map(
      ([algorithm]) => algorithm
    );

    if (0 === candidateAlgorithms.length) {
      fail(`Unsupported checksum length: ${JSON.stringify(line)}`);
    } else if (!algorithm && 1 < candidateAlgorithms.length) {
      fail(
          `Ambiguous checksum length ${checksum.length}; ` +
          `possible algorithms: ${candidateAlgorithms.join(", ")}`
      );
    } else if (!algorithm) {
      [algorithm] = candidateAlgorithms;
    }

    records.push({
      filename,
      checksum,
      algorithm,
    });
  }

  if (0 === records.length) {
    fail(`No digest for ${expectedFile} was found`);
  }

  return records;
}

function validateManifestDigests(records: ManifestRecord[], local: DownloadHashes): void {
  for (const record of records) {
    const expected = createDigest(record.algorithm, record.checksum);
    if (expected !== local[record.algorithm]) {
      fail(
        `${record.algorithm} checksum mismatch:\n` +
          `expected: ${expected}\n` +
          `actual:   ${local[record.algorithm]}`,
      );
    }
  }
}

async function streamText(stream: NodeJS.ReadableStream | null): Promise<string> {
  let result = "";
  if (!stream) return result;
  for await (const chunk of stream) {
    result += Buffer.isBuffer(chunk) ? chunk.toString("utf8") : String(chunk);
  }
  return result;
}

function processExit(child: ReturnType<typeof spawn>): Promise<number> {
  return new Promise<number>((resolve, reject) => {
    child.once("error", reject);

    child.once("close", (code) => {
      resolve(code ?? -1);
    });
  });
}

async function runChild(
  command: string,
  args: string[],
  options: Parameters<typeof spawn>[2] = {},
) {
  const timeout = Math.max(10_000, Math.min(options.timeout ?? 0, MAX_COMMAND_TIME));
  const signal = AbortSignal.timeout(5_000 + 1_000 + timeout);
  const child = spawn(command, args, {
    ...options,
    shell: false,
    signal: signal,
    stdio: options.stdio ?? ["ignore", "pipe", "pipe"],
    timeout: timeout,
  });

  const timeout_term = setTimeout(() => {
    console.error(`[TIMEOUT] Sending the child (PID=${child.pid}) SIGTERM`);
    child.kill("SIGTERM");
    process.exitCode = 124;
  }, 1_000 + MAX_COMMAND_TIME);

  try {
    const stdoutPromise = streamText(child.stdout);
    const stderrPromise = streamText(child.stderr);
    const exitPromise = processExit(child);

    return await Promise.all([
      stderrPromise,
      stdoutPromise,
      exitPromise,
    ]);
  } catch (error) {
    if (signal.aborted) {
      console.error(
        "A spawned command was aborted: " +
        `PID=${child.pid} CMD=${child.spawnfile} ARGS=${child.spawnargs.join(" ")}`
      );
      child.kill("SIGKILL");
      child.unref();
      process.exitCode = 137;
    }
    throw error;
  } finally {
    clearTimeout(timeout_term);
  }
}

async function commandOutput(command: string, args: string[]): Promise<string> {
  const [stderr, stdout, code] = await runChild(
    command, args, {
    killSignal: "SIGINT",
    timeout: MAX_COMMAND_TIME,
  });

  if (code !== 0) {
    fail(`${command} failed:\n${stderr || stdout}`);
  }

  return stdout;
}

async function findCommand(candidates: string[]): Promise<string | undefined> {
  for (const candidate of candidates) {
    try {
      const [stderr, stdout, code] = await runChild(
        candidate, ["--help"], {
          stdio: ["ignore", "ignore", "ignore"],
      });
      if (code === 0) return candidate;
    } catch {}
  }
  return undefined;
}

async function unzipOutput(args: string[]): Promise<string> {
  // This attempts to sync the filesystems before and after unzip.
  // It also slows itself down to attempt to work around a bun bug.
  const bashUnzipSupervisor = `
child_pid=

sync() { builtin command sync || : ; } 2>/dev/null

forward_signal() {
  local signal="$1"

  if [[ -n "$child_pid" ]]; then
    builtin kill -s "$signal" -- "$child_pid" || :
  fi
} 2>/dev/null

on_term() {
  forward_signal TERM
}

on_int() {
  forward_signal INT
}

sync

trap on_term TERM
trap on_int INT

builtin command unzip "$@" &
child_pid=$!
builtin wait "$child_pid"
status=$?

trap - TERM INT

sync
builtin command sleep 1

exit "$status"
`;

  return await commandOutput("bash", [
    "--noprofile",
    "--norc",
    "-c",
    "--",
    bashUnzipSupervisor,
    "bash",
    ...args,
  ]);
}

async function verifyWithSqv(
  command: string,
  keyPath: string,
  signaturePath: string,
  messagePath: string,
  cleartext: boolean,
): Promise<void> {
  const args = ["--signatures", "1", "--keyring", keyPath];
  if (cleartext) {
    args.push("--output", messagePath, "--message", signaturePath);
  } else {
    args.push("--signature-file", signaturePath, messagePath);
  }

  const [stderr, stdout, code] = await runChild(
    command, args,
  );

  if (code !== 0 || stdout.trimEnd() !== TRUSTED_FINGERPRINT) {
    fail(`sqv rejected the signature:\n${stderr || stdout}`);
  }
}

async function verifyWithSq(
  command: string,
  keyPath: string,
  signaturePath: string,
  messagePath: string,
  cleartext: boolean,
): Promise<void> {
  const args = ["verify", "--no-cert-store", "--signatures", "1", "--keyring", keyPath, "--trust-root", TRUSTED_FINGERPRINT];
  if (cleartext) {
    args.push("--message", "--output", messagePath, signaturePath);
  } else {
    args.push("--signature-file", signaturePath, messagePath);
  }

  const [stderr, stdout, code] = await runChild(
    command, args,
  );

  if (code !== 0) {
    fail(`sq rejected the signature:\n${stderr || stdout}`);
  }
}

async function verifyWithGpg(
  command: string,
  home: string,
  keyPath: string,
  signaturePath: string,
  messagePath: string,
  cleartext: boolean,
): Promise<void> {
  await mkdir(home, { recursive: true, mode: 0o700 });
  const base = ["--batch", "--no-options", "--no-auto-key-retrieve", "--no-auto-key-locate", "--homedir", home];

  const import_stdout = await commandOutput(
    command, [...base, "--import", keyPath]
  );

  const args = cleartext
    ? [...base, "--status-fd", "3", "--output", messagePath, "--decrypt", signaturePath]
    : [...base, "--status-fd", "3", "--verify", signaturePath, messagePath];

  const child = spawn(command, args, {
    shell: false,
    stdio: ["ignore", "pipe", "pipe", "pipe"],
    env: { ...process.env, GNUPGHOME: home },
    timeout: MAX_COMMAND_TIME,
  });

  const stdoutPromise = streamText(child.stdout);
  const stderrPromise = streamText(child.stderr);
  const statusPromise = streamText(child.stdio[3] as any);

  const [stderr, stdout, status, code] = await Promise.all([
    stderrPromise,
    stdoutPromise,
    statusPromise,
    processExit(child),
  ]);

  if (code !== 0) {
    fail(`gpg rejected the signature:\n${stderr || stdout}`);
  }

  let trustedSignature = false;
  for (const line of status.split(/\r?\n/)) {
    if (!line.startsWith("[GNUPG:] VALIDSIG ")) continue;
    const fields = line.split(/\s+/);
    const signingFingerprint = fields[2]?.toUpperCase();
    const primaryFingerprint = fields[11]?.toUpperCase();
    if (signingFingerprint === TRUSTED_FINGERPRINT || primaryFingerprint === TRUSTED_FINGERPRINT) {
      trustedSignature = true;
    }
  }

  if (!trustedSignature) {
    fail(`No valid signature from ${TRUSTED_FINGERPRINT}`);
  }
}

async function verifySignature(
  keyPath: string,
  signaturePath: string,
  messagePath: string,
  cleartext: boolean,
  gpgHome: string,
): Promise<void> {
  const sqv = await findCommand(["sqv"]);
  if (sqv) {
    const sqv_help = await commandOutput("sqv", ["--help"]);
    if (sqv_help.includes("--message")) {
      console.log(`Verifying with: ${sqv}`);
      await verifyWithSqv(sqv, keyPath, signaturePath, messagePath, cleartext);
      return;
    }
  }

  const sq = await findCommand(["sq"]);
  if (sq) {
    const sq_help = await commandOutput("sq", ["help", "verify"]);
    if (sq_help.includes("--message")) {
      console.log(`Verifying with: ${sq}`);
      await verifyWithSq(sq, keyPath, signaturePath, messagePath, cleartext);
      return;
    } else if (cleartext) {
      // Ubuntu LTS uses an older version without --message
      console.log(`Verifying with: ${sq}`);
      await commandOutput("sq", [
        "verify", "--no-cert-store",
        "--keyring", keyPath,
        "--trust-root", TRUSTED_FINGERPRINT,
        "--output", messagePath, signaturePath,
      ]);
      return;
    }
  }

  const gpg = await findCommand(["gpg2", "gpg", "gnupg2", "gnupg", "gpg2.exe", "gpg.exe"]);
  if (!gpg) {
    fail("Neither sq nor a working gpg executable was found");
  }

  console.log(`Verifying with: ${gpg}`);
  await verifyWithGpg(gpg, gpgHome, keyPath, signaturePath, messagePath, cleartext);
}

async function isCleartextSignature(path: string): Promise<boolean> {
  const prefix = (await readFile(path, "utf8")).slice(0, 128);
  return prefix.startsWith("-----BEGIN PGP SIGNED MESSAGE-----");
}

async function verifyAllManifests(
  release: Release,
  work: string,
  keyPath: string,
  archiveName: string,
  archiveHashes: DownloadHashes,
): Promise<void> {
  const signatureAssets = release.assets.filter((asset) => asset.name.toLowerCase().endsWith(".asc"));
  if (signatureAssets.length === 0) {
    fail("No .asc signature or manifest assets were found");
  }

  let covered = false;

  for (const signatureAsset of signatureAssets) {
    if (!safeFileName(signatureAsset.name)) {
      fail(`Unsafe signature asset name: ${signatureAsset.name}`);
    }

    const signaturePath = join(work, signatureAsset.name);
    console.log(`Downloading: ${signatureAsset.browser_download_url}`);
    await download(signatureAsset.browser_download_url, signaturePath, MAX_MANIFEST_BYTES);

    const cleartextPath = join(work, `${signatureAsset.name}.message`);

    if (await isCleartextSignature(signaturePath)) {
      await verifySignature(keyPath, signaturePath, cleartextPath, true, join(work, "gnupg"));
      const records = parseManifest(await readFile(cleartextPath, "utf8"), archiveName);
      validateManifestDigests(records, archiveHashes);
      covered = true;
      continue;
    }

    const messageName = signatureAsset.name.slice(0, -4);
    const messageAsset = release.assets.find((asset) => asset.name === messageName);
    if (!messageAsset) continue;

    if (!safeFileName(messageAsset.name)) {
      fail(`Unsafe manifest asset name: ${messageAsset.name}`);
    }

    const messagePath = join(work, messageAsset.name);
    console.log(`Downloading: ${messageAsset.browser_download_url}`);
    await download(messageAsset.browser_download_url, messagePath, MAX_MANIFEST_BYTES);

    await verifySignature(keyPath, signaturePath, messagePath, false, join(work, "gnupg"));
    const records = parseManifest(await readFile(messagePath, "utf8"), archiveName);
    validateManifestDigests(records, archiveHashes);
    covered = true;
  }

  if (!covered) {
    fail(`No signed checksum manifest covers ${archiveName}`);
  }
}

function safeArchiveEntry(entry: string): boolean {
  if (!entry || entry.includes("\0")) return false;
  const slashNormalized = entry.replaceAll("\\", "/");
  if (slashNormalized.startsWith("/") || /^[A-Za-z]:\//.test(slashNormalized)) return false;
  if (slashNormalized.split("/").some((part) => part === "..")) return false;
  const normalized = normalize(slashNormalized);
  return normalized !== ".." && !normalized.startsWith(`..${process.platform === "win32" ? "\\" : "/"}`);
}

async function extractBinary(archivePath: string, extractionDirectory: string): Promise<string> {
  const unzip = await findCommand(["unzip"]);
  if (!unzip) {
    fail("The unzip executable is required for installation");
  }

  console.log(`Listing files from: ${archivePath}`);
  const listing = await unzipOutput(["-Z1", archivePath]);

  for (const entry of listing.split(/\r?\n/).filter(Boolean)) {
    if (!safeArchiveEntry(entry)) fail(`Archive contains a traversal path: ${entry}`);
  }

  console.log(`Extracting into: ${extractionDirectory}`);
  await unzipOutput(["-q", "-o", "-d", extractionDirectory, archivePath]);

  const candidates: string[] = [];
  async function walk(directory: string): Promise<void> {
    for (const entry of await readdir(directory, { withFileTypes: true })) {
      const path = join(directory, entry.name);
      if (entry.isSymbolicLink()) fail(`Archive extraction produced a symbolic link: ${path}`);
      if (entry.isDirectory()) {
        await walk(path);
      } else if (entry.isFile() && (entry.name === "bun" || entry.name === "bun.exe")) {
        candidates.push(path);
      }
    }
  }

  await walk(extractionDirectory);
  if (1 !== candidates.length) fail(`Expected exactly one extracted Bun executable; found ${candidates.length}`);
  return candidates[0]!;
}

async function installBinary(archivePath: string, installDirectory: string): Promise<string> {
  await mkdir(installDirectory, { recursive: true, mode: 0o755 });
  const extractionDirectory = await mkdtemp(join(dirname(archivePath), "bun-extract-"));

  try {
    const extractedPath = await extractBinary(archivePath, extractionDirectory);
    const extractedInfo = await lstat(extractedPath);
    if (!extractedInfo.isFile()) fail("Extracted Bun executable is not a regular file");
    console.log(`Hashing: ${extractedPath}`);
    const extractedSha512 = await hashFile(extractedPath, "sha512");

    await chmod(extractedPath, 0o755);
    const finalName = process.platform === "win32" ? "bun.exe" : "bun";
    const finalPath = join(installDirectory, finalName);
    const stagingPath = join(installDirectory, `.${finalName}.staged-${process.pid}-${Date.now()}`);

    await ensureAbsent(stagingPath);

    try {
      console.log(`Staging at: ${stagingPath}`);
      await moveOrCopyToStage(extractedPath, stagingPath);
      const stagedSha512 = await hashFile(stagingPath, "sha512");

      if (extractedSha512 !== stagedSha512) fail("Staged executable failed SHA-512 verification");

      await chmod(stagingPath, 0o755);
      await replaceDestination(stagingPath, finalPath);
      return finalPath;
    } catch (error) {
      await unlink(stagingPath).catch(() => {});
      throw error;
    }
  } finally {
    await rm(extractionDirectory, { recursive: true, force: true });
  }
}

async function publishArchive(
  archivePath: string,
  outputPath: string,
  expectedSha512: Digest<"sha512">,
): Promise<string> {
  const archiveFile = basename(archivePath);
  const outputInfo = await lstat(outputPath).catch(
    (err) => err.code === "ENOENT" ? undefined : Promise.reject(err)
  );

  if (outputInfo?.isDirectory()) {
    outputPath = join(outputPath, archiveFile);
  } else {
    await mkdir(dirname(outputPath), { recursive: true });
  }

  const stagePath = join(
    dirname(outputPath),
    `.${archiveFile}.staged-${process.pid}-${Date.now()}`,
  );
  await ensureAbsent(stagePath);

  try {
    await moveOrCopyToStage(archivePath, stagePath);
    const stagedChecksum = await hashFile(stagePath, "sha512");
    const stagedSha512 = createDigest("sha512", stagedChecksum);

    if (expectedSha512 !== stagedSha512) {
      fail(
        `Staged archive failed SHA-512 verification:\n` +
        `expected: ${expectedSha512}\n` +
        `actual: ${stagedSha512}`
      );
    }

    await syncFile(stagePath);
    await replaceDestination(stagePath, outputPath);
    return outputPath;
  } finally {
    await unlink(stagePath).catch(() => {});
  }
}

async function main(): Promise<void> {
  const parsed = parseArgs(process.argv.slice(2));

  const assetName = parsed.asset ?? defaultAssetName();
  if (!safeFileName(assetName)) {
    fail(`Unsafe archive name: ${assetName}`);
  }
  const outputPath = resolve(
    parsed.out ?? join(process.cwd(), assetName),
  );

  const releasesUrl = `https://api.github.com/repos/${OWNER}/${REPOSITORY}/releases`
  const releaseUrl =
    "latest" === parsed.release
      ? `${releasesUrl}/latest`
      : `${releasesUrl}/tags/${encodeURIComponent(parsed.release)}`;

  console.log(`Requesting: ${releaseUrl}`);
  const release = await githubJson<Release>(releaseUrl);
  if (release.draft) fail("Refusing to use a draft release");
  if (release.prerelease && !parsed.allowPrerelease) {
    fail("Release is a prerelease; use --allow-prerelease");
  }

  const archive = release.assets.find(
    (asset) => asset.name === assetName,
  );
  if (!archive) fail(`Archive asset not found: ${assetName}`);
  if (!isGitHubDownloadUrl(archive.browser_download_url)) {
    fail(`Unexpected archive URL: ${archive.browser_download_url}`);
  }

  const work = await mkdtemp(
    join(tmpdir(), "bun-verify-"),
  );
  await chmod(work, 0o700);

  const archivePath = join(work, archive.name);
  const keyPath = join(work, "published-key.asc");
  const downloadedKeyPath = join(work, "downloaded-key.asc");

  try {
    /*
     * The embedded key is always written first. The downloaded key is
     * optional and is appended only as an additional certificate source.
     * The verifier still requires TRUSTED_FINGERPRINT.
     */
    console.log(`Writing embedded public key to: ${keyPath}`);
    await writeEmbeddedKey(keyPath);

    try {
      console.log(`Downloading: ${KEY_URL}`);
      // await download(KEY_URL, downloadedKeyPath, MAX_KEY_BYTES);
      await download(
        KEY_URL,
        downloadedKeyPath,
        MAX_KEY_BYTES,
      );
      await appendFile(keyPath, downloadedKeyPath);
    } catch (error) {
      console.error(
        "Warning: could not download published key; " +
        `using embedded key only: ${getErrorMessage(error)}`,
      );
    }

    console.log(`Downloading: ${archive.browser_download_url}`);
    // const archiveHashes = await download(archive.browser_download_url, archivePath, MAX_ARCHIVE_BYTES);
    const archiveHashes = await download(
      archive.browser_download_url,
      archivePath,
      MAX_ARCHIVE_BYTES,
    );

    console.log("Validating API digest...");
    validateApiDigest(archive, archiveHashes);

    console.log("Verifying manifests...");
    // await verifyAllManifests(release, work, keyPath, archive.name, archiveHashes);
    await verifyAllManifests(
      release,
      work,
      keyPath,
      archive.name,
      archiveHashes,
    );

    const algorithms = Object.keys(
      expectedAlgorithmLengths
    ) as Array<Algorithm>;
    if (parsed.installDir) {
      console.log(`Installing into: ${parsed.installDir}`);
      // const installedPath = await installBinary(archivePath, resolve(parsed.installDir));
      const installedPath = await installBinary(
        archivePath,
        resolve(parsed.installDir),
      );

      console.log(`Calculating hashes for: ${installedPath}`);
      
      /*
      const entries = await Promise.all(
        algorithms.map(async (algo) => [algo, await hashFile(installedPath, algo)] as const)
      );
      */
      const digests = await Promise.all(
        algorithms.map(async (algorithm) => [
          algorithm,
          createDigest(algorithm, await hashFile(installedPath, algorithm)),
        ] as const),
      );
      // const binHashes = Object.fromEntries(entries) as Record<(typeof algorithms)[number], string>;
      const binHashes = Object.fromEntries(digests) as Record<
          (typeof algorithms)[number], string>;

      console.log(`Installed: ${installedPath}`);
      console.group("Binary Digests");
      for (const a of algorithms) console.log(binHashes[a]);
      console.groupEnd();
      console.group("Archive Digests");
      for (const a of algorithms) console.log(archiveHashes[a]);
      console.groupEnd();
    } else {
      // const publishedPath = await publishArchive(archivePath, outputPath, archiveHashes.sha512);
      const publishedPath = await publishArchive(
        archivePath,
        outputPath,
        archiveHashes.sha512,
      );

      console.log(`Verified archive: ${publishedPath}`);
      console.group("Digests");
      for (const a of algorithms) console.log(archiveHashes[a]);
      console.groupEnd();
    }
  } finally {
    await rm(work, { force: true, recursive: true });
  }
}

main().catch((error) => {
  console.error(`bun-verify: ${getErrorMessage(error)}`);
  process.exitCode = 1;
});

