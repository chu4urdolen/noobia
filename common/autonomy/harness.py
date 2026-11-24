"""The host autonomy loop (PLAN H0): sense view -> chunks -> ranker/Aigel -> the Noob.

One ``Harness`` runs on each host that carries a Noob. Every collaborator is
injected, so each path is testable without a phone, a log, or Nexus:

    read_new()        -> list[str]          new raw lines of the noobia-sense view
    chunker           trigger.Chunker
    ranker            ranker.Ranker | None   (PRIORITY chunks only)
    client            .send_chunk(chunk) -> {decision, message, patterns, note,
                                             priority_rules?}
    adapter           agent_link.Adapter     (delivers to the Noob)
    emit(line)        writes a sense line    (heartbeat)
    log(line)         writes to the noobia-autonomy view
    on_priority_rules(rules)                 hands Aigel's rules to the prioritizer
    validate_pattern(p) raises ValueError    (ranker.validate_pattern bound to a corpus)

Routing (ARCHITECTURE.md §2):
- PRIORITY chunks go to the ranker. Explained lines become messages from
  the ranker, and unexplained lines go to Aigel.
- TIMEOUT and VOLUME chunks go straight to Aigel.
- Liveness: a heartbeat line every ``heartbeat_s``. If the sense view is
  silent for ``silence_s``, the harness reports it to Aigel directly, not
  through the log.

Bounds:
- at most 1 send to Aigel per ``min_interval_s`` and ``max_per_hour`` per
  rolling hour;
- while Aigel is unreachable or rate-limited, chunks wait in a queue of at
  most ``queue_max`` (oldest dropped and counted);
- one evidence list of at most 10 lines per message.
"""

from __future__ import annotations

from collections import deque
import time

try:
    from . import agent_link, sense
except ImportError:  # run from the directory, as on hosts
    import agent_link
    import sense

MAX_EVIDENCE = 10


