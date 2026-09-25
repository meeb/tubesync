import { spawn } from "node:child_process";
import { stat } from "node:fs/promises";

const archivePath = Bun.argv[Bun.argv.length - 1];

if (!archivePath) {
  console.error("usage: bun run ./reproduction.ts /path/to/bun-linux-aarch64.zip");
  process.exit(2);
}

await stat(archivePath);

console.error("archive:", archivePath);

const child = spawn(
  "unzip",
  ["-Z1", archivePath],
  {
    shell: false,
    stdio: ["ignore", "pipe", "pipe"],
  },
);

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

const timeout_timer = setTimeout(() => {
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
