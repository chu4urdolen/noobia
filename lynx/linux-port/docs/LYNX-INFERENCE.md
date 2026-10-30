# Lynx inference path

The one-shot test uses the OpenAI Responses API from Lynx's native Alpine
userspace. `tools/lynx_inference_probe.py` sends one bounded prompt with
`store=false` and at most 64 output tokens, then returns a short text answer
and token counts. It reads the API credential from stdin and never writes it
to Lynx storage. `tools/trial_v50_openai_inference.py` obtains Rose's existing
API key from `~/.config/rose-chat/settings.json` on Syra over the pinned `rose`
SSH login, streams it to Lynx over the pinned SSH session, and saves only a
redacted result receipt. It stages the probe under `/run` and removes it
afterward. This is a test path, not Lynx's long-term credential design.

Lynx reached `api.openai.com` with working TLS and received the expected HTTP
401 for an unauthenticated `/v1/models` request. The local probe logic passed
an isolated request test. The first orchestration attempt stopped before any
API call because Syra at `192.168.100.7` was unreachable; receipt:
`logs/v50-openai-inference-1793304994313463601.json`. No credential was copied
or stored. Nexus's Syra power controller currently lacks its Tuya local key,
so the host cannot be powered remotely by that route.

After Syra is online, run `python3 tools/trial_v50_openai_inference.py` from
`/noobia/lynx`. A successful receipt proves a native phone HTTPS request and
response, but no autonomous agent or tool loop. The next design step is a
scoped credential broker or Lynx-specific API key, with local audit and a
revocable permission boundary. Do not copy Rose's general key permanently
onto the phone.

API behavior is based on the official [OpenAI text generation guide](https://developers.openai.com/api/docs/guides/text).
