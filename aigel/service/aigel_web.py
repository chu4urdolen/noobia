#!/usr/bin/env python3
"""Aigel's web page (PLAN A4, contract section 5: the "People" channel).

A small, fully offline page on Nexus port 112 that a Noob can open:

- **See the hosts:** last seen, awake/silent flag, chunk count, last
  decision, from ``GET /api/v1/status``.
- **Read the recent chunks and Aigel's decisions** (bounded history,
  part of the same status reply).
- **Talk to Aigel:** ``POST /api/v1/chat`` - a bounded, logged chat
  turn on Qwen. Read-only on the hosts: she describes the world,
  she never commands it (contract section 5), and her chat prompt
  keeps that rule.

The page is self-contained: no CDN, no external assets. All data is
JSON from ``/api/v1/*`` and rendered through the DOM API
(``textContent``), so host names and sense lines cannot inject
markup into the page.

Authentication: the chunk path keeps its per-host HMAC/Bearer auth.
The chat requires a ``chat_token`` (``--chat-token`` or
``AIGEL_CHAT_TOKEN``): until one is configured the chat endpoint is
**disabled** and answers an honest 503 - no anonymous chat, even on
the Noobia LAN (Gwyn review #255). With a token set, requests need
``Authorization: Bearer <token>``.

Bounded: chat body 8 KiB, message <= 1000 chars, reply <= 1000
chars, at most one chat turn every 2 s and at most 60 turns per
hour (Aigel shares the single Qwen queue with everyone else).
Qwen down -> honest 503.

    python3 aigel/service/aigel_intake.py --port 112   # A1 + A4 together
"""

from __future__ import annotations

import hmac
import json
import threading
import time

try:  # package import (aigel.service.aigel_web)
    from .aigel_think import AigelChatUnavailable, CHAT_MAX_INPUT_CHARS
except ImportError:  # direct script use from aigel/service/
    from aigel_think import AigelChatUnavailable, CHAT_MAX_INPUT_CHARS

MAX_CHAT_BODY_BYTES = 8_192
DEFAULT_MIN_GAP_S = 2.0
CHAT_HOURLY_CAP = 60  # turns per rolling hour: protect the shared Qwen queue

PAGE = b"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Aigel - nurse angel</title>
<style>
:root { color-scheme: dark light; }
body { font-family: system-ui, sans-serif; max-width: 46rem; margin: 2rem auto;
       padding: 0 1rem; line-height: 1.45; }
h1 { font-weight: 600; } h1 small { font-weight: 400; opacity: .7; }
h2 { font-size: 1rem; font-weight: 600; margin-top: 1.6rem; }
table { border-collapse: collapse; width: 100%; }
td, th { text-align: left; padding: .3rem .5rem;
         border-bottom: 1px solid rgba(127,127,127,.25); }
