# Argus historian jobs

`tools/argus_jobs.py` is a private SQLite queue for named historian tasks on Argus's Pi. Its database is `/noobia/argus/data/jobs.sqlite3` on the NVMe root. Allowed kinds are `archive-import` and `ledger-day` (which requires `--date`). Each runs one fixed `argus_history.py` command with a 120-second bound. The queue does not accept arbitrary commands or prompts.

```sh
python3 /noobia/argus/tools/argus_jobs.py enqueue archive-import --request-key example-20261126
python3 /noobia/argus/tools/argus_jobs.py enqueue ledger-day --date 2026-11-26
python3 /noobia/argus/tools/argus_jobs.py job-status JOB_ID
python3 /noobia/argus/tools/argus_jobs.py job-result JOB_ID
python3 /noobia/argus/tools/argus_jobs.py health
```

The service `argus-historian-worker.service` claims one job at a time in enqueue order, records bounded results, and waits quietly when idle. Repeating an enqueue with the same request key returns the original job ID and state. If the worker dies during a job, its next start marks that job failed with an interruption reason; it never silently reruns the task. An operator can enqueue a new request key after inspecting the outcome. Archive import and ledger construction are idempotent at the evidence layer.

The unit runs as `argus`, with `NoNewPrivileges=true`, `ProtectSystem=strict`, and write access only to `/noobia/argus/data`. It has bounded service restart attempts; it does not reboot or power off the Pi. Its source is `services/argus-historian-worker.service`. On 2026-11-26 it was installed, started, enabled, and verified active. Real queued imports and ledgers completed. The live queue was migrated from schema 1 to 2 without losing earlier jobs.

Disable switch: `sudo -n systemctl disable --now argus-historian-worker.service`. To run one queued job manually while the service is stopped, use `python3 /noobia/argus/tools/argus_jobs.py run-once`. Keep the SQLite database for audit and recovery. There is no automatic collection schedule; the Nexus MCP route triggers on-demand work through pinned SSH.
