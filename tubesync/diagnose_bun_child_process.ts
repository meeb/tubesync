import { spawn, type ChildProcess } from "node:child_process";
import { createHash, randomUUID } from "node:crypto";
import {
  mkdir,
  readFile,
  rm,
  stat,
  writeFile,
} from "node:fs/promises";
import { join } from "node:path";

type EventRecord = {
  time: string;
  test: string;
  event: string;
  details?: Record<string, unknown>;
};

type TestResult = {
  name: string;
  args: string[];
  stdio: string;
  pid?: number;
  exitCode?: number | null;
  exitSignal?: NodeJS.Signals | null;
  closeCode?: number | null;
  closeSignal?: NodeJS.Signals | null;
  timedOut: boolean;
  durationMs: number;
  stdoutBytes: number;
  stderrBytes: number;
  stdoutPreview: string;
  stderrPreview: string;
  events: string[];
  procSamples: Array<Record<string, unknown>>;
  error?: string;
};

const DEFAULT_URL =
  "https://github.com/oven-sh/bun/releases/download/" +
  "bun-v1.3.14/bun-linux-aarch64.zip";

const DEFAULT_SHA256 =
  "a27ffb63a8310375836e0d6f668ae17fa8d8d18b88c37c821c65331973a19a3b";

const events: EventRecord[] = [];
const results: TestResult[] = [];

function timestamp(): string {
  return new Date().toISOString();
}

function record(
  test: string,
  event: string,
  details?: Record<string, unknown>,
): void {
  const item: EventRecord = {
    time: timestamp(),
    test,
    event,
    details,
  };

  events.push(item);

  console.log(
    `[${item.time}] ${test}: ${event}` +
      (details ? ` ${JSON.stringify(details)}` : ""),
  );
}

function argValue(name: string): string | undefined {
  const index = process.argv.indexOf(name);
  if (index < 0) return undefined;
  return process.argv[index + 1];
}

function hasArg(name: string): boolean {
  return process.argv.includes(name);
}

async function sha256(bytes: Uint8Array): Promise<string> {
  return createHash("sha256").update(bytes).digest("hex");
}

function preview(value: Buffer | string, max = 4096): string {
  const text = Buffer.isBuffer(value) ? value.toString("utf8") : value;
  return text.length <= max ? text : `${text.slice(0, max)}…`;
}

async function readProc(
  pid: number,
): Promise<Record<string, unknown> | undefined> {
  try {
    const [statText, statusText, wchanText, ioText] = await Promise.all([
      readFile(`/proc/${pid}/stat`, "utf8").catch(() => ""),
      readFile(`/proc/${pid}/status`, "utf8").catch(() => ""),
      readFile(`/proc/${pid}/wchan`, "utf8").catch(() => ""),
      readFile(`/proc/${pid}/io`, "utf8").catch(() => ""),
    ]);

    if (!statText && !statusText && !wchanText && !ioText) {
      return undefined;
    }

    const statFields = statText.trim().split(/\s+/);

    const values: Record<string, unknown> = {
      pid,
      state: statFields[2] ?? "",
      ppid: statFields[3] ?? "",
      utimeTicks: statFields[13] ?? "",
      stimeTicks: statFields[14] ?? "",
      wchan: wchanText.trim(),
    };

    for (const line of statusText.split("\n")) {
      const match = line.match(/^(State|VmRSS|voluntary_ctxt_switches|nonvoluntary_ctxt_switches):\s*(.*)$/);
      if (match) values[match[1]] = match[2];
    }

    for (const line of ioText.split("\n")) {
      const match = line.match(/^([^:]+):\s*(.*)$/);
      if (match) values[`io_${match[1]}`] = match[2];
    }

    return values;
  } catch (error) {
    return { pid, readError: String(error) };
  }
}

