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
- **`expense_analyser/parsers/registry.py`** — `PARSER_REGISTRY`, mapping a folder-path key (e.g. `"IslandFederal_checking/bank_statement"`) to the parser class that understands it. Adding a new source means writing one new parser class and one registry entry — no other code changes.
- **`expense_analyser/storage.py`** — `TransactionRepository`, a thin wrapper around SQLite. Inserts are idempotent (`INSERT OR IGNORE` + a `UNIQUE` constraint on a content hash), so re-ingesting overlapping statements is safe.
- **`expense_analyser/ingest.py`** — the ingestion CLI. Walks `expense_reports/`, looks up the right parser per folder via `PARSER_REGISTRY`, and stores the results. Folders with no matching registry entry are skipped with a warning rather than crashing the run.
- **`expense_analyser/categorization.py`** — the categorization CLI. Genuine deposits and known merchants are auto-labeled without prompting (a merchant rule, once set, applies itself to every future transaction from that merchant — including refunds, which share the original purchase's description); only genuinely new merchants stop and ask. `recategorize()` bulk-fixes an already-categorized merchant by search term; `review_month()`/`review_category()` show a given month's or category's total and every transaction in it, letting you selectively fix any of their categories — `review_category` is the tool for "this category's report total looks wrong, what's actually in it?", since a merchant-key collision (two different real-world merchants sharing the same normalized key) can silently lump an unrelated transaction into the wrong category.
- **`expense_analyser/reporting.py`** — spend-by-category, spend-by-month, and spend-by-month-and-category reports, printed to the terminal and exported to `reports/` as CSV. Amounts are summed net of refunds within each category/month.
- **`expense_analyser/formatting.py`** — `format_amount`, the shared "signed integer cents -> human-readable dollar string" helper used by both `categorization.py` and `reporting.py`.

### Folder convention for statements

```
expense_reports/<account_id>/<document_type>/*.pdf
```

e.g. `expense_reports/IslandFederal_checking/bank_statement/` and `expense_reports/IslandFederal_checking/transaction_history/` — one real bank account can have PDFs in more than one layout (e.g. an official mailed statement vs. a web transaction-history export), so `account_id` (which real account this money moved through) is kept separate from the parser routing key (which layout this specific file uses). All parsers for the same account still tag their output with the same `account_id`, so spending analysis groups correctly regardless of which document format a transaction came from.

`expense_reports/` is gitignored — real statement PDFs never get committed. The SQLite database file (`*.db`) is gitignored too, since it holds your real parsed transaction data.

## Status

- [x] `Transaction` model
- [x] `StatementParser` interface + registry
- [x] SQLite storage layer with idempotent inserts
- [x] `IslandFederalStatementParser` (official bank statement format)
- [ ] Parser for IslandFederal checking transaction-history export format
- [x] Ingestion CLI
- [x] Categorization CLI (with merchant-rule auto-suggestion)
- [x] Spend analysis / reporting
- [ ] Self-hostable packaging (Docker Compose) + web UI for phone access

## Setup

```
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pytest
```

## Usage

Ingest all statement PDFs under `expense_reports/` into the database:

```
python3 -m expense_analyser.ingest
```

By default this reads from `expense_reports/` and writes to `expenses.db` in the project root. Both are configurable:

```
python3 -m expense_analyser.ingest --expense-reports-dir path/to/statements --db-path path/to/expenses.db
```

Then categorize whatever's uncategorized:

```
python3 -m expense_analyser.categorization
```

Deposits and refunds are handled automatically (see `categorization.py` above); you're only asked about a transaction the first time its merchant shows up — after that, every future transaction from that merchant is auto-applied and just logged, not re-asked. If a merchant rule was ever set wrong, fix every affected transaction at once:

```
python3 -m expense_analyser.categorization --recategorize "search term"
```

To see a given month's total spend and every individual transaction in it (and fix any of their categories on the spot):

```
python3 -m expense_analyser.categorization --review-month 2026-01
```

To track down why a category's report total looks wrong — shows every transaction currently in it and lets you move outliers elsewhere:

```
python3 -m expense_analyser.categorization --review-category "Bank of America Expenses"
```

Finally, generate reports:

```
python3 -m expense_analyser.reporting
```

Prints spend-by-category, spend-by-month, and a spend-by-month-and-category breakdown to the terminal, and writes matching CSVs to `reports/` (both `--db-path` and `--reports-dir` are overridable, same pattern as above).