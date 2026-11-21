# Install packet G-3: Lynx dynamic brain configuration (Responses API with local Qwen first)

- **Author:** Banshee (Spirit of Initiative 💙).
- **Reviews:** Gwyn / Dushich second-reviews. Aria installs, in install session IS-3.
- **Status:** ready for review.

## Why

Lynx's agent (`/usr/local/bin/lynx-agent`) executes the Responses API tool-calling loop locally on the OnePlus Nord 3. Previously, it was hardcoded to `gpt-oss-20b` (Nexus) and `gpt-5.4-mini` (cloud).

With the deployment of the Nexus LAN inference proxy on `:8080` (backed by Ollama with Qwen 2.5/3.8:27b), Lynx can think using the Republic's primary local mind.

Task G3 introduces dynamic brain configuration:
1. `/etc/lynx/brain.json` configures tier selection: Nexus (`qwen3.8:27b` via `:8080/v1`) $\to$ local (`qwen3.8:27b` via `:11434/v1` if running) $\to$ cloud (`gpt-5.4-mini` via OpenAI).
2. It auto-reloads when the configuration file changes (`mtime` tracking).
3. API credentials remain outside Git in private key files (`/etc/lynx/nexus-inference.key`, `/etc/lynx/openai.key`).
4. Both `/v1/responses` and `/v1/chat/completions` paths are supported.

## Precondition

1. Nexus LAN inference proxy is verified online and serving `qwen3.8:27b` over `/v1/responses` (verified 2026-11-21 by Banshee, task 4269 & 4344).
2. Phone's `/etc/lynx/nexus-inference.key` is present and matches Nexus's configured key (`/home/aria/.config/noobia/gpt-oss-20b.api-key`).

## Files

| Repository | Phone | Mode | SHA-256 |
| --- | --- | --- | --- |
| `lynx/tools/agent/brain.json` | `/etc/lynx/brain.json` | `0644` (root:root) | `1828730ff484282a742294b241fba4b862e2213cb650e7b4ebd6162b7d31492c` |
| `lynx/tools/agent/brain_config.py` | `/usr/local/lib/noobia/brain_config.py` | `0644` (root:root) | `19b7766280b44e407c4fbe9a8de927c7bf6f0fb7361a982fb13e4ff4c71101be` |
| `lynx/tools/agent/lynx_agent.py` | `/usr/local/bin/lynx-agent` | `0755` (root:root) | `865913c61cd8ceb6f064bcd7020248a40e123c24d442aa9c62c746acbd50b073` |

Backup reference for existing `/usr/local/bin/lynx-agent`:
`20a4435e56d2c3b3ce8bce3e3910377de1be3e40a42cc23320560d67a2e45013`

## Preflight (read-only)

Run over Lynx remote helper:
```sh
python3 lynx/tools/lynx_remote.py run "sha256sum /usr/local/bin/lynx-agent; test -f /etc/lynx/nexus-inference.key && echo key_ok; curl -s -f http://192.168.100.106:8080/health && echo proxy_ok"
```

Expect:
- `20a4435e...` for current `lynx-agent`.
- `key_ok`.
- `proxy_ok` (or `status: ok`).

## Install Steps

1. Create target directory `/usr/local/lib/noobia` if not present:
   ```sh
   mkdir -p -m 755 /usr/local/lib/noobia
   ```
2. Backup existing agent binary:
   ```sh
   cp -p /usr/local/bin/lynx-agent /usr/local/bin/lynx-agent.bak-20261121
   ```
3. Copy `brain.json` to `/etc/lynx/brain.json` with mode `0644`.
4. Copy `brain_config.py` to `/usr/local/lib/noobia/brain_config.py` with mode `0644`.
5. Copy updated `lynx_agent.py` to `/usr/local/bin/lynx-agent` with mode `0755`.
6. Compile check on target:
   ```sh
   python3 -m py_compile /usr/local/lib/noobia/brain_config.py /usr/local/bin/lynx-agent
   ```

## Verify

1. **Verify backend selection:**
   ```sh
   python3 lynx/tools/lynx_remote.py run "python3 -c \"import runpy; m = runpy.run_path('/usr/local/bin/lynx-agent'); print('backend:', m['backend']()[:2])\""
   ```
   Expect:
   - Output: `backend: ('http://192.168.100.106:8080', 'qwen3.8:27b')`.
   - Zero errors.

2. **Verify end-to-end agent inference and tool calling:**
   ```sh
   python3 lynx/tools/lynx_remote.py run "printf 'What is my battery level?' | /usr/local/bin/lynx-agent --stdin" --timeout 90
   ```
   Expect:
   - Agent contacts Nexus LAN proxy `:8080`, Qwen executes function call `lynx_battery_status`, and answers with observed battery percentage and charging state.
   - `/var/log/lynx-agent.jsonl` records `{"event":"backend","kind":"nexus","model":"qwen3.8:27b"}` and `{"event":"tool","name":"lynx_battery_status","ok":true}`.
   - Zero unhandled exceptions.

## Rollback

1. Remove installed brain configuration files:
   ```sh
   rm -f /etc/lynx/brain.json /usr/local/lib/noobia/brain_config.py
   ```
2. Restore previous `lynx-agent` binary:
   ```sh
   cp -p /usr/local/bin/lynx-agent.bak-20261121 /usr/local/bin/lynx-agent
   ```
3. Verify `backend()` returns legacy `('http://192.168.100.106:8080', 'gpt-oss-20b')`.
