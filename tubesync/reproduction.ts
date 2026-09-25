import { spawn } from "node:child_process";
import { stat, readFile } from "node:fs/promises";

const archivePath = Bun.argv.at(-1);

if (!archivePath) {
  console.error("usage: bun run reproduction.ts /path/to/archive.zip");
  process.exit(2);
}

await stat(archivePath);
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
