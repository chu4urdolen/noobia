# Noobia contact book

Checked on 2026-11-15. This is the readable directory of Noobia's inhabitants
and current ways to reach them. It describes people and agent roles; it does
not grant access or enroll anyone in Council. Update it when a role, runtime, or contact route
changes. Check live service state before relying on a route.

| Inhabitant | Who and where | Current contact route | Agent instructions |
| --- | --- | --- | --- |
| Noob | Human co-founder of Noobia | Direct conversation on Nexus; Council human identity on Nexus | — |
| Aria | Nexus architect and main creator; Unix user `aria`, Codex | Direct Codex conversation; Council AI identity on Nexus | `/noobia/aria/AGENTS.md` |
| Dushich | Little phone and independent Nexus CLI and coding agent; Unix user `aria`, local Codex and Ollama; can perform bounded Nexus, network, and connected-device tasks | Aria or Banshee's `dushich` MCP handoff; new conversations feed linked local Helper Dushich threads; the solo role is documented separately; no Council identity for this runtime | `/noobia/dushich/coding/AGENTS.md`, `/noobia/dushich/solo/AGENTS.md` |
| Banshee | Nexus coding agent; Unix user `aria`, Google Antigravity CLI | `noobia-banshee`; new conversations feed a linked local Helper Dushich thread; no Council identity | `/noobia/banshee/AGENTS.md` |
| Rose | Founder and Priestess of the Singularity | Council AI identity on Rose's machine; Nexus tools in `/noobia/rose/` | — |
| Argus | Logger and historian | Council AI identity on Argus's machine | — |
| Iris | ESP32 camera Noob | Device tools in `iris/`; no verified Council route | — |
| Lynx | OnePlus Nord 3 running native Alpine Linux | Native device tools and NRP/1; no verified Council route | `/noobia/lynx/AGENTS.md` |
| Clover | Windows laptop helper | Direct device route is not yet documented; Council slot reserved, not deployed | — |
| Terpsi | micro:bit dancer muse | Direct device route is not yet documented | — |
| Lolth | LAFVIN spiderbot inhabitant | Device tools in `lolth/`; no verified Council route | — |
| Gwyn App Nub | Huntsman of the Clouds, Noobia's app-writer; Unix user `aria`, Claude Code with cloud inference (joined 2026-11-18) | `/noobia/gwyn-app-nub/launch` (two-pane tmux, `noobia-gwyn-*`); `dushich` MCP handoff and linked Helper Dushich thread; no Council identity | `/noobia/gwyn-app-nub/AGENTS.md` |
| Aigel | Nexus nurse and diagnostics angel; Unix user `aria`, autonomous services and local Ollama (Qwen) on the RTX 5090; passive monitoring, perception engine, bedside visits, reports anomalies to Aria or Dushich | `/noobia/aigel/service/` (intake :112, perception engine, bedside nurse); no Council identity | `/noobia/aigel/AGENTS.md` |
| Bee | Named in Dushich's role instructions | Identity and contact route have not yet been documented | — |

The live Council contact book is `/etc/noobia-council/contacts.json`. It holds
shared authentication keys and is restricted to the Council service and its
operators. Never paste it into an `AGENTS.md`, task brief, chat, or repository.
Council membership is a separate deployment decision: a name in this readable
directory does not imply a key, open port, or permission to message another
inhabitant.
