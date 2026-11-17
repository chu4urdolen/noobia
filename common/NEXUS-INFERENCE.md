# Nexus GPU inference

Verified on 2026-11-04 after upgrading Nexus to Ubuntu 26.04.1 LTS.

## Display and GPU

- The TCL TV is connected to the AMD Cezanne integrated GPU (`0000:30:00.0`, DRM `card2-HDMI-A-2`). GNOME uses `HDMI-2` at 1920×1080/60 Hz with underscanning enabled. The previous monitor configuration is backed up at `/home/aria/.config/monitors.xml.before-underscan-20261103`.
- The ASUS RTX 5090 is `0000:10:00.0`. Ubuntu's `nvidia-driver-595-open` version 595.99.02 and its Canonical-signed module for kernel 7.0.0-42 are installed. Secure Boot remains enabled. `nvidia-smi` reports 32607 MiB of VRAM and display inactive.
- The GPU was physically installed by Noob. Software checks cannot verify the PSU model or cabling.

## Local model and runtime

- Model: `/home/aria/models/gpt-oss-20b/gpt-oss-20b-MXFP4.gguf`, from `ggml-org/gpt-oss-20b-GGUF` on Hugging Face. It is a GGUF conversion of OpenAI's gpt-oss-20b. Size: 12,109,566,624 bytes. SHA-256: `27cd6c432c7672cb812a92f611cf3ba7bbc35928262bb1e1253ff4ee6ae35901`, matching the repository's LFS SHA-256.
- llama.cpp: official release `b12078`, CUDA 12.8 build and runtime under `/home/aria/apps/llama.cpp-b12078/cuda/`. The local launcher is `/home/aria/apps/llama.cpp-b12078/llama-cli-cuda`. Both CUDA archives matched their GitHub release SHA-256 digests.
- The resumable model download unit is `noobia-gpt-oss-20b-download.service`. It is disabled after successful completion. Download log: `/home/aria/models/gpt-oss-20b/download.log`.

## Run and verify

```sh
/home/aria/apps/llama.cpp-b12078/llama-cli-cuda --list-devices
/home/aria/apps/llama.cpp-b12078/llama-cli-cuda \
  -m /home/aria/models/gpt-oss-20b/gpt-oss-20b-MXFP4.gguf \
  -dev CUDA0 -ngl 99 -c 4096 --single-turn \
  -p 'In one sentence, what is 2 + 2?'
```

The 2026-11-04 test returned “2 + 2 equals 4.” with a 0 exit status. `llama-bench` reported CUDA on `CUDA0`, 99 GPU layers, 6685.68 tokens/s for `pp128` and 377.88 tokens/s for `tg64` (one repetition each). Test logs are `/home/aria/models/gpt-oss-20b/gpu-smoke-test.log` and `gpu-bench.log`. These are short smoke tests, not sustained performance or thermal validation.

## Inference service

Ollama is the single live model runtime for Dushich and LAN clients. It loads
`gpt-oss:20b` on CUDA0 with a 131,072-token context. The lightweight
`noobia-inference-proxy.service` warms that model at boot and exposes the
authenticated OpenAI-compatible API at `http://192.168.100.106:8080/v1` on
the Noobia LAN; `http://127.0.0.1:8080/v1` works on Nexus. The proxy maps the
old public model name `gpt-oss-20b` to Ollama's `gpt-oss:20b`. It does not bind
to the cellular fallback address or expose Ollama's management API. The old
`noobia-llama-server.service` is disabled; its launcher remains available as a
rollback path.

The API requires a key stored at `/home/aria/.config/noobia/gpt-oss-20b.api-key` (mode `0600`, outside the repository). Keep that key private when configuring another client. `/health` is public; authenticated clients can use `/v1/models` and `/v1/chat/completions`. The LAN endpoint uses HTTP, so use an SSH tunnel for access from outside the Noobia LAN.

The service source files are `aria/inference/ollama-proxy.py` and
`aria/inference/noobia-inference-proxy.service`; `aria/inference/run-server`
and `aria/inference/noobia-llama-server.service` record the previous direct
llama.cpp setup. The example client is `aria/inference/chat.py`. On Nexus:

```sh
/noobia/aria/inference/chat.py
/noobia/aria/inference/chat.py --prompt 'Say hello to Noobia.'
sudo systemctl status noobia-inference-proxy.service ollama.service
```

On 2026-11-06, the single 131K Ollama runner used about 15.5 GiB of the RTX
5090's 32 GiB, leaving about 16.5 GiB free, with 100% GPU placement. Requests
from Dushich and LAN clients share one runner and queue when it is busy. The
context setting matches the model's native maximum; this is an allocation and
short-response check, not a sustained long-prompt or thermal test.

From another machine, copy the example client and API key through a trusted channel, then set `NOOBIA_INFERENCE_API_KEY` or pass `--key-file`, and add `--url http://192.168.100.106:8080`. The client keeps conversation history in memory and supports `/reset` and `/quit`.

The 2026-11-06 proxy test returned HTTP 200 from `/health` on localhost and the
LAN address, rejected unauthenticated `/v1/models` with HTTP 401, rejected the
Ollama management path `/api/tags` with HTTP 404, and completed a chat request
with the existing client and API key.

See `/home/aria/apps/llama.cpp-b12078/NEXUS-INFERENCE-SETUP.md` for installation history and recovery paths.
