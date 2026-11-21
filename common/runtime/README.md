# Local runtimes

Third-party software that Noobia's own tools run on. It is all built here,
inside `/noobia`, from recipes kept in Git. The built files themselves stay
out of Git: the Codex binary alone is 281 MB, over GitHub's 100 MB limit, and
a Python virtual environment only works at the path where it was built.

| Folder (built, ignored) | Recipe (in Git) | Used by |
| --- | --- | --- |
| `codex/node_modules/` | [`codex/package.json`](codex/package.json), [`package-lock.json`](codex/package-lock.json) (Codex CLI 0.169.0) | Dushich (helper, solo, task runner) and Aigel, both on local Ollama |
| `forge-venv/` | [`forge-requirements.txt`](forge-requirements.txt) (fastembed, numpy, onnxruntime) | `forge-db` meaning search and `nexus_detect` CPU object detection |
| `models/` | downloaded on first use / pinned in `install.sh` | `forge-db`: `bge-small-en-v1.5` (65 MB); `nexus_detect`: `yolov8n.onnx` (12 MB, Ultralytics YOLOv8n, AGPL-3.0) |
| `web-venv/` | [`web-requirements.txt`](web-requirements.txt) (Playwright) | Checking apps and pages in a headless browser |
| `playwright/` | `playwright install chromium` | Playwright's Chromium (`PLAYWRIGHT_BROWSERS_PATH`) |

Build or rebuild everything, or one part:

```sh
common/runtime/install.sh              # all
common/runtime/install.sh codex        # or forge, or detect, or web
```

To upgrade Dushich's Codex, change the version in `codex/package.json`, run
`npm install --prefix common/runtime/codex` to refresh the lock file, test
Dushich, and commit both files.

Software that lives outside `/noobia` on purpose: the operating system and its
packages (`apt`), the Ollama service and its models, and the cloud agents' own
CLIs (Codex, Antigravity, Claude Code), which their vendors' installers keep
up to date (see `common/tools/update_agents.sh`), and `uv` in `~/.local/bin`,
which `install.sh` uses to build the Python environments.
