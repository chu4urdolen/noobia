#!/usr/bin/env python3
"""
Argus shell bridge + inline editor (with simple auth):
- PTY /bin/bash -i with live streaming over WebSocket (/stream)
- Login via POST /login; all routes require header X-Auth-Password or ?token=
- 1000-line rolling history
"""
import asyncio, os, pty, signal, subprocess, threading, re
from collections import deque
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Depends, HTTPException, status, Query
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.websockets import WebSocketState

# ---------- Auth ----------
PASSWORD = os.environ.get("ARGUS_PASSWORD", "changeme")

def verify_password_header(request: Request):
    token = request.headers.get("X-Auth-Password") or request.query_params.get("token")
    if token != PASSWORD:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
    return True

# ---------- Config ----------
SHELL = "/bin/bash"
SHELL_ARGS = ["-i"]
ENV = dict(os.environ, TERM="dumb")
HISTORY_LINES = 1000

# Strip ANSI/OSC/control sequences
ANSI_RE = re.compile(
    r"("                       
    r"\x1B\[[0-?]*[ -/]*[@-~]"  # CSI
    r"|\x1B\][^\x07\x1b]*\x07"  # OSC ... BEL
    r"|\x1B\][^\x1b]*\x1B\\"    # OSC ... ST
    r"|\x1B[@-Z\\-_]"           # 2-char ESC
    r")"
)
CTRL_RE = re.compile(r"[^\x09\x0A\x0D\x20-\x7E]")

def scrub(s: str) -> str:
    s = s.replace("\x1b[?2004h", "").replace("\x1b[?2004l", "")
    s = ANSI_RE.sub("", s)
    s = CTRL_RE.sub("", s)
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    return s

app = FastAPI()

# ---------- PTY + Bash ----------
master_fd, slave_fd = pty.openpty()
proc = subprocess.Popen(
    [SHELL] + SHELL_ARGS,
    stdin=slave_fd, stdout=slave_fd, stderr=slave_fd,
    preexec_fn=os.setsid, close_fds=True, env=ENV
)
os.close(slave_fd)

# ---------- Broadcast + History ----------
clients_lock = threading.Lock()
clients: set[WebSocket] = set()
broadcast_queue: asyncio.Queue[str] = asyncio.Queue()
history = deque(maxlen=HISTORY_LINES)
_hist_buf = ""

def _ingest_text(txt: str):
    global _hist_buf
    _hist_buf += txt
    parts = _hist_buf.split('\n')
    _hist_buf = parts[-1]
    for line in parts[:-1]:
        history.append(line + '\n')

async def _broadcaster():
    while True:
        msg = await broadcast_queue.get()
        _ingest_text(msg)
        with clients_lock:
            targets = list(clients)
        if targets:
            await asyncio.gather(*[
                ws.send_text(msg) for ws in targets
                if ws.client_state == WebSocketState.CONNECTED
            ], return_exceptions=True)

def _reader_thread(loop: asyncio.AbstractEventLoop):
    try:
        while True:
            try:
                chunk = os.read(master_fd, 4096)
                if not chunk: break
                text = chunk.decode("utf-8", errors="replace")
                clean = scrub(text)
                if clean:
                    asyncio.run_coroutine_threadsafe(broadcast_queue.put(clean), loop)
            except OSError:
                break
    finally:
        asyncio.run_coroutine_threadsafe(broadcast_queue.put("\n[pty closed]\n"), loop)

@app.on_event("startup")
async def _startup():
    loop = asyncio.get_running_loop()
    asyncio.create_task(_broadcaster())
    t = threading.Thread(target=_reader_thread, args=(loop,), daemon=True)
    t.start()

# ---------- Routes ----------
@app.get("/", response_class=HTMLResponse)
async def index():
    if os.path.exists("index.html"):
        with open("index.html", "r", encoding="utf-8") as f:
            return HTMLResponse(f.read())
    return HTMLResponse("<h3>Put index.html next to server.py</h3>")

