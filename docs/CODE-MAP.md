# Noobia code map

This is the quick entry point for Noobia's local source tree. Device state can
change without a repository edit, so confirm a live device before acting on
hardware. Private keys, firmware archives, logs, and backups stay in their
existing local directories; this map points to code and operating notes.

## Inhabitants and machines

| Inhabitant or machine | Start here | Main code and controls |
| --- | --- | --- |
| Lynx, OnePlus Nord 3 | [Lynx](noobs/LYNX.md) | `lynx/tools/`, `lynx/linux-port/`, native Alpine, NRP/1, local display |
| Iris, ESP32 camera Noob | [Iris](noobs/IRIS.md) | `iris/firmware/iris_noob/`, `iris/tools/`, `iris/programs/` |
| Rose | [Rose](noobs/ROSE.md) | `rose/calls/`, `rose/chatbot/`, camera and voice utilities; `rose_tools/` is a compatibility link |
| Argus | [Argus](noobs/ARGUS.md) | `argus/services/`, `argus/tools/`, `argus/web/` |
| Dushich | [Dushich](noobs/DUSHICH.md) | `dushich/`, [local coding workshop](../dushich/coding/README.md), [solo terminal](../dushich/solo/README.md), and [disabled read-only web monitor](../dushich/web/README.md); check device inventory before assuming a runtime |
| Aigel (planned) | [Draft](../aigel/README.md) | Local Nexus nurse concept; scope and authority await Noob's plan |
| Banshee | [Banshee](../banshee/README.md) | `banshee/workspace/`, Google Antigravity CLI coding workspace on Nexus |
| Gwyn App Nub | [Gwyn](../gwyn-app-nub/README.md) | `gwyn-app-nub/workspace/`, Claude Code workspace and isolated configuration; authentication pending |
| Lolth | [Lolth](noobs/LOLTH.md) | `lolth/firmware/`, `lolth/tools/` |
| Clover and Terpsi | [Other inhabitants](noobs/OTHER.md) | Locate the actual device repository before changing hardware |

## Shared systems

| System | Start here | Purpose |
| --- | --- | --- |
| ESP common | [`esp/common/README.md`](../esp/common/README.md) | NRP/1 protocol, VM, sequence and thread classes, reusable services |
| Council | [`council/README.md`](../council/README.md) | Authenticated Noobian communication |
| Neo | [`neo/README.md`](../neo/README.md) | Local display and physical I/O services |
| Wisp | [`wisp/README.md`](../wisp/README.md) | Console and interaction reference |
| Aria workspace | [Aria tools](../aria/README.md) | Nexus-side local tools, including the [two-pane Codex launcher](../aria/codex-with-dushich), [Dushich handoffs](../aria/dushich-bridge), and the new-conversation Helper Dushich mirror |
| Shared references | [Common](../common/README.md) | Contact book, Nexus inference notes, and pointers to shared services |
| Nexus GPU inference | [Nexus inference](../common/NEXUS-INFERENCE.md) | AMD TV output, RTX 5090 CUDA runtime, LAN inference service and chat client |
| Contact book | [Noobia contact book](../common/CONTACT-BOOK.md) | Readable inhabitant roles and routes; Council authentication keys remain separate |

Nexus coding agents Aria, Banshee, and Dushich now share the `aria` Unix login.
Their separate identities, instructions, workspaces, and conversation histories
remain under their own `/noobia` directories. Former `banshee` and `dushich`
home directories are preserved as private archives in those directories.
Their terminal CLIs are the primary contact routes: `noobia-codex` for Aria,
`noobia-banshee` (`/noobia/banshee/launch`) for Banshee, and `/noobia/dushich/solo/launch` for
Solo Dushich. The Dushich web monitor is disabled by default and read-only;
do not build new agent chat routing around it.

## Working rule

Keep each device's hardware backend local to its own directory. Expose verified
operations through its native Noob protocol and through small local tools for
an on-device agent. Shared protocol code belongs in `esp/common` or a clearly
named common module. An interface's existence is not evidence that the
hardware function works; record trial evidence on the device page.
