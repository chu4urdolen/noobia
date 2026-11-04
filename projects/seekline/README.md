# seekline

A minimal, standard‑library‑only command‑line tool that searches UTF‑8 text files for a regular expression pattern.

## Usage

```bash
$ python3 seekline.py PATTERN FILE [FILE ...]
```

### Options

| Flag | Description |
|------|-------------|
| `--ignore-case` | Perform a case‑insensitive search. |
| `--json` | Output results as a JSON array. |

### Output

* **Default** – `path:line_number:line_text` per match, one per line.
* **JSON** – a single JSON array containing objects:
```json
[{"path":"file.txt","line_number":3,"text":"the matched line"}]
```

### Errors

* Invalid regex → non‑zero exit code, message on `stderr`.
* Missing file → non‑zero exit code, message on `stderr`.
* Empty pattern → non‑zero exit code, message on `stderr`.

```
