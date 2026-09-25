import { spawn } from "node:child_process";
import {
  chmod,
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

const archivePath = Bun.argv.at(-1);

if (!archivePath) {
  console.error("usage: bun run reproduction.ts /path/to/archive.zip");
  process.exit(2);
}

await lstat(archivePath);
console.error("archive:", archivePath);

const child = spawn("unzip", ["-Z1", archivePath], {
  shell: false,
  stdio: ["ignore", "pipe", "pipe"],
});

let stdout = "";
let stderr = "";

child.stdout.setEncoding("utf8");
child.stderr.setEncoding("utf8");

child.stdout.on("data", chunk => {
  stdout += chunk;
});

child.stderr.on("data", chunk => {
  stderr += chunk;
});

child.once("spawn", () => {
  console.error("spawn:", child.pid);
});

child.once("error", error => {
  console.error("error:", error);
});

const timeout_timer = setTimeout(async () => {
  const pid = child.pid;

  console.error("TIMEOUT:", {
    pid: child.pid,
    killed: child.killed,
    exitCode: child.exitCode,
    signalCode: child.signalCode,
    stdoutLength: stdout.length,
    stderrLength: stderr.length,
  });

  console.log("output:", {
    stdout: JSON.stringify(stdout),
    stderr: JSON.stringify(stderr),
  });

  if (pid !== undefined) {
    for (const file of ["status", "stat", "wchan"]) {
      try {
        console.error(`/proc/${pid}/${file}:`);
        console.error(await readFile(`/proc/${pid}/${file}`, "utf8"));
      } catch (error) {
        console.error(`/proc/${pid}/${file}: unavailable`, String(error));
      }
    }

    child.kill("SIGTERM");

    setTimeout(() => {
      if (!child.killed && child.exitCode === null) {
        child.kill("SIGKILL");
      }
    }, 2_000);
  }

  process.exitCode = 124;
}, 15_000);

child.once("exit", (code, signal) => {
  clearTimeout(timeout_timer);
  console.error("exit:", { code, signal });
});

child.once("close", (code, signal) => {
  clearTimeout(timeout_timer);

  console.error("close:", {
    code,
    signal,
    stdoutLength: stdout.length,
    stderrLength: stderr.length,
    stdout: JSON.stringify(stdout),
    stderr: JSON.stringify(stderr),
  });
});


import { createHash } from "node:crypto";
import { createReadStream, createWriteStream } from "node:fs";
import { tmpdir } from "node:os";
import {
  basename,
  dirname,
  join,
  normalize,
  resolve,
} from "node:path";
import { Readable, Transform, Writable } from "node:stream";
import { pipeline } from "node:stream/promises";

const MAX_COMMAND_TIME = 20_000;


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
file_path=

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

read_archive() {
  local _arg
  for _arg in "$@" ; do
    if [[ -f "$_arg" ]]; then
      builtin command time --verbose mv "$_arg" "$_arg".tmp.zip
      builtin command time --verbose cp "$_arg".tmp.zip "$_arg"
      file_path="$_arg"
    fi
  done
} >/dev/null

sync
builtin command sleep 1
read_archive "$@"

trap on_term TERM
trap on_int INT

builtin command time --verbose unzip </dev/null "$@" &
child_pid=$!
builtin wait "$child_pid"
status=$?

trap - TERM INT

builtin command time --verbose cksum -a sha256 "$file_path" 1>&2
builtin command sleep $(( 1 + INSTALL_BUN_ATTEMPT ))
if [[ 0 < $(( 0 + INSTALL_BUN_FORCE_ERROR )) ]]; then
  exit 1
fi
exit "$status"
`;

  return await commandOutput("bash", [
    "--noprofile",
    "--norc",
    "-c",
    "--",
    bashUnzipSupervisor,
    "unzip",
    ...args,
  ]);
}

console.log(await unzipOutput(["-Z1", archivePath]));