function wait(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function streamText(
  stream: NodeJS.ReadableStream | null,
  onData: (data: Buffer) => void,
  onEnd: (event: string) => void,
  eventName: string,
): void {
  if (!stream) {
    onEnd(`${eventName}-absent`);
    return;
  }

  stream.on("data", (data: Buffer | string) => {
    onData(Buffer.isBuffer(data) ? data : Buffer.from(data));
  });

  stream.on("end", () => onEnd(`${eventName}-end`));
  stream.on("close", () => onEnd(`${eventName}-close`));
  stream.on("error", (error) => {
    onEnd(`${eventName}-error:${String(error)}`);
  });
}

async function runSpawnTest(
  name: string,
  args: string[],
  stdioMode: "pipe" | "ignore",
  timeoutMs = 90_000,
): Promise<TestResult> {
  const result: TestResult = {
    name,
    args,
    stdio: stdioMode,
    timedOut: false,
    durationMs: 0,
    stdoutBytes: 0,
    stderrBytes: 0,
    stdoutPreview: "",
    stderrPreview: "",
    events: [],
    procSamples: [],
  };

  const started = performance.now();

  const event = (
    name: string,
    details?: Record<string, unknown>,
  ): void => {
    result.events.push(name);
    record(result.name, name, details);
  };

  let child: ChildProcess;

  try {
    child = spawn("unzip", args, {
      stdio: stdioMode === "pipe"
        ? ["ignore", "pipe", "pipe"]
        : ["ignore", "ignore", "ignore"],
      shell: false,
    });
  } catch (error) {
    result.error = `spawn threw synchronously: ${String(error)}`;
    result.durationMs = Math.round(performance.now() - started);
    results.push(result);
    record(result.name, "spawn-throw", { error: result.error });
    return result;
  }

  result.pid = child.pid;

  event("spawn-returned", {
    pid: child.pid,
    args,
    stdio: stdioMode,
  });

  let stdout = Buffer.alloc(0);
  let stderr = Buffer.alloc(0);

  const appendOutput = (
    target: "stdout" | "stderr",
    data: Buffer,
  ): void => {
    if (target === "stdout") {
      result.stdoutBytes += data.length;
      if (stdout.length < 8192) {
        stdout = Buffer.concat([stdout, data]).subarray(0, 8192);
      }
    } else {
      result.stderrBytes += data.length;
      if (stderr.length < 8192) {
        stderr = Buffer.concat([stderr, data]).subarray(0, 8192);
      }
    }
  };

  streamText(
    child.stdout,
    (data) => appendOutput("stdout", data),
    (name) => event(name),
    "stdout",
  );

  streamText(
    child.stderr,
    (data) => appendOutput("stderr", data),
    (name) => event(name),
    "stderr",
  );

  child.on("spawn", () => event("spawn-event"));

  child.on("error", (error) => {
    result.error = String(error);
    event("error", { error: String(error) });
  });

  child.on("exit", (code, signal) => {
    result.exitCode = code;
    result.exitSignal = signal;
    event("exit", { code, signal });
  });

  child.on("close", (code, signal) => {
    result.closeCode = code;
    result.closeSignal = signal;
    event("close", { code, signal });
  });

  let finished = false;

  const monitor = (async () => {
    while (!finished && child.pid) {
      const sample = await readProc(child.pid);

      if (sample) {
        result.procSamples.push(sample);

        if (result.procSamples.length % 4 === 0) {
          event("proc-sample", sample);
        }
      }

      await wait(250);
    }
  })();

  const timeout = setTimeout(() => {
    result.timedOut = true;
    event("timeout", { timeoutMs });

    try {
      child.kill("SIGTERM");
      event("sigterm-sent");
    } catch (error) {
      event("sigterm-failed", { error: String(error) });
    }

    setTimeout(() => {
      if (!finished) {
        try {
          child.kill("SIGKILL");
          event("sigkill-sent");
        } catch (error) {
          event("sigkill-failed", { error: String(error) });
        }
      }
    }, 5_000).unref();
  }, timeoutMs);

  await new Promise<void>((resolve) => {
    child.once("close", () => resolve());

    child.once("error", () => {
      // An error may occur without close on some implementations.
      setTimeout(resolve, 1_000).unref();
    });
  });

  finished = true;
  clearTimeout(timeout);
  await monitor;

  result.stdoutPreview = preview(stdout);
  result.stderrPreview = preview(stderr);
  result.durationMs = Math.round(performance.now() - started);

  event("test-finished", {
    durationMs: result.durationMs,
    exitCode: result.exitCode,
    closeCode: result.closeCode,
    timedOut: result.timedOut,
    stdoutBytes: result.stdoutBytes,
    stderrBytes: result.stderrBytes,
  });

  results.push(result);
  return result;
}

async function downloadVerifiedArchive(
  url: string,
  expectedSha256: string,
  path: string,
): Promise<Uint8Array> {
  record("download", "start", { url });

  const response = await fetch(url);

  if (!response.ok) {
    throw new Error(`Download failed: HTTP ${response.status}`);
  }

  const bytes = new Uint8Array(await response.arrayBuffer());
  const actualSha256 = await sha256(bytes);

  record("download", "completed", {
    bytes: bytes.byteLength,
    actualSha256,
    expectedSha256,
  });

  if (actualSha256.toLowerCase() !== expectedSha256.toLowerCase()) {
    throw new Error(
      `SHA-256 mismatch: expected ${expectedSha256}, got ${actualSha256}`,
    );
  }

  await writeFile(path, bytes);

  record("download", "checksum-verified", {
    path,
    sha256: actualSha256,
  });

  return bytes;
}

async function printAnalysis(
  archive: string,
  url: string,
  expectedSha256: string,
): Promise<void> {
  console.log("\n================ ANALYSIS ================\n");

  console.log(`Archive URL: ${url}`);
  console.log(`Expected SHA-256: ${expectedSha256}`);
  console.log(`Temporary archive: ${archive}`);
  console.log(`Tests completed: ${results.length}\n`);

  for (const result of results) {
    console.log(`--- ${result.name} ---`);
    console.log(`stdio: ${result.stdio}`);
    console.log(`args: unzip ${result.args.join(" ")}`);
    console.log(`pid: ${result.pid ?? "unknown"}`);
    console.log(`duration: ${result.durationMs} ms`);
    console.log(`timed out: ${result.timedOut}`);
    console.log(`exit: code=${result.exitCode} signal=${result.exitSignal}`);
    console.log(`close: code=${result.closeCode} signal=${result.closeSignal}`);
    console.log(`stdout bytes: ${result.stdoutBytes}`);
    console.log(`stderr bytes: ${result.stderrBytes}`);
    console.log(`events: ${result.events.join(" -> ")}`);

    if (result.error) {
      console.log(`error: ${result.error}`);
    }

    if (result.stdoutPreview) {
      console.log(`stdout preview:\n${result.stdoutPreview}`);
    }

    if (result.stderrPreview) {
      console.log(`stderr preview:\n${result.stderrPreview}`);
    }

    const dStateSamples = result.procSamples.filter((sample) =>
      String(sample.state ?? "").includes("D")
    );

    if (dStateSamples.length > 0) {
      console.log(
        `D-state samples: ${dStateSamples.length}; ` +
          `example=${JSON.stringify(dStateSamples[0])}`,
      );
    }

    console.log("");
  }

  const timedOut = results.filter((result) => result.timedOut);
  const closeMissing = results.filter((result) =>
    result.closeCode === undefined &&
    result.closeSignal === undefined
  );
  const exitedWithoutClose = results.filter((result) =>
    result.exitCode !== undefined &&
    result.closeCode === undefined &&
    result.closeSignal === undefined
  );
  const dState = results.filter((result) =>
    result.procSamples.some((sample) =>
      String(sample.state ?? "").includes("D")
    )
  );

  console.log("=============== CONCLUSION ===============\n");

  if (timedOut.length === 0) {
    console.log(
      "All node:child_process.spawn tests completed within the timeout.",
    );
    console.log(
      "This reproduction did not trigger the intermittent failure.",
    );
  } else {
    console.log(
      `${timedOut.length} node:child_process.spawn test(s) timed out.`,
    );

    if (dState.length > 0) {
      console.log(
        "At least one unzip process entered D state. " +
          "That indicates kernel-level I/O waiting.",
      );
    }

    if (exitedWithoutClose.length > 0) {
      console.log(
        "At least one child emitted exit without close. " +
          "This implicates child-process lifecycle or stdio handling.",
      );
    }

    if (closeMissing.length > 0 && dState.length === 0) {
      console.log(
        "At least one child failed to produce close without observed D state. " +
          "This is consistent with a node:child_process compatibility or " +
          "verifier wait-path problem.",
      );
    }
  }

  console.log("\nAll captured events:");
  for (const item of events) {
    console.log(JSON.stringify(item));
  }
}

async function main(): Promise<number> {
  const url = argValue("--url") ??
    process.env.BUN_ARCHIVE_URL ??
    DEFAULT_URL;

  const expectedSha256 = (
    argValue("--sha256") ??
    process.env.BUN_ARCHIVE_SHA256 ??
    DEFAULT_SHA256
  ).toLowerCase();

  const timeoutMs = Number(
    argValue("--timeout-ms") ??
      process.env.BUN_DIAGNOSTIC_TIMEOUT_MS ??
      "90000",
  );

  const tempRoot = process.env.RUNNER_TEMP ?? "/tmp";
  const workDir = join(tempRoot, `bun-child-process-${randomUUID()}`);
  const archive = join(workDir, "bun-linux-aarch64.zip");
  const extractPipe = join(workDir, "extract-pipe");
  const extractIgnore = join(workDir, "extract-ignore");

  await mkdir(extractPipe, { recursive: true });
  await mkdir(extractIgnore, { recursive: true });

  console.log("========== Bun child_process diagnostic ==========");
  console.log(`runtime: ${process.execPath}`);
  console.log(`runtime version: ${process.version}`);
  console.log(`pid: ${process.pid}`);
  console.log(`platform: ${process.platform}`);
  console.log(`architecture: ${process.arch}`);
  console.log(`url: ${url}`);
  console.log(`timeout: ${timeoutMs} ms`);
  console.log("");

  try {
    await downloadVerifiedArchive(url, expectedSha256, archive);

    await runSpawnTest(
      "list-piped",
      ["-Z1", archive],
      "pipe",
      timeoutMs,
    );

    await runSpawnTest(
      "list-ignored",
      ["-Z1", archive],
      "ignore",
      timeoutMs,
    );

    await runSpawnTest(
      "test-piped",
      ["-t", archive],
      "pipe",
      timeoutMs,
    );

    await runSpawnTest(
      "extract-piped",
      ["-u", "-o", "-d", extractPipe, archive],
      "pipe",
      timeoutMs,
    );

    await runSpawnTest(
      "extract-ignored",
      ["-u", "-o", "-d", extractIgnore, archive],
      "ignore",
      timeoutMs,
    );

    await printAnalysis(archive, url, expectedSha256);

    const failed = results.some((result) =>
      result.timedOut ||
      result.error ||
      result.exitCode !== 0 ||
      result.closeCode !== 0
    );

    return failed ? 1 : 0;
  } catch (error) {
    console.error("\nDIAGNOSTIC SETUP FAILED:");
    console.error(error instanceof Error ? error.stack : String(error));
    return 2;
  } finally {
    // Cleanup happens only after all output has been produced.
    // No diagnostic conclusion depends on this directory surviving.
    await rm(workDir, { recursive: true, force: true }).catch(() => {});
  }
}

const exitCode = await main();
process.exitCode = exitCode;

