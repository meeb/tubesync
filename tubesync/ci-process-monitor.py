#!/usr/bin/env python3
import json
import os
import signal
import socket
import sqlite3
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

SOCKET_NAME = "\0ci-process-monitor"
POLL_INTERVAL = 0.25
KEEP_SAMPLES = 2400  # 10 minutes at 250 ms

db = sqlite3.connect(":memory:", check_same_thread=False)
db.execute("""
    CREATE TABLE samples (
        id INTEGER PRIMARY KEY,
        ts REAL NOT NULL,
        load1 REAL,
        load5 REAL,
        load15 REAL,
        processes TEXT NOT NULL
    )
""")
db.commit()

db_lock = threading.Lock()
running = True
server = None


def get_processes():
    command = [
        "ps", "-eo",
        "pid=,ppid=,pgid=,stat=,etime=,wchan:32=,"
        "pcpu=,pmem=,rss=,vsz=,args="
    ]

    completed = subprocess.run(
        command,
        text=True,
        capture_output=True,
        check=False,
    )

    interesting = []
    needles = (
        "bun",
        "unzip",
        "verify_bun",
        "gpg",
        "asfald",
    )

    for line in completed.stdout.splitlines():
        lowered = line.lower()
        if any(needle in lowered for needle in needles):
            interesting.append(line.strip())

    return interesting


def collect_sample():
    load1, load5, load15 = os.getloadavg()

    sample = {
        "time": time.time(),
        "loadavg": [load1, load5, load15],
        "processes": get_processes(),
    }

    with db_lock:
        db.execute(
            """
            INSERT INTO samples(ts, load1, load5, load15, processes)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                sample["time"],
                load1,
                load5,
                load15,
                json.dumps(sample["processes"]),
            ),
        )

        db.execute("""
            DELETE FROM samples
            WHERE id NOT IN (
                SELECT id FROM samples ORDER BY id DESC LIMIT ?
            )
        """, (KEEP_SAMPLES,))

        db.commit()

    return sample


def sampler():
    while running:
        try:
            collect_sample()
        except Exception as exc:
            # This goes to the process's stderr only; no filesystem output.
            print(f"monitor sample error: {exc}", flush=True)

        time.sleep(POLL_INTERVAL)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        # Prevent access logging to stderr unless explicitly desired.
        pass

    def send_json(self, value, status=200):
        payload = json.dumps(value).encode()

        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if self.path == "/health":
            self.send_json({"ok": True})
            return

        if self.path == "/latest":
            with db_lock:
                row = db.execute("""
                    SELECT ts, load1, load5, load15, processes
                    FROM samples
                    ORDER BY id DESC
                    LIMIT 1
                """).fetchone()

            if row is None:
                self.send_json({"sample": None})
                return

            ts, load1, load5, load15, processes = row
            self.send_json({
                "sample": {
                    "time": ts,
                    "loadavg": [load1, load5, load15],
                    "processes": json.loads(processes),
                }
            })
            return

        if self.path == "/recent":
            with db_lock:
                rows = db.execute("""
                    SELECT ts, load1, load5, load15, processes
                    FROM samples
                    ORDER BY id DESC
                    LIMIT 200
                """).fetchall()

            self.send_json({
                "samples": [
                    {
                        "time": row[0],
                        "loadavg": row[1:4],
                        "processes": json.loads(row[4]),
                    }
                    for row in reversed(rows)
                ]
            })
            return

        self.send_json({"error": "not found"}, 404)


class AbstractUnixHTTPServer(HTTPServer):
    address_family = socket.AF_UNIX

    def server_bind(self):
        self.socket.bind(SOCKET_NAME)
        self.server_name = "abstract-process-monitor"
        self.server_port = 0


def shutdown(*_args):
    global running
    running = False
    if server is not None:
        server.shutdown()


signal.signal(signal.SIGTERM, shutdown)
signal.signal(signal.SIGINT, shutdown)

threading.Thread(target=sampler, daemon=True).start()

server = AbstractUnixHTTPServer(SOCKET_NAME, Handler)
server.serve_forever()
