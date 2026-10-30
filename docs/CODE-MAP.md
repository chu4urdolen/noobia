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
| Rose | [Rose](noobs/ROSE.md) | `rose_tools/calls/`, `rose_tools/chatbot/`, camera and voice utilities |
| Argus | [Argus](noobs/ARGUS.md) | `argus/services/`, `argus/tools/`, `argus/web/` |
| Dushich | [Dushich](noobs/DUSHICH.md) | `dushich/`; check device inventory before assuming a runtime |
| Lolth | [Lolth](noobs/LOLTH.md) | `lolth/firmware/`, `lolth/tools/` |
| Clover and Terpsi | [Other inhabitants](noobs/OTHER.md) | Locate the actual device repository before changing hardware |

## Shared systems

| System | Start here | Purpose |
| --- | --- | --- |
| ESP common | [`esp/common/README.md`](../esp/common/README.md) | NRP/1 protocol, VM, sequence and thread classes, reusable services |
| Council | [`council/README.md`](../council/README.md) | Authenticated Noobian communication |
| Neo | [`neo/README.md`](../neo/README.md) | Local display and physical I/O services |
| Wisp | [`wisp/README.md`](../wisp/README.md) | Console and interaction reference |
| Aria workspace | `aria/README.md` (local) | Nexus-side local tools |

## Working rule

Keep each device's hardware backend local to its own directory. Expose verified
operations through its native Noob protocol and through small local tools for
an on-device agent. Shared protocol code belongs in `esp/common` or a clearly
named common module. An interface's existence is not evidence that the
hardware function works; record trial evidence on the device page.
