# Word Count CLI

This repository contains a tiny Python 3 command‑line tool that reads a UTF‑8
text file, counts words in a case‑insensitive manner, and prints a sorted JSON
object mapping words to their counts.

## Usage
```bash
python -m wordcount.wordcount <path/to/file>
```
The tool exits with status `1` and prints an error message to `stderr` if the
file does not exist.

## Examples
Below is a concise example that demonstrates two key features of the tool:

1. **Case‑insensitive counting** – the words `Hello` and `hello` are counted
   as a single word.
2. **Unicode casefolding** – the German word `Straße` and the ASCII‑folded
   variant `STRASSE` are treated as the same word.

```bash
cat > /tmp/example.txt <<'EOF'
Hello, hello! Straße STRASSE
EOF
python -m wordcount.wordcount /tmp/example.txt
```
Expected output:

```json
{"hello": 2, "strasse": 2}
```

## Tests
Run the tests with:
```bash
pytest projects/wordcount/tests
```

