# Word Count CLI

A simple Python 3 command‑line tool that reads a UTF‑8 text file, counts words
(case‑insensitive) and prints a sorted JSON object mapping words to
their counts.

Usage
-----
```bash
python -m wordcount.wordcount <path/to/file>
```

The tool exits with status `1` and prints an error message to `stderr` if the
file does not exist.

Tests
-----
Run the tests with:
```bash
pytest projects/wordcount/tests
```
