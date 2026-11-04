# Mini Ledger

This is a tiny command‑line utility that reads a CSV file containing rows of
```
name,amount
```
where *amount* is a decimal number, and prints a JSON object mapping each name to the exact total of its amounts.

## Usage

```bash
python3 -m projects.mini_ledgers.ledger data.csv
```

The script prints the result to **stdout** and any errors to **stderr**.

## Examples

```csv
Alice,10.5
Bob,5
Alice,4.5
```

Running the command above will output:

```json
{"Alice": "15.0", "Bob": "5"}
```

The tool validates that each line has exactly two columns, that the name is not empty, and that the amount is a finite decimal value (no `NaN` or `Infinity`).

## Tests

Run the bundled tests with:

```bash
python3 -m unittest discover -s projects/mini_ledgers/tests
```

