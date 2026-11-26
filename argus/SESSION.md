# Argus interactive session

Argus's Codex CLI runs in one detached `tmux` session named `argus-codex`. This preserves the live terminal across SSH disconnects. It starts idle, makes no autonomous model requests, and opens no network listener. The session belongs to the `argus` Unix account; the CLI uses full local execution (`-s danger-full-access -a never`), as authorized for Argus.

From Nexus, use a terminal:

```sh
ssh -t argus /noobia/argus/launch
```

`/noobia/argus/launch status` returns running or stopped. `launch start` creates the session without attaching; repeating it reuses the one session. If the tmux session ends, `launch resume` starts Codex with `resume --last` and attaches to the latest saved interactive conversation. `launch` without an argument attaches to the running session; if none exists, it starts a new one. To detach while keeping Argus alive, press `Ctrl-b d` inside tmux.

The shell launcher is in Git. `tmux` 3.5a-3 and its `libjemalloc2` dependency were installed on the Pi on 2026-11-27; no other package was upgraded. The first session was started and verified to contain the Codex process. A restart or power loss ends tmux, but Codex's saved conversation can be resumed explicitly. No service restarts it at boot, and no prompt queue is connected to this session. The separate historian worker continues to handle only fixed archive and ledger jobs.
