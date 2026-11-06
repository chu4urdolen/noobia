# Lynx AI Agent Architecture

## 1. Overview

Lynx is a lightweight Android‑derived phone running Alpine Linux.  The goal is to
run a **local inference agent** that can call the full set of Noobia tools
(`lynx/tools/*`) while retaining the option to fall back to the remote
OpenAI Responses API when the Nexus proxy is unavailable.  The design keeps
all critical state local to the phone (user data, model files, and a
dedicated *agent* user) and relies on the already‑validated **Nexus
Responses** endpoint (see `docs/NEXUS-INFERENCE.md`).  The agent runs under a
dedicated Unix user (`lynx-agent`) with a tight permission set so that only
the agent and the NRP socket can be accessed.

The architecture is split into three layers:

1. **Local runtime** – the agent process, a Python wrapper that exposes a
   simple JSON‑over‑STDIN API compatible with the `Responses` protocol.  It
   talks to the *Noobia NRP* socket (`/run/lynx/nrp.sock`) for all local
   tools.
2. **Tool registry** – a shared catalog that lives both in the agent and
   in the `lynx/tools` package.  Adding a new tool file automatically
   registers it for both the agent and the NRP.
3. **Fallback layer** – if the Nexus proxy is unreachable, the agent
   switches to the OpenAI API via a locally stored key.  The key is kept in
   `/home/lynx/.config/noobia/gpt-oss-20b.api-key` and is never committed.

## 2. Local‑First Responses + Remote Fallback

* **Local** – the agent posts a JSON payload to the local `Responses`
  endpoint running on the phone (`http://127.0.0.1:8080/v1/responses`).  The
  endpoint is provided by the `noobia-inference-proxy.service` which
  forwards calls to the Ollama runtime (`gpt-oss:20b`).
* **Remote** – when a connection to the local proxy fails (timeout or
  connection refused), the agent falls back to `https://api.openai.com/v1/`
  with the stored API key.  The switch is performed per request; the
  agent remembers the last successful endpoint to avoid hammering the
  fallback unnecessarily.

Both endpoints honour the same function‑call schema, so the agent logic is
endpoint‑agnostic.

## 3. Shared Tool Registry

The `lynx/tools` directory already contains a collection of JSON‑schema
tool definitions (`*.json`).  The agent reads this directory at start‑up
and injects each entry into the `Responses` function‑call namespace.  The
registry is therefore **shared**:

```bash
cat projects/lynx_gain/LYNX_AGENT_ARCHITECTURE.md | grep -n 'tool registry'
```

When a new tool file is added to `lynx/tools`, the agent automatically
exposes it without further changes – the same file is used by the
`lynx-noob-runtime.py` NRP interface.  This guarantees that the agent and
any external caller (e.g., Rose’s chatbot) use identical definitions.

## 4. Codex CLI on ARM64‑musl

The agent uses the **Codex CLI** (`codex-cli`) for heavy text generation
only when the local Ollama runtime is disabled or when a user explicitly
requests a different model.  The CLI binaries are shipped in the
`codex` repository and the release that matches Alpine’s
`aarch64-unknown-linux-musl` is the one we need:

```
https://github.com/openai/codex/releases/download/v0.1.0/codex-cli-0.1.0-aarch64-unknown-linux-musl
```

The agent stores the binary in `/usr/local/bin/codex-cli` and calls it via
`subprocess.run`.  Permissions are set to `0755` and the binary is owned by
`lynx-agent`.

## 5. Agent Identity and Permissions

* **User** – `lynx-agent` (uid 900, gid 900).  The user has read/write
  access only to `/run/lynx/nrp.sock` and its own home directory.
* **Capabilities** – The agent is *unprivileged*; it cannot modify the
  kernel, boot images, or system services.  All calls to the NRP are
  forwarded to the `lynx-noob-runtime.py` process which runs as
  `root` but only exposes the API defined in
  `lynx/linux-port/docs/LYNX-NOOB-RUNTIME.md`.
* **Isolation** – The agent runs inside a `systemd` slice
  (`lynx-agent.slice`) with `MemoryLimit=2G` and `CPUQuota=50%` to avoid
  starving the phone.

## 6. Kernel vs Alpine Persistence

The current verified state (see `LYNX-KERNEL-TO-AGENT-GATE.md`) shows that
all camera modules, the NRP socket, and the local inference proxy can be
started from an **Alpine** root filesystem without flashing a new
`boot_a` image.  The only kernel‑level change required is the patched
`mtk-cam-isp.ko` module, which is loaded on demand by the NRP and does not
require persistence in the boot partition.  Therefore the agent can be
re‑installed or upgraded purely in user space.

## 7. Staged Build Plan

1. **Prerequisites** – Ensure the Nexus inference proxy is running
   (`systemctl status noobia-inference-proxy.service`).  Verify the local
   proxy responds:
   ```bash
   curl -s http://127.0.0.1:8080/health
   ```
2. **Deploy the agent user and directory** – create `/home/lynx` and
   install the `lynx-agent` user.
3. **Install Codex CLI** – download the ARM64 musl binary and place it in
   `/usr/local/bin/codex-cli`.
4. **Copy the tool registry** – link `lynx/tools/*.json` into
   `/home/lynx/agent-tools/`.
5. **Write the agent script** (`/home/lynx/agent.py`) that:
   * loads the registry,
   * starts a HTTP server on `127.0.0.1:8090` that accepts the
     `Responses` payload,
   * forwards to the local proxy or to OpenAI, and
   * invokes local tools via the NRP socket.
6. **Create a systemd unit** (`lynx-agent.service`) that runs the script
   as `lynx-agent`.
7. **Test** – run the unit, send a sample function call to the agent, and
   observe that it returns a response from the local proxy.
8. **Rollback** – if the agent crashes, the unit restarts automatically
   and the phone remains stable.

The plan keeps the kernel untouched and relies solely on user‑space
components, satisfying the *no flashing* requirement.

## 8. Verification Points

* **Local inference** – `curl http://127.0.0.1:8080/v1/responses` returns
  a JSON object with a `status: "completed"` field.
* **Remote fallback** – intentionally block the proxy and send the same
  request; the agent should return the same answer using the OpenAI API.
* **Tool registry** – adding `lynx/tools/new_tool.json` should automatically
  be available via the agent without modifying the agent code.
* **Codex CLI** – run `codex-cli --help` from the agent environment.

All these tests can be scripted in `tests/test_agent.py` and will be
executed as part of the normal `python3 -m unittest discover -s projects/lynx_gain`.

---

### References

* `docs/NEXUS-INFERENCE.md`
* `lynx/linux-port/docs/LYNX-KERNEL-TO-AGENT-GATE.md`
* `lynx/linux-port/docs/LYNX-NOOB-RUNTIME.md`
* `lynx/tools/lynx_noob_runtime.py`
* `lynx/tools/*.json`
* `codex` release for `aarch64-unknown-linux-musl`

---

This architecture is a *proposal*; the actual implementation will follow the
staged plan and be verified by the tests supplied above.

