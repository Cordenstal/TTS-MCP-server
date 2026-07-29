from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from ..support.runtime_trace import record as _record_trace


ROOT = Path(__file__).resolve().parents[2]
CHILD_MODULE = "tts_mcp.app.server"
SUPERVISOR_HOST = os.getenv("TTS_SUPERVISOR_HOST", "127.0.0.1")
SUPERVISOR_PORT = int(os.getenv("TTS_SUPERVISOR_PORT", "8770"))


def response(handler: BaseHTTPRequestHandler, status: int, payload: Any, content_type: str = "application/json") -> None:
    body = payload if isinstance(payload, bytes) else (
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
        if content_type == "application/json" else str(payload).encode("utf-8")
    )
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


SUPERVISOR_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>TTS MCP Supervisor</title><style>
body{font:16px system-ui,sans-serif;max-width:800px;margin:3rem auto;padding:0 1rem;background:#111827;color:#e5e7eb}section{background:#1f2937;border:1px solid #374151;border-radius:10px;padding:1.2rem;margin:1rem 0}button{padding:.7rem 1rem;margin:.4rem .5rem .4rem 0;border:0;border-radius:6px;color:white;background:#2563eb;cursor:pointer}button.danger{background:#b91c1c}.status{white-space:pre-wrap;background:#111827;padding:1rem;border-radius:6px}.muted{color:#9ca3af}a{color:#93c5fd}
</style></head><body><h1>TTS MCP Supervisor</h1>
<p class="muted">This process remains alive while the MCP/TTS server is stopped.</p>
<section><h2>Server process</h2><div id="status" class="status">Loading...</div><button onclick="act('start')">Start server</button><button onclick="act('restart')">Restart server</button><button class="danger" onclick="act('stop')">Stop all bridge processes</button></section>
<section><p>Backend settings, models, prompts, and conversation logs:</p><a href="http://127.0.0.1:8765/admin">Open AI backend control panel</a></section>
<script>const $=id=>document.getElementById(id);async function refresh(){try{let r=await fetch('/admin/api/status');$('status').textContent=JSON.stringify(await r.json(),null,2)}catch(e){$('status').textContent=e}}async function act(a){if(a==='stop'&&!confirm('Stop the MCP server and its child processes?'))return;try{let r=await fetch('/admin/api/server/'+a,{method:'POST'});$('status').textContent=JSON.stringify(await r.json(),null,2)}catch(e){$('status').textContent=e}setTimeout(refresh,1000)}refresh();setInterval(refresh,3000)</script></body></html>"""


class ProcessSupervisor:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.process: subprocess.Popen[Any] | None = None
        self._stderr_thread: threading.Thread | None = None
        self.log_path = ROOT / "tts_mcp_server.log"

    def _is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def status(self) -> dict[str, Any]:
        with self._lock:
            running = self._is_running()
            return {
                "running": running,
                "pid": self.process.pid if self.process and running else None,
                "server": CHILD_MODULE,
                "http_port": int(os.getenv("TTS_HTTP_PORT", "8765")),
                "log": str(self.log_path),
            }

    def _forward_stderr(self, process: subprocess.Popen[Any]) -> None:
        """Mirror child trace output to this console while retaining a log file."""
        stream = process.stderr
        if stream is None:
            return
        try:
            with self.log_path.open("ab") as log:
                for chunk in iter(stream.readline, b""):
                    if not chunk:
                        break
                    log.write(chunk)
                    log.flush()
                    try:
                        console = getattr(sys.stdout, "buffer", sys.stdout)
                        console.write(chunk)
                        console.flush()
                    except (OSError, TypeError, ValueError):
                        # The console can disappear during shutdown; the file
                        # copy remains available for post-mortem inspection.
                        pass
        finally:
            stream.close()

    def start(self) -> dict[str, Any]:
        with self._lock:
            if self._is_running():
                return self.status()
            _record_trace(
                "process_start_requested",
                component="mcp_server",
                executable=sys.executable,
                command=[sys.executable, "-m", CHILD_MODULE],
            )
            env = os.environ.copy()
            env["TTS_SUPERVISED"] = "1"
            env.setdefault("PYTHONUNBUFFERED", "1")
            log = self.log_path.open("ab")
            flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            self.process = subprocess.Popen(
                [sys.executable, "-m", CHILD_MODULE],
                cwd=str(ROOT),
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.PIPE,
                bufsize=0,
                creationflags=flags,
            )
            log.close()
            self._stderr_thread = threading.Thread(
                target=self._forward_stderr,
                args=(self.process,),
                name="tts-mcp-child-trace",
                daemon=True,
            )
            self._stderr_thread.start()
            _record_trace(
                "process_started",
                component="mcp_server",
                child_pid=self.process.pid,
                log=str(self.log_path),
            )
            return self.status()

    def stop(self) -> dict[str, Any]:
        with self._lock:
            process = self.process
            if process is None or process.poll() is not None:
                self.process = None
                return self.status()
            _record_trace(
                "process_stop_requested",
                component="mcp_server",
                child_pid=process.pid,
            )
            if os.name == "nt":
                completed = subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if completed.returncode != 0 and process.poll() is None:
                    process.kill()
            else:
                process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            if self._stderr_thread is not None:
                self._stderr_thread.join(timeout=2)
                self._stderr_thread = None
            self.process = None
            _record_trace(
                "process_stopped",
                component="mcp_server",
                child_pid=process.pid,
                returncode=process.returncode,
            )
            return self.status()

    def restart(self) -> dict[str, Any]:
        self.stop()
        time.sleep(0.5)
        return self.start()


supervisor = ProcessSupervisor()


class SupervisorHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_GET(self) -> None:
        path = urlsplit(self.path).path.rstrip("/")
        if path == "/admin":
            response(self, 200, SUPERVISOR_HTML, "text/html; charset=utf-8")
        elif path in {"/health", "/admin/api/status"}:
            response(self, 200, {"ok": True, "service": "tts-mcp-supervisor", **supervisor.status()})
        else:
            response(self, 404, {"error": "not_found"})

    def do_POST(self) -> None:
        path = urlsplit(self.path).path.rstrip("/")
        if path not in {"/admin/api/server/start", "/admin/api/server/stop", "/admin/api/server/restart"}:
            response(self, 404, {"error": "not_found"})
            return
        action = path.rsplit("/", 1)[-1]
        try:
            status = getattr(supervisor, action)()
            response(self, 200, {"ok": True, "action": action, **status})
        except OSError as exc:
            response(self, 500, {"ok": False, "error": str(exc)})


def main() -> None:
    http = ThreadingHTTPServer((SUPERVISOR_HOST, SUPERVISOR_PORT), SupervisorHandler)
    try:
        if os.getenv("TTS_SUPERVISOR_AUTOSTART", "1").strip().lower() not in {"0", "false", "no", "off"}:
            supervisor.start()
        print("Live child server trace is mirrored below; MCP protocol output is saved to tts_mcp_server.log.", flush=True)
        print(f"TTS supervisor: http://{SUPERVISOR_HOST}:{SUPERVISOR_PORT}/admin", flush=True)
        http.serve_forever()
    finally:
        supervisor.stop()
        http.server_close()


if __name__ == "__main__":
    main()