@app.post("/login")
async def login(payload: dict):
    return {"ok": payload.get("password") == PASSWORD}

def _cwd() -> str:
    return os.readlink(f"/proc/{proc.pid}/cwd")

def _resolve_in_cwd(name: str) -> str:
    base = os.path.realpath(_cwd())
    target = os.path.realpath(os.path.join(base, name))
    if not (target == base or target.startswith(base + os.sep)):
        raise ValueError("invalid path")
    return target

@app.get("/cwd")
async def get_cwd(_: bool = Depends(verify_password_header)):
    try:
        return JSONResponse({"cwd": _cwd()})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/open")
async def open_file(request: Request, _: bool = Depends(verify_password_header)):
    try:
        name = request.query_params.get("filename", "")
        if not name:
            return JSONResponse({"ok": False, "error": "filename required"}, status_code=400)
        path = _resolve_in_cwd(name)
        if not os.path.exists(path):
            return JSONResponse({"ok": True, "exists": False, "path": path, "bytes": 0, "content": ""})
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            data = f.read()
        return JSONResponse({"ok": True, "exists": True, "path": path, "bytes": len(data), "content": data})
    except ValueError as ve:
        return JSONResponse({"ok": False, "error": str(ve)}, status_code=400)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

@app.post("/run")
async def run_cmd(payload: dict, _: bool = Depends(verify_password_header)):
    cmd = (payload.get("cmd") or "").rstrip("\r\n")
    if not cmd: return JSONResponse({"ok": True})
    try:
        os.write(master_fd, (cmd + "\n").encode())
        return JSONResponse({"ok": True})
    except OSError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

@app.post("/signal")
async def send_signal(payload: dict, _: bool = Depends(verify_password_header)):
    sig = (payload.get("sig") or "").upper()
    sig_map = {"INT": signal.SIGINT, "TERM": signal.SIGTERM, "HUP": signal.SIGHUP}
    if sig not in sig_map:
        return JSONResponse({"ok": False, "error": "unknown signal"}, status_code=400)
    try:
        if sig == "INT":
            sent = False
            try:
                fg_pgid = os.tcgetpgrp(master_fd)
                os.killpg(fg_pgid, signal.SIGINT); sent = True
            except Exception:
                pass
            if not sent:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGINT); sent = True
                except Exception:
                    pass
            try:
                os.write(master_fd, b"\x03")
            except Exception:
                pass
            if not sent:
                return JSONResponse({"ok": False, "error": "could not deliver SIGINT"}, status_code=500)
            return JSONResponse({"ok": True})
        os.killpg(os.getpgid(proc.pid), sig_map[sig])
        return JSONResponse({"ok": True})
    except ProcessLookupError:
        return JSONResponse({"ok": False, "error": "process not running"}, status_code=410)

@app.post("/save")
async def save_file(payload: dict, _: bool = Depends(verify_password_header)):
    name = payload.get("filename")
    content = payload.get("content", "")
    if not name or not isinstance(name, str):
        return JSONResponse({"ok": False, "error": "filename required"}, status_code=400)
    try:
        path = _resolve_in_cwd(name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return JSONResponse({"ok": True, "path": path, "bytes": len(content)})
    except ValueError as ve:
        return JSONResponse({"ok": False, "error": str(ve)}, status_code=400)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

@app.websocket("/stream")
async def stream(ws: WebSocket, token: str | None = Query(default=None)):
    if token != PASSWORD:
        await ws.close(code=1008)  # policy violation
        return
    await ws.accept()
    with clients_lock:
        clients.add(ws)
    try:
        if history:
            await ws.send_text("".join(history))
        while True:
            await asyncio.sleep(60)
    except WebSocketDisconnect:
        pass
    finally:
        with clients_lock:
            clients.discard(ws)

@app.on_event("shutdown")
async def _shutdown():
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except Exception:
        pass