.badge { padding: .05rem .45rem; border-radius: .6rem; font-size: .8em; }
.badge.silent { background: #b34455; color: #fff; }
.badge.awake { background: #2a8a5f; color: #fff; }
.meta { opacity: .72; font-size: .9em; }
#recent li { margin: .6rem 0; }
#chat { display: flex; gap: .5rem; margin-top: .6rem; }
#chat input { flex: 1; padding: .5rem .6rem; font: inherit; }
#talk .them, #talk .her { margin: .55rem 0; max-width: 88%; white-space: pre-wrap;
       padding: .4rem .6rem; border-radius: .6rem; }
#talk .them { margin-left: auto; background: rgba(127,127,127,.18); }
#talk .her { background: rgba(55,122,170,.20); }
button { padding: .5rem .8rem; font: inherit; cursor: pointer; }
#error { color: #c0524f; min-height: 1.2em; }
</style>
</head>
<body>
<h1>Aigel <small>- nurse angel of Noobia</small></h1>
<p>This page is read-only on every host: Aigel describes the world;
she never commands it.</p>

<h2>Hosts</h2>
<table id="hosts">
<tr><th>host</th><th>last seen</th><th>chunks</th><th>last decision</th><th></th></tr>
</table>

<h2>Recent chunks &amp; decisions</h2>
<ul id="recent"></ul>
<button id="refresh">refresh</button>

<h2>Talk to Aigel</h2>
<div id="talk"></div>
<form id="chat">
  <input id="msg" placeholder="say something gentle..." maxlength="1000" autocomplete="off">
  <button>send</button>
</form>
<div id="error"></div>

<script>
const $ = (id) => document.getElementById(id);
function rel(t) {
  if (!t) return 'never';
  const s = Math.max(0, Date.now() / 1000 - t);
  if (s < 90) return Math.round(s) + 's ago';
  if (s < 5400) return Math.round(s / 60) + 'm ago';
  if (s < 172800) return Math.round(s / 3600) + 'h ago';
  return Math.round(s / 86400) + 'd ago';
}
function cell(v) { const td = document.createElement('td'); td.textContent = (v === null || v === undefined) ? '' : String(v); return td; }
async function load() {
  $('error').textContent = '';
  try {
    const r = await fetch('/api/v1/status');
    const d = await r.json();
    const tbl = $('hosts');
    tbl.querySelectorAll('tr[data-host]').forEach(tr => tr.remove());
    for (const [host, h] of Object.entries(d.hosts || {})) {
      const tr = document.createElement('tr'); tr.dataset.host = host;
      tr.append(cell(host), cell(rel(h.last_seen)), cell(h.chunks || 0), cell(h.last_decision || ''));
      const td = document.createElement('td');
      const b = document.createElement('span');
      b.className = 'badge ' + (h.silent ? 'silent' : 'awake');
      b.textContent = h.silent ? 'silent' : 'awake';
      td.append(b); tr.append(td);
      tbl.append(tr);
    }
    const ul = $('recent'); ul.textContent = '';
    (d.recent || []).forEach(c => {
      const li = document.createElement('li');
      const meta = document.createElement('div'); meta.className = 'meta';
      meta.textContent = c.host + ' - ' + (c.reason || 'unknown') + ' - ' + c.lines + ' lines - ' + rel(c.t);
      li.append(meta);
      if (Array.isArray(c.evidence) && c.evidence.length) {
        c.evidence.forEach(line => {
          const e = document.createElement('div'); e.className = 'meta';
          e.textContent = line; li.append(e);
        });
      }
      if (c.message) { const m = document.createElement('div'); m.textContent = 'Aigel: ' + c.message; li.append(m); }
      if (c.note) { const n = document.createElement('div'); n.className = 'meta'; n.textContent = 'note: ' + c.note; li.append(n); }
      ul.append(li);
    });
  } catch (e) { $('error').textContent = 'status: ' + e; }
}
$('refresh').addEventListener('click', load);
$('chat').addEventListener('submit', async (ev) => {
  ev.preventDefault();
  const msg = $('msg').value.trim();
  if (!msg) return;
  $('error').textContent = '';
  const talk = $('talk');
  const p = document.createElement('div'); p.className = 'them'; p.textContent = msg; talk.append(p);
  $('msg').value = '';
  const her = () => { const q = document.createElement('div'); q.className = 'her'; talk.append(q); return q; };
  try {
    const r = await fetch('/api/v1/chat', { method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: msg }) });
    const d = await r.json().catch(() => ({}));
    const q = her();
    q.textContent = r.ok ? (d.reply || '(no reply)') : (d.error || ('error ' + r.status));
  } catch (e) { her().textContent = 'Aigel is unreachable: ' + e; }
});
load();
setInterval(load, 10000);
</script>
</body>
</html>
"""


class AigelWeb:
    """The people channel: status (from the intake state) + chat."""

    def __init__(self, intake, log, chat_token: str | None = None,
                 min_gap_s: float = DEFAULT_MIN_GAP_S,
                 hourly_cap: int = CHAT_HOURLY_CAP, now_fn=time.time):
        self.intake = intake
        self.log = log
        self.chat_token = chat_token
        self.min_gap_s = float(min_gap_s)
        self.hourly_cap = max(1, int(hourly_cap))
        self.now_fn = now_fn
        self._lock = threading.Lock()
        self._last_chat = 0.0
        self._chat_times: list = []

    # -- chat ---------------------------------------------------------------

    def check_chat_auth(self, headers: dict) -> tuple[bool, str | None]:
        if not self.chat_token:
            return True, None  # no token configured: documented LAN-only risk
        auth = headers.get("Authorization")
        if not isinstance(auth, str) or not hmac.compare_digest(
                auth, "Bearer " + self.chat_token):
            return False, "bad token"
        return True, None

    def handle_chat(self, raw_body: bytes, headers: dict,
                    now: float | None = None) -> tuple[int, dict]:
        now = float(now if now is not None else self.now_fn())
        if len(raw_body) > MAX_CHAT_BODY_BYTES:
            self.log.write("chat refused: body over bound")
            return 413, {"error": "message too large"}
        if not self.chat_token:
            self.log.write("chat refused: disabled (no token configured)")
            return 503, {"error": "chat disabled: no chat token configured"}
        ok, why = self.check_chat_auth(headers)
        if not ok:
            self.log.write(f"chat refused: {why}")
            return 401, {"error": why}
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self.log.write("chat refused: not json")
            return 400, {"error": "not json"}
        message = payload.get("message") if isinstance(payload, dict) else None
        if not isinstance(message, str) or not message.strip():
            self.log.write("chat refused: empty message")
            return 400, {"error": "message must be a non-empty string"}
        if len(message) > CHAT_MAX_INPUT_CHARS:
            self.log.write(f"chat refused: message over bound ({len(message)})")
            return 400, {"error": "message over bound"}
        with self._lock:
            if now - self._last_chat < self.min_gap_s:
                self.log.write("chat: too soon, waiting")
                return 429, {"error": "aigel is still thinking; wait a moment"}
            self._chat_times = [t for t in self._chat_times if now - t < 3600]
            if len(self._chat_times) >= self.hourly_cap:
                self.log.write("chat: hourly cap reached")
                return 429, {"error": "hourly chat limit reached; try again in a bit"}
            self._last_chat = now
            self._chat_times.append(now)
        self.log.write(f"chat in: {len(message)} chars")
        try:
            reply = self.intake.thinker.chat(message)
        except AigelChatUnavailable as e:
            self.log.write(f"chat: aigel unavailable: {str(e)[:120]}")
            return 503, {"error": f"aigel unavailable: {str(e)[:200]}"}
        except Exception as e:  # defensive: the page must never get a stack trace
            self.log.write(f"chat failed: {type(e).__name__}")
            return 503, {"error": "aigel could not answer"}
        self.log.write(f"chat out: {len(reply)} chars: {reply[:80]!r}")
        return 200, {"reply": reply}

    # -- the page -------------------------------------------------------------

    def page(self) -> bytes:
        return PAGE
