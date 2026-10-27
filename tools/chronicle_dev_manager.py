from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import URLError
from urllib.request import Request, urlopen

ROOT_DIR = Path(__file__).resolve().parents[1]


class Session:
    def __init__(self, manifest_path: Path, token: str, api_port: int, ui_port: int, data_dir: Path):
        self.manifest_path = manifest_path
        self.token = token
        self.api_port = api_port
        self.ui_port = ui_port
        self.data_dir = data_dir
        self.api_url = f"http://127.0.0.1:{api_port}"
        self.ui_url = f"http://127.0.0.1:{ui_port}"
        self.logs = {
            "api": manifest_path.parent / "api.log",
            "ui": manifest_path.parent / "ui.log",
        }
        self.processes: list[tuple[str, subprocess.Popen, object]] = []
        self.shutdown_requested = threading.Event()
        self.status = "starting"
        self.failure: dict | None = None
        self.control_server: ThreadingHTTPServer | None = None

    def manifest(self) -> dict:
        return {
            "schemaVersion": 1,
            "runId": self.manifest_path.parent.name,
            "status": self.status,
            "managerPid": os.getpid(),
            "managerPort": self.control_server.server_address[1] if self.control_server else None,
            "token": self.token,
            "apiUrl": self.api_url,
            "uiUrl": self.ui_url,
            "apiPort": self.api_port,
            "uiPort": self.ui_port,
            "dataDir": str(self.data_dir),
            "logs": {key: str(value) for key, value in self.logs.items()},
            "failure": self.failure,
        }

    def save(self) -> None:
        temporary = self.manifest_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.manifest(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, self.manifest_path)

    def start_process(self, name: str, command: list[str], environment: dict[str, str]) -> None:
        log_handle = self.logs[name].open("ab")
        options = {
            "cwd": ROOT_DIR,
            "env": environment,
            "stdin": subprocess.DEVNULL,
            "stdout": log_handle,
            "stderr": subprocess.STDOUT,
        }
        if os.name == "nt":
            options["creationflags"] = (
                getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                | getattr(subprocess, "CREATE_NO_WINDOW", 0)
            )
        else:
            options["start_new_session"] = True
        try:
            process = subprocess.Popen(command, **options)
        except Exception:
            log_handle.close()
            raise
        self.processes.append((name, process, log_handle))

    def wait_for_url(self, name: str, url: str, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        process = next(proc for proc_name, proc, _ in self.processes if proc_name == name)
        while time.monotonic() < deadline and not self.shutdown_requested.is_set():
            if process.poll() is not None:
                self.failure = {"code": "dev_process_exited", "service": name, "exitCode": process.returncode}
                return False
            try:
                with urlopen(url, timeout=1) as response:
                    if response.status < 500:
                        return True
            except (URLError, TimeoutError, OSError):
                pass
            time.sleep(0.25)
        if not self.failure:
            self.failure = {"code": "dev_start_timeout", "service": name, "url": url}
        return False

    def stop_processes(self) -> None:
        for _, process, _ in reversed(self.processes):
            if process.poll() is None:
                process.terminate()
        for _, process, _ in reversed(self.processes):
            if process.poll() is None:
                try:
                    process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
        for _, _, handle in self.processes:
            handle.close()

    def run(self) -> int:
        if self.data_dir.exists():
            self.status = "failed"
            self.failure = {"code": "data_directory_exists", "nextAction": "Start a new dev session with its generated data directory."}
            self.save()
            return 1

        handler = self.make_handler()
        self.control_server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.control_server.session = self
        server_thread = threading.Thread(target=self.control_server.serve_forever, daemon=True)
        server_thread.start()
        self.save()

        vite = ROOT_DIR / "node_modules" / "vite" / "bin" / "vite.js"
        node = shutil.which("node")
        if not vite.is_file() or not node:
            self.status = "failed"
            self.failure = {"code": "dev_runtime_unavailable", "nextAction": "Install the project dependencies and ensure Node.js is available."}
            self.save()
            self.control_server.shutdown()
            return 1

        environment = os.environ.copy()
        environment["CHRONICLE_DATA_DIR"] = str(self.data_dir)
        environment["CHRONICLE_DEV_RUN_ID"] = self.manifest_path.parent.name
        environment["CHRONICLE_API_TARGET"] = self.api_url
        try:
            self.data_dir.parent.mkdir(parents=True, exist_ok=True)
            self.start_process(
                "api",
                [sys.executable, "-m", "uvicorn", "backend.app.main:app", "--host", "127.0.0.1", "--port", str(self.api_port)],
                environment,
            )
            self.start_process(
                "ui",
                [node, str(vite), "--config", "ui/vite.config.js", "--host", "127.0.0.1", "--port", str(self.ui_port), "--strictPort"],
                environment,
            )
            self.save()
            if not self.wait_for_url("api", f"{self.api_url}/api/runtime/identity", 45):
                self.status = "failed"
            elif not self.wait_for_url("ui", self.ui_url, 45):
                self.status = "failed"
            else:
                self.status = "running"
        except Exception as exc:
            self.status = "failed"
            self.failure = {"code": "dev_start_failed", "message": str(exc)}

        self.save()
        while self.status == "running" and not self.shutdown_requested.wait(0.5):
            exited = [(name, process.returncode) for name, process, _ in self.processes if process.poll() is not None]
            if exited:
                name, exit_code = exited[0]
                self.failure = {"code": "dev_process_exited", "service": name, "exitCode": exit_code}
                self.status = "failed"
                self.save()
                break

        if self.status != "running":
            self.stop_processes()
        else:
            self.status = "stopping"
            self.save()
            self.stop_processes()
            self.status = "stopped"
            self.save()
        self.control_server.shutdown()
        self.control_server.server_close()
        return 0 if self.status == "stopped" else 1

    def make_handler(self):
        session = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path != "/status":
                    self.send_error(404)
                    return
                if self.headers.get("X-Chronicle-Token") != session.token:
                    self.send_error(403)
                    return
                body = json.dumps(session.manifest(), ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                if self.path != "/shutdown":
                    self.send_error(404)
                    return
                if self.headers.get("X-Chronicle-Token") != session.token:
                    self.send_error(403)
                    return
                session.shutdown_requested.set()
                self.send_response(202)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, _format, *_args):
                return

        return Handler


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--api-port", type=int, required=True)
    parser.add_argument("--ui-port", type=int, required=True)
    parser.add_argument("--data-dir", required=True)
    args = parser.parse_args()
    session = Session(
        Path(args.manifest),
        args.token,
        args.api_port,
        args.ui_port,
        Path(args.data_dir),
    )
    return session.run()


if __name__ == "__main__":
    raise SystemExit(main())