class Harness:
    def __init__(self, *, host, read_new, chunker, client, adapter, ranker=None,
                 emit=None, log=None, on_priority_rules=None, validate_pattern=None,
                 clock=time.monotonic, heartbeat_s=300.0, silence_s=900.0,
                 min_interval_s=1.0, max_per_hour=30, queue_max=20,
                 extra_heartbeat_fields=None, disabled=None, combine=False,
                 aigel_enabled=True, async_aigel=False):
        self.host, self.read_new, self.chunker = host, read_new, chunker
        # combine (Tom 2026-11-23): every chunk, whatever closed it, goes
        # through the pattern DB, and all its unique sentences reach the Noob
        # as ONE observation ("You see laptop. You are now lying flat. ...").
        self.combine = bool(combine)
        # Aigel off (Tom 2026-11-23): lines no pattern explains go straight to
        # the Noob in the combined message instead of to Aigel.
        self.aigel_enabled = bool(aigel_enabled)
        # async_aigel: Aigel thinks on the same Qwen and can take a minute;
        # the call runs in a worker thread so reading senses and delivering
        # matched sentences to the Noob never waits for her. Replies are
        # applied here in the main loop (ranker and queue stay single-threaded).
        self.async_aigel = bool(async_aigel)
        self._inflight = None          # (thread, box) while a send is running
        self.client, self.adapter, self.ranker = client, adapter, ranker
        self.emit = emit or (lambda line: None)
        self.log = log or (lambda line: None)
        self.on_priority_rules = on_priority_rules
        self.validate_pattern = validate_pattern
        self.clock = clock
        self.heartbeat_s, self.silence_s = heartbeat_s, silence_s
        self.min_interval_s, self.max_per_hour = min_interval_s, max_per_hour
        self.extra_heartbeat_fields = extra_heartbeat_fields
        # Kill switch (ARCHITECTURE section 9.2). While it holds, step() reads new lines only
        # to discard them, sends nothing, delivers nothing, drops anything queued, and logs
        # once on each transition. Re-enabling starts fresh: no stale replay.
        self.disabled = disabled or (lambda: False)
        self._was_disabled = False
        self.queue = deque()
        self.queue_max = queue_max
        self.dropped = 0
        self.sent_times = deque()
        self.failures = 0              # consecutive send failures
        self.retry_at = 0.0            # no send attempt before this time
        self.max_backoff_s = 300.0
        start = clock()
        self.last_line_at = start
        self.last_heartbeat_at = None
        self.silence_reported = False

    # ------------------------------------------------------------------ loop
    def step(self):
        """One pass: read, chunk, route, flush. Returns a small summary."""
        now = self.clock()
        if self.disabled():
            return self._step_disabled(now)
        if self._was_disabled:
            self._was_disabled = False
            if hasattr(self.chunker, "reset"):
                self.chunker.reset()
            self.last_line_at = now
            self.silence_reported = False
            self.log("autonomy re-enabled: starting fresh; lines from the disabled period were discarded")
        self._heartbeat(now)
        lines = self.read_new()
        closed = []
        for line in lines:
            self.last_line_at = now
            self.silence_reported = False
            parsed = sense.parse_line(line)
            if parsed:
                if parsed["sense"] == "autonomy" and parsed["event"] == "heartbeat":
                    continue  # liveness only: a heartbeat must never wake Aigel by itself
                # Stripped from log if matches an ignore pattern in the ranker
                if self.ranker and hasattr(self.ranker, "is_ignored") and self.ranker.is_ignored(parsed):
                    continue
                # Built-in null perception stripping: "see nothing" / "hear nothing"
                if parsed.get("sense") == "camera" and parsed.get("event") == "frame.analyzed" and (parsed.get("fields") or {}).get("objects") == "0":
                    continue
                if parsed.get("sense") == "hearing" and parsed.get("event") == "status.sample":
                    continue
            closed += self.chunker.feed(line, now)
        closed += self.chunker.tick(now)
        delivered = 0
        for chunk in closed:
            delivered += self._route(chunk, now)
        self._check_silence(now)
        delivered += self._flush(now)
        return {"lines": len(lines), "chunks": len(closed), "delivered": delivered,
                "queued": len(self.queue), "dropped": self.dropped}

    def _step_disabled(self, now):
        discarded = len(self.read_new())         # advance past them: never replayed later
        dropped_now = len(self.queue)
        if dropped_now:
            self.queue.clear()
            self.dropped += dropped_now
        if not self._was_disabled:
            self._was_disabled = True
            self.log(f"autonomy disabled by kill switch: sending nothing; "
                     f"dropped {dropped_now} queued chunk(s)")
        elif dropped_now:
            self.log(f"autonomy disabled: dropped {dropped_now} queued chunk(s)")
        return {"lines": discarded, "chunks": 0, "delivered": 0, "queued": 0,
                "dropped": self.dropped, "disabled": True}

    def run(self, interval_s=1.0, stop=lambda: False):  # pragma: no cover - live loop
        while not stop():
            self.step()
            time.sleep(interval_s)

    # --------------------------------------------------------------- routing
    def _route(self, chunk, now):
        reason, lines = chunk["reason"], chunk["lines"]
        if self.combine and self.ranker is not None and reason != "silence":
            return self._route_combined(chunk, now)
        if reason == "priority" and self.ranker is not None:
            result = self.ranker.process(lines, now)
            delivered = 0
            deliveries = result.get("deliveries")
            if deliveries is None:  # an older ranker without templated messages
                deliveries = [(text, next((p for line, p in result["explained"]
                                           if self._message_of(p) == text), None))
                              for text in result["messages"]]
            for text, pid in deliveries:
                evidence = [l["raw"] for l, p in result["explained"] if p == pid][:MAX_EVIDENCE]
                delivered += self._deliver("ranker", text, evidence, pid)
            self.log(f"harness chunk reason=priority lines={len(lines)} "
                     f"explained={len(result['explained'])} unexplained={len(result['unexplained'])}")
            if result["unexplained"]:
                self._enqueue({"reason": "priority", "lines": result["unexplained"]})
            return delivered
        self.log(f"harness chunk reason={reason} lines={len(lines)} -> aigel")
        self._enqueue({"reason": reason, "lines": lines})
        return 0

    def _route_combined(self, chunk, now):
        reason, lines = chunk["reason"], chunk["lines"]
        result = self.ranker.process(lines, now)
        deliveries = result.get("deliveries") or []
        raw_texts = [str(t).strip() for t, _ in deliveries]
        direct = []
        if not self.aigel_enabled:
            # Routine samples are not events: since every line is P20 (Tom,
            # 2026-11-24), skip them by name or the Noob drowns in "sample" lines.
            direct = [l for l in result["unexplained"]
                      if l.get("p", 0) >= 1 and not l.get("self_caused") and l.get("text")
                      and not str(l.get("event", "")).endswith(("status.sample", "heartbeat"))]
            raw_texts += [str(l["text"]).strip() for l in direct]
        texts = list(dict.fromkeys(t for t in raw_texts if t))
        delivered = 0
        if texts:
            sentences = [t if t[-1] in ".!?" else t + "." for t in texts]
            pids = list(dict.fromkeys(pid for _, pid in deliveries if pid))
            evidence = ([l["raw"] for l, p in result["explained"] if l.get("raw")]
                        + [l["raw"] for l in direct if l.get("raw")])[:MAX_EVIDENCE]
            pid = pids[0] if len(pids) == 1 else "combined"
            delivered = self._deliver("ranker", " ".join(sentences), evidence, pid)
        self.log(f"harness chunk reason={reason} lines={len(lines)} combined={len(texts)} "
                 f"explained={len(result['explained'])} unexplained={len(result['unexplained'])}")
        # Observability pipeline stream log
        for p in ("/usr/local/lib/noobia/autonomy", "/usr/local/lib/noobia/lynx", "/noobia/lynx/tools"):
            if p not in sys.path:
                sys.path.insert(0, p)
        try:
            import stream_logger
            stream_logger.log_event("chunk_closed", {
                "reason": reason,
                "lines_count": len(lines),
                "raw_lines": [l.get("raw", "") if isinstance(l, dict) else str(l) for l in lines],
                "explained": [{"pattern_id": p, "raw": l.get("raw", "")} for l, p in result.get("explained", [])],
                "unexplained": [l.get("raw", "") if isinstance(l, dict) else str(l) for l in result.get("unexplained", [])],
                "rendered_text": " ".join(sentences) if texts else None,
            })
        except Exception:
            pass
        if result["unexplained"] and self.aigel_enabled:
            self._enqueue({"reason": reason, "lines": result["unexplained"]})
        return delivered

    def _message_of(self, pattern_id):
        for p in self.ranker.store:
            if p["id"] == pattern_id:
                return p["message"]
        return None

    def _enqueue(self, chunk):
        if len(self.queue) >= self.queue_max:
            self.queue.popleft()
            self.dropped += 1
            self.log(f"harness queue full: dropped oldest chunk (total dropped={self.dropped})")
        self.queue.append(chunk)

    def _rate_ok(self, now):
        while self.sent_times and now - self.sent_times[0] >= 3600:
            self.sent_times.popleft()
        if self.sent_times and now - self.sent_times[-1] < self.min_interval_s:
            return False
        return len(self.sent_times) < self.max_per_hour

    def _flush(self, now):
        delivered = 0
        if not self.aigel_enabled:
            self.queue.clear()
            return 0
        if self.async_aigel:
            return self._flush_async(now)
        if now < self.retry_at:
            return 0
        while self.queue and self._rate_ok(now):
            chunk = self.queue[0]
            try:
                reply = self.client.send_chunk(chunk)
            except Exception as exc:  # unreachable, refused or bad reply: keep it, back off
                self.failures += 1
                wait = min(self.max_backoff_s, 2.0 ** min(self.failures, 16))
                self.retry_at = now + wait
                self.log(f"harness aigel send failed ({self.failures} in a row, retry in {wait:.0f} s): "
                         f"{type(exc).__name__}: {str(exc)[:160]}")
                break
            self.failures = 0
            self.retry_at = 0.0
            self.queue.popleft()
            self.sent_times.append(now)
            delivered += self._apply_reply(reply, chunk)
        return delivered

    def _flush_async(self, now):
        import threading
        delivered = 0
        if self._inflight is not None:
            thread, box = self._inflight
            if thread.is_alive():
                return 0
            self._inflight = None
            chunk = box["chunk"]
            if "error" in box:
                exc = box["error"]
                self.failures += 1
                wait = min(self.max_backoff_s, 2.0 ** min(self.failures, 16))
                self.retry_at = now + wait
                self.log(f"harness aigel send failed ({self.failures} in a row, retry in {wait:.0f} s): "
                         f"{type(exc).__name__}: {str(exc)[:160]}")
            else:
                self.failures = 0
                self.retry_at = 0.0
                if self.queue and self.queue[0] is chunk:
                    self.queue.popleft()
                self.sent_times.append(now)
                delivered += self._apply_reply(box["reply"], chunk)
        if self.queue and now >= self.retry_at and self._rate_ok(now):
            box = {"chunk": self.queue[0]}

            def send(box=box):
                try:
                    box["reply"] = self.client.send_chunk(box["chunk"])
                except Exception as exc:  # noqa: BLE001
                    box["error"] = exc
            thread = threading.Thread(target=send, name="aigel-send", daemon=True)
            self._inflight = (thread, box)
            thread.start()
        return delivered

    def _apply_reply(self, reply, chunk):
        self.log(f"harness aigel decision={reply.get('decision')} note={str(reply.get('note', ''))[:120]}")
        delivered = 0
        if reply.get("decision") == "message" and reply.get("message"):
            evidence = [l.get("raw", "") for l in chunk["lines"]][:MAX_EVIDENCE]
            delivered += self._deliver("aigel", reply["message"], evidence, None)
        for pattern in reply.get("patterns") or []:
            self._add_pattern(pattern)
        rules = reply.get("priority_rules") or []
        if rules and self.on_priority_rules is not None:
            try:
                self.on_priority_rules(rules)
                self.log(f"harness priority_rules handed over n={len(rules)}")
            except Exception as exc:
                self.log(f"harness priority_rules rejected: {type(exc).__name__}: {str(exc)[:160]}")
        return delivered

    def _add_pattern(self, pattern):
        pid = pattern.get("id") if isinstance(pattern, dict) else None
        if self.ranker is None or self.validate_pattern is None or not hasattr(self.ranker, "add_pattern"):
            self.log(f"harness pattern ignored id={pid}: no validating ranker")
            return
        try:
            self.validate_pattern(pattern)
            self.ranker.add_pattern(pattern)
            self.log(f"harness pattern added id={pid} origin=aigel")
        except (ValueError, TypeError, KeyError) as exc:
            self.log(f"harness pattern rejected id={pid}: {str(exc)[:160]}")

    def _deliver(self, source, text, evidence, pattern_id):
        try:
            message = agent_link.make_message(self.host, source, "observation",
                                              str(text)[:agent_link.MAX_TEXT_CHARS].replace("\n", " "),
                                              [e for e in evidence if e][:MAX_EVIDENCE], pattern_id)
        except agent_link.MessageError as exc:
            self.log(f"harness message invalid: {exc}")
            return 0
        receipt = self.adapter.deliver(message)
        return 1 if receipt["status"] == "delivered" else 0

    # -------------------------------------------------------------- liveness
    def _heartbeat(self, now):
        if self.last_heartbeat_at is None or now - self.last_heartbeat_at >= self.heartbeat_s:
            self.last_heartbeat_at = now
            fields: dict[str, str | int] = {"host": self.host}
            if self.extra_heartbeat_fields:
                try:
                    extra = self.extra_heartbeat_fields()
                    if isinstance(extra, dict):
                        fields.update(extra)
                except Exception:
                    pass
            self.emit(sense.format_line(0, "autonomy", "heartbeat", fields))

    def _check_silence(self, now):
        if self.silence_reported or now - self.last_line_at < self.silence_s:
            return
        self.silence_reported = True
        line = sense.format_line(1, "autonomy", "view.silent",
                                 {"host": self.host, "silent_s": int(now - self.last_line_at)},
                                 "No sense line, not even my heartbeat, has reached the view")
        self.log(f"harness view silent for {int(now - self.last_line_at)} s -> aigel")
        self._enqueue({"reason": "silent", "lines": [sense.parse_line(line)]})
