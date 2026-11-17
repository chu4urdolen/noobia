# Dushich agent tools

`duplicate_filenames.py` reports duplicate **filenames** (basenames), regardless
of file content. It scans regular files, skips Git metadata and symlinked
directories, records access errors, and writes a complete sorted JSON report
to `/noobia/dushich/private/duplicate-reports/`.

```sh
/noobia/dushich/tools/duplicate_filenames.py start /noobia
/noobia/dushich/tools/duplicate_filenames.py status JOB_ID
/noobia/dushich/tools/duplicate_filenames.py result JOB_ID
```

`start` returns immediately with a job ID. `status` and `result` return bounded
text; the full report remains in the private JSON file named by `result`.
Use `--dir STATE_DIR` with each command to put reports elsewhere. Run
`python3 -m unittest discover -s /noobia/dushich/tools -p 'test_duplicate_filenames.py' -q`
to check the tool.

Check the report's error count. For a complete scan of root-owned backup
directories, run `start` and subsequent status/result commands with
`sudo -n` and an explicitly chosen private state directory. The command
remains nonblocking; elevated access changes which filenames it can see.
