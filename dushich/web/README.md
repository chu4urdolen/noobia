# Dushich conversation monitor

The local page is disabled by default. The terminal CLIs are the primary agent
interfaces: `noobia-codex`, `noobia-banshee`, and
`/noobia/dushich/solo/launch`.

If the page is started manually with
`python3 /noobia/dushich/web/server.py`, it binds only to
`http://127.0.0.1:8765/`. The front page shows recorded Foreman activity,
project assignments, and pending human-help flags. **Current status** shows the
visible conversation timelines for Aria, Banshee, and Solo Dushich, with a
selector for existing conversations. Dushich's visible helper replies appear
alongside the coding agent's output when a handoff exists.

The page is read-only. It has no message composer, no **New conversation**
choice, and all HTTP POST requests return 405. Start and continue conversations
through the terminal CLIs. Project selection and Foreman operation also take
place outside this page.

The old user service file remains at `noobia-dushich-web.service`, but its
systemd user startup link was removed on 2026-11-17. The service uses
`KillMode=process` so stopping the HTTP server does not stop a terminal agent
that it previously launched.

Conversation histories remain in each agent's native store. The Banshee
adapter reads the Antigravity CLI SQLite format observed on Nexus; if that
format changes, unknown messages are omitted from the display. The monitor
shows visible messages and selected Dushich results, not private reasoning.
