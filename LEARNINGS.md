# Learnings

Running notes on non-obvious design decisions and Python/tooling concepts encountered while building this project.

## Money as integer cents, never float

Floats use IEEE 754 binary floating point, which can't exactly represent most base-10 decimal fractions (`0.1 + 0.2 != 0.3`). Errors are tiny individually but compound across many summed transactions, and can break exact-equality checks (e.g. reconciling parsed transactions against a statement's running balance).

Fix: never let an amount touch `float` at any point in the pipeline. Convert straight from the raw string to `decimal.Decimal` (constructed from the string, not from a float — `Decimal("19.99")`, not `Decimal(19.99)`), multiply by 100, then `int()`. This is why APIs like Stripe's represent money as plain integers.

## `ABC` / `abstractmethod`

`ABC` (from the `abc` module) enforces an interface contract at runtime, not just by convention. `StatementParser` has no real parsing logic of its own — there's no generic algorithm that reads every bank's PDF layout — so it's deliberately incomplete. Without `ABC`, that incompleteness would only surface later: someone could instantiate `StatementParser` directly, or write a subclass that forgets to implement `parse`, and the bug wouldn't show up until something actually called `.parse()`. With `ABC` + `@abstractmethod`, Python raises `TypeError` at the moment you try to instantiate an incomplete subclass, catching the mistake immediately instead of downstream.

## `__init__.py`

Makes a directory a proper Python package so dotted imports (`expense_analyser.parsers.base`) resolve reliably. Python does support "implicit namespace packages" (folders without `__init__.py` sometimes still import), but they're inconsistent across tooling. We hit exactly this class of bug once already: pytest couldn't resolve `expense_analyser` until the project root was explicitly added via `pyproject.toml`'s `pythonpath` setting. Keeping every package explicit avoids repeating that.

## The parser registry pattern

`PARSER_REGISTRY` (in `parsers/registry.py`) maps an `account_id` string to the `StatementParser` subclass that knows how to read that account's PDF layout. Without it, the ingestion pipeline would need a growing `if/elif` chain — one branch per bank — meaning every new account requires editing shared ingestion code. With the registry, adding a new bank means: write one new `StatementParser` subclass, add one line to the dict. The ingestion pipeline itself never changes.

## Idempotent inserts via `INSERT OR IGNORE` + `UNIQUE`

Re-running ingestion on overlapping statements is expected (new PDFs added to an already-ingested folder, etc.). Rather than querying "does this transaction already exist" before every insert (racy, extra round-trip), a `UNIQUE` constraint on a `dedup_hash` column lets `INSERT OR IGNORE` handle it in one statement — SQLite silently skips rows that would violate the constraint.