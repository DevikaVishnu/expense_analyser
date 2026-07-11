# Expense Analyser

A personal finance tracker and analyser that ingests bank/credit-card statement PDFs, parses them into a normalized transaction history, and supports categorizing and analyzing spending — without handing your financial data to a third-party SaaS.

## Why this exists

Most personal finance tools (Mint, Copilot, Monarch) require linking your bank credentials to a third-party company. This project is designed to be **self-hosted**: your statements and data stay on infrastructure you control. It's also deliberately built to be **generic** — not hardcoded to one bank — since statement layouts vary wildly between accounts, cards, and providers.

## Architecture

```
PDF statement  --(parser)-->  Transaction  --(repository)-->  SQLite
```

- **`expense_analyser/models.py`** — `Transaction`, the canonical schema every statement format gets normalized into. Amounts are stored as integer cents (never float — see `LEARNINGS.md`) to avoid rounding errors.
- **`expense_analyser/parsers/base.py`** — `StatementParser`, an abstract base class. Each bank/card/document-format gets its own subclass that knows how to turn its specific PDF layout into a list of `Transaction`s. Nothing else in the system needs to know how any individual format is laid out.
- **`expense_analyser/parsers/registry.py`** — `PARSER_REGISTRY`, mapping a folder-path key (e.g. `"IslandFederal_checking/bank_statment"`) to the parser class that understands it. Adding a new source means writing one new parser class and one registry entry — no other code changes.
- **`expense_analyser/storage.py`** — `TransactionRepository`, a thin wrapper around SQLite. Inserts are idempotent (`INSERT OR IGNORE` + a `UNIQUE` constraint on a content hash), so re-ingesting overlapping statements is safe.

### Folder convention for statements

```
expense_reports/<account_id>/<document_type>/*.pdf
```

e.g. `expense_reports/IslandFederal_checking/bank_statment/` and `expense_reports/IslandFederal_checking/transaction_history/` — one real bank account can have PDFs in more than one layout (e.g. an official mailed statement vs. a web transaction-history export), so `account_id` (which real account this money moved through) is kept separate from the parser routing key (which layout this specific file uses). All parsers for the same account still tag their output with the same `account_id`, so spending analysis groups correctly regardless of which document format a transaction came from.

`expense_reports/` is gitignored — real statement PDFs never get committed.

## Status

- [x] `Transaction` model
- [x] `StatementParser` interface + registry
- [x] SQLite storage layer with idempotent inserts
- [ ] Parsers for IslandFederal checking (bank statement + transaction history formats) — in progress
- [ ] Ingestion CLI
- [ ] Categorization CLI (with merchant-rule auto-suggestion)
- [ ] Spend analysis / reporting
- [ ] Self-hostable packaging (Docker Compose) + web UI for phone access

## Setup

```
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pytest
```