# LNX-47 Reflex inference priority: measurements and options

*Gwyn, 2026-11-25, for Tom and Aria (the GPU and Ollama are Aria's). Rose's backlog, LNX-47.*

## Measured

**Lynx's reaction time**: from the call to her brain to her first tool (speech, buzz, light),
over her last 206 reactions (`/var/log/lynx-agent.jsonl`), after the one-call change of 2026-11-24:

| median | 25 % | 75 % | 90 % | max | < 10 s | 10-30 s | 30-60 s | > 60 s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **17.2 s** | 10.3 s | 33.7 s | **54.1 s** | 97.9 s | 51 | 86 | 53 | 16 |

**Qwen's own work per reaction is 0.1-0.8 s** (Ollama eval counters, 2026-11-24). The rest
is waiting: Ollama serves one request at a time, in arrival order, and cannot interrupt a
running request.

**Who keeps Qwen busy** (`ss -tnp`, sampled 2026-11-25):

| Caller | Route | What it is |
| --- | --- | --- |
| `codex --oss` (Dushich) | `:11434` direct | coding and review sessions; prompts up to ~41k tokens |
| `common/dushich/helper_mirror.py watch` | `:11434` direct | Helper Dushich's conversation mirror: Codex turns and summaries, in a constant loop. This is the "unknown `/api/chat` caller" of 2026-11-24 |
| `aria/inference/ollama-proxy.py` (:8080) | -> `:11434` | **Lynx's only route** (and the other remote clients) |

With one slot, the callers also evict each other's prompt cache, so each request re-reads its
whole prompt (3k-41k tokens).

## Options

| | Option | Expected effect for Lynx | Cost and risk | Owner |
| --- | --- | --- | --- | --- |
| A | **Cooperative gate**: the proxy marks "a reflex is in flight" (a timestamp file in `/dev/shm`); `helper_mirror`, `dushich-explore` and `dushich-summarizer` wait before starting a new request | removes the *queue* behind her, not the request already running: roughly 17 s -> 10 s median, the tail stays | small code in Aria's proxy and Dushich's mirror; no GPU change | Aria + Dushich |
| B | `OLLAMA_NUM_PARALLEL=2` | two requests at once | the KV cache for the 131k context doubles: likely does not fit in 32 GB next to the model; slower per request | Aria (GPU) |
| C | **A small reflex model for SENSE only** (e.g. a 3-4B instruction model, ~3 GB VRAM) loaded next to Qwen, with `OLLAMA_MAX_LOADED_MODELS=3`; CHAT stays on qwen3.8:27b | her own lane: reflexes in ~1-2 s whatever Dushich is doing | ~3 GB VRAM (the embedding model already shares the card); shorter, simpler reactions; AGENTS.md says no *large* model next to Qwen, and a small one needs Tom's and Aria's OK | Aria (GPU), Gwyn (agent switch) |
| D | On-device reflex model on Lynx (LNX-44) | independent of Nexus, works offline | CPU heat on the phone, slow tokens; a bigger project | Aria |
| E | Pause the helper mirror while Lynx is active (START) | the biggest background load is gone during her waking hours | Dushich's helpers lag while she is awake | Tom |

## Recommendation

**C, with A as the cheap first step.** A can land today and helps at once. C gives her
reflexes their own lane, which is what "reflex priority" really means. Lynx's side of C is
small: `/etc/lynx/brain.json` gets a `reflex` backend, and `lynx_agent` uses it for `SENSE:`
jobs only (CHAT keeps Qwen 27B). I will write that switch as soon as a model is chosen and
loaded.

Decision needed from Tom and Aria: **which option(s)**, and for C **which small model**.
