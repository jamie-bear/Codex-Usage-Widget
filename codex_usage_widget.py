#!/usr/bin/env python3
"""Local Codex/ChatGPT subscription usage widget.

Runs a localhost-only web page and reads rate-limit information through the
Codex App Server JSON-RPC interface. It does not read auth.json, browser
cookies, or raw OAuth tokens.

Requires:
  - Python 3.10+
  - `codex` CLI installed and logged in with ChatGPT
"""

from __future__ import annotations

import argparse
import atexit
import json
import os
import queue
import shutil
import signal
import subprocess
import sys
import threading
import time
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
RPC_TIMEOUT = 20.0
CACHE_SECONDS = 15.0

PAGE = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Codex Usage</title>
<style>
  :root { color-scheme: light dark; --bg:#171717; --card:#232323; --line:#3a3a3a; --text:#f2f2f2; --muted:#a8a8a8; --track:#444; --fill:#d8d8d8; --error:#ffb4ab; }
  @media (prefers-color-scheme: light) {
    :root { --bg:#f4f4f4; --card:#fff; --line:#ddd; --text:#181818; --muted:#666; --track:#e8e8e8; --fill:#333; --error:#b3261e; }
  }
  * { box-sizing:border-box; }
  html,body { margin:0; min-height:100%; font:14px/1.4 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; background:var(--bg); color:var(--text); }
  body { display:grid; place-items:start center; padding:28px 14px; }
  .card { width:min(420px,100%); background:var(--card); border:1px solid var(--line); border-radius:18px; padding:18px; box-shadow:0 14px 40px rgba(0,0,0,.14); }
  header { display:flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom:14px; }
  h1 { font-size:16px; margin:0; font-weight:650; }
  .plan { color:var(--muted); text-transform:capitalize; }
  .row { border-top:1px solid var(--line); padding:14px 0 4px; }
  .topline { display:grid; grid-template-columns:72px 1fr auto; gap:10px; align-items:center; }
  .label { font-weight:550; }
  .pct { font-variant-numeric:tabular-nums; font-weight:650; min-width:44px; text-align:right; }
  .reset { color:var(--muted); font-variant-numeric:tabular-nums; font-size:12px; margin:7px 0 0 82px; }
  .bar { height:7px; border-radius:999px; background:var(--track); overflow:hidden; }
  .fill { height:100%; width:0; background:var(--fill); border-radius:inherit; transition:width .25s ease; }
  footer { display:flex; justify-content:space-between; align-items:center; gap:12px; margin-top:14px; color:var(--muted); font-size:12px; }
  button { font:inherit; color:inherit; background:transparent; border:1px solid var(--line); border-radius:9px; padding:5px 9px; cursor:pointer; }
  button:hover { background:rgba(127,127,127,.12); }
  #error { color:var(--error); white-space:pre-wrap; padding-top:10px; }
  .empty { color:var(--muted); padding:10px 0; }
  .credits { color:var(--muted); font-size:12px; margin-top:10px; }
</style>
</head>
<body>
<main class="card">
  <header><div><h1>Codex usage</h1><div class="plan" id="plan">Loading…</div></div><button id="refresh" type="button">Refresh</button></header>
  <section id="limits"></section>
  <div id="credits" class="credits"></div>
  <div id="error"></div>
  <footer><span id="updated">Connecting…</span><span>localhost only</span></footer>
</main>
<script>
const limitsEl=document.getElementById('limits');
const planEl=document.getElementById('plan');
const updatedEl=document.getElementById('updated');
const errorEl=document.getElementById('error');
const creditsEl=document.getElementById('credits');

function resetText(ts) {
  if (!ts) return 'Reset time unavailable';
  const d=new Date(ts*1000);
  const now=new Date();
  const sameDay=d.toDateString()===now.toDateString();
  const t=d.toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'});
  if (sameDay) return `Resets ${t}`;
  return `Resets ${d.toLocaleDateString([], {month:'short',day:'numeric'})} ${t}`;
}
function esc(s) { return String(s).replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
function render(data) {
  errorEl.textContent='';
  planEl.textContent=data.plan ? `ChatGPT ${data.plan}` : 'ChatGPT plan';
  if (!data.windows || data.windows.length===0) {
    limitsEl.innerHTML='<div class="empty">No rate-limit windows were returned for this account.</div>';
  } else {
    limitsEl.innerHTML=data.windows.map(w=>{
      const p=Math.max(0,Math.min(100,Number(w.remainingPercent)));
      return `<div class="row"><div class="topline"><span class="label">${esc(w.label)}</span><div class="bar" title="${p}% remaining"><div class="fill" style="width:${p}%"></div></div><span class="pct">${Math.round(p)}%</span></div><div class="reset">${esc(resetText(w.resetsAt))}</div></div>`;
    }).join('');
  }
  const c=data.credits;
  if (c && c.hasCredits) creditsEl.textContent=c.unlimited ? 'Credits: unlimited' : `Credits: ${c.balance ?? 'available'}`;
  else creditsEl.textContent='';
  updatedEl.textContent=`Updated ${new Date(data.fetchedAt*1000).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit',second:'2-digit'})}`;
}
async function refresh() {
  document.getElementById('refresh').disabled=true;
  try {
    const r=await fetch('/api/usage', {cache:'no-store'});
    const j=await r.json();
    if (!r.ok) throw new Error(j.error || `HTTP ${r.status}`);
    render(j);
  } catch(e) {
    errorEl.textContent=e.message;
    updatedEl.textContent='Update failed';
  } finally {
    document.getElementById('refresh').disabled=false;
  }
}
document.getElementById('refresh').addEventListener('click',refresh);
refresh();
setInterval(refresh, 60000);
</script>
</body>
</html>'''


class CodexAppServer:
    """Small JSON-RPC client for a local `codex app-server` process."""

    def __init__(self) -> None:
        self.proc: subprocess.Popen[str] | None = None
        self._reader: threading.Thread | None = None
        self._pending: dict[int, queue.Queue[dict[str, Any]]] = {}
        self._pending_lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._lifecycle_lock = threading.RLock()
        self._next_id = 1
        self._codex = self._find_codex()

    @staticmethod
    def _find_codex() -> str:
        explicit = os.environ.get("CODEX_BIN")
        if explicit:
            return explicit
        found = shutil.which("codex.exe") if os.name == "nt" else None
        found = found or shutil.which("codex")
        if not found:
            raise RuntimeError(
                "Could not find the `codex` CLI in PATH. Install Codex, restart the terminal, "
                "then run `codex` once and sign in with your ChatGPT account."
            )
        return found

    def _command(self) -> tuple[Any, bool]:
        args = [self._codex, "app-server", "--listen", "stdio://"]
        if os.name == "nt" and self._codex.lower().endswith((".cmd", ".bat")):
            return subprocess.list2cmdline(args), True
        return args, False

    def start(self) -> None:
        with self._lifecycle_lock:
            if self.proc and self.proc.poll() is None:
                return
            self.close()
            cmd, use_shell = self._command()
            creationflags = 0
            if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
                creationflags = subprocess.CREATE_NO_WINDOW
            self.proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                shell=use_shell,
                creationflags=creationflags,
            )
            self._reader = threading.Thread(target=self._reader_loop, args=(self.proc,), daemon=True)
            self._reader.start()

            self._rpc(
                "initialize",
                {
                    "clientInfo": {"name": "local-codex-usage-widget", "title": "Local Codex Usage Widget", "version": "1.0.0"},
                    "capabilities": {"experimentalApi": False},
                },
                timeout=RPC_TIMEOUT,
            )
            self._notify("initialized")

    def _reader_loop(self, proc: subprocess.Popen[str]) -> None:
        assert proc.stdout is not None
        try:
            for raw in proc.stdout:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                request_id = msg.get("id")
                if isinstance(request_id, int):
                    with self._pending_lock:
                        q = self._pending.get(request_id)
                    if q:
                        q.put(msg)
        finally:
            err = {"error": {"message": "Codex app-server stopped unexpectedly."}}
            with self._pending_lock:
                queues = list(self._pending.values())
            for q in queues:
                try:
                    q.put_nowait(err)
                except queue.Full:
                    pass

    def _send(self, obj: dict[str, Any]) -> None:
        proc = self.proc
        if not proc or proc.poll() is not None or proc.stdin is None:
            raise RuntimeError("Codex app-server is not running.")
        line = json.dumps(obj, separators=(",", ":")) + "\n"
        with self._write_lock:
            proc.stdin.write(line)
            proc.stdin.flush()

    def _rpc(self, method: str, params: dict[str, Any] | None = None, timeout: float = RPC_TIMEOUT) -> dict[str, Any]:
        with self._pending_lock:
            request_id = self._next_id
            self._next_id += 1
            q: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1)
            self._pending[request_id] = q
        try:
            msg: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id, "method": method}
            if params is not None:
                msg["params"] = params
            self._send(msg)
            try:
                response = q.get(timeout=timeout)
            except queue.Empty as exc:
                raise RuntimeError(f"Timed out waiting for Codex app-server method {method!r}.") from exc
            if response.get("error"):
                error = response["error"]
                if isinstance(error, dict):
                    raise RuntimeError(error.get("message") or json.dumps(error))
                raise RuntimeError(str(error))
            result = response.get("result")
            if not isinstance(result, dict):
                raise RuntimeError(f"Codex app-server returned an unexpected response for {method!r}.")
            return result
        finally:
            with self._pending_lock:
                self._pending.pop(request_id, None)

    def _notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        msg: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        self._send(msg)

    def get_rate_limits(self) -> dict[str, Any]:
        # Serialize lifecycle/retry operations. The app-server itself may still emit
        # notifications; the reader thread ignores those for this request/response flow.
        with self._lifecycle_lock:
            for attempt in range(2):
                try:
                    self.start()
                    return self._rpc("account/rateLimits/read", timeout=RPC_TIMEOUT)
                except Exception:
                    self.close()
                    if attempt == 1:
                        raise
            raise RuntimeError("Unable to read Codex rate limits.")

    def close(self) -> None:
        with self._lifecycle_lock:
            proc, self.proc = self.proc, None
            if not proc:
                return
            try:
                if proc.stdin:
                    proc.stdin.close()
            except Exception:
                pass
            if proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(timeout=2)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass


def _window_label(minutes: Any) -> str:
    if not isinstance(minutes, (int, float)):
        return "Usage"
    minutes = int(minutes)
    if minutes == 300:
        return "5h"
    if minutes == 10080:
        return "Weekly"
    if minutes % 10080 == 0:
        weeks = minutes // 10080
        return f"{weeks}w"
    if minutes % 1440 == 0:
        days = minutes // 1440
        return f"{days}d"
    if minutes % 60 == 0:
        hours = minutes // 60
        return f"{hours}h"
    return f"{minutes}m"


def normalize_rate_limits(result: dict[str, Any]) -> dict[str, Any]:
    by_id = result.get("rateLimitsByLimitId")
    snap = by_id.get("codex") if isinstance(by_id, dict) else None
    if not isinstance(snap, dict):
        snap = result.get("rateLimits")
    if not isinstance(snap, dict):
        raise RuntimeError("No Codex rate-limit snapshot was returned.")

    windows: list[dict[str, Any]] = []
    seen: set[tuple[Any, Any]] = set()
    for key in ("primary", "secondary"):
        w = snap.get(key)
        if not isinstance(w, dict) or not isinstance(w.get("usedPercent"), (int, float)):
            continue
        mins = w.get("windowDurationMins")
        reset_at = w.get("resetsAt")
        dedupe = (mins, reset_at)
        if dedupe in seen:
            continue
        seen.add(dedupe)
        used = max(0.0, min(100.0, float(w["usedPercent"])))
        windows.append(
            {
                "label": _window_label(mins),
                "windowDurationMins": mins,
                "usedPercent": used,
                "remainingPercent": 100.0 - used,
                "resetsAt": reset_at if isinstance(reset_at, int) else None,
            }
        )

    windows.sort(key=lambda x: x.get("windowDurationMins") if isinstance(x.get("windowDurationMins"), (int, float)) else 10**18)
    credits = snap.get("credits") if isinstance(snap.get("credits"), dict) else None
    reset_credits = result.get("rateLimitResetCredits") if isinstance(result.get("rateLimitResetCredits"), dict) else None

    return {
        "plan": snap.get("planType"),
        "limitId": snap.get("limitId") or "codex",
        "windows": windows,
        "credits": credits,
        "resetCredits": reset_credits,
        "rateLimitReachedType": snap.get("rateLimitReachedType"),
        "fetchedAt": int(time.time()),
    }


class UsageCache:
    def __init__(self, app_server: CodexAppServer) -> None:
        self.app_server = app_server
        self.lock = threading.Lock()
        self.data: dict[str, Any] | None = None
        self.at = 0.0

    def get(self) -> dict[str, Any]:
        with self.lock:
            now = time.monotonic()
            if self.data is not None and now - self.at < CACHE_SECONDS:
                return self.data
            raw = self.app_server.get_rate_limits()
            self.data = normalize_rate_limits(raw)
            self.at = now
            return self.data


class WidgetHandler(BaseHTTPRequestHandler):
    cache: UsageCache

    def log_message(self, fmt: str, *args: Any) -> None:
        # Keep the terminal quiet except for startup/errors.
        return

    def _headers(self, status: HTTPStatus, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            body = PAGE.encode("utf-8")
            self._headers(HTTPStatus.OK, "text/html; charset=utf-8")
            self.wfile.write(body)
            return
        if path == "/api/usage":
            try:
                payload = self.cache.get()
                body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
                self._headers(HTTPStatus.OK, "application/json; charset=utf-8")
            except Exception as exc:
                body = json.dumps({"error": str(exc)}).encode("utf-8")
                self._headers(HTTPStatus.SERVICE_UNAVAILABLE, "application/json; charset=utf-8")
            self.wfile.write(body)
            return
        self._headers(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8")
        self.wfile.write(b"Not found")


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve a localhost Codex usage widget.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"localhost port (default: {DEFAULT_PORT})")
    parser.add_argument("--no-browser", action="store_true", help="do not open the page automatically")
    args = parser.parse_args()

    if sys.version_info < (3, 10):
        print("Python 3.10 or newer is required.", file=sys.stderr)
        return 2

    try:
        app_server = CodexAppServer()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    atexit.register(app_server.close)

    WidgetHandler.cache = UsageCache(app_server)
    try:
        httpd = ThreadingHTTPServer((DEFAULT_HOST, args.port), WidgetHandler)
    except OSError as exc:
        print(f"Could not bind http://{DEFAULT_HOST}:{args.port}: {exc}", file=sys.stderr)
        return 1

    url = f"http://{DEFAULT_HOST}:{args.port}/"
    print(f"Codex usage widget: {url}")
    print("Press Ctrl+C to stop.")

    if not args.no_browser:
        threading.Timer(0.35, lambda: webbrowser.open(url)).start()

    def stop(_signum: int, _frame: Any) -> None:
        threading.Thread(target=httpd.shutdown, daemon=True).start()

    try:
        signal.signal(signal.SIGTERM, stop)
        if hasattr(signal, "SIGINT"):
            signal.signal(signal.SIGINT, stop)
    except Exception:
        pass

    try:
        httpd.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        app_server.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
