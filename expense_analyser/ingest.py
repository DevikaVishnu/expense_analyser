import argparse
from pathlib import Path

from expense_analyser.parsers.base import StatementParser
from expense_analyser.parsers.registry import PARSER_REGISTRY
from expense_analyser.storage import TransactionRepository

DEFAULT_DB_PATH = "expenses.db"
DEFAULT_EXPENSE_REPORTS_DIR = "expense_reports"


def ingest_all(
    expense_reports_dir: Path,
    repo: TransactionRepository,
    registry: dict[str, type[StatementParser]] = PARSER_REGISTRY,
) -> None:
    for account_dir in sorted(expense_reports_dir.iterdir()):
        if not account_dir.is_dir():
            continue

        for doctype_dir in sorted(account_dir.iterdir()):
            if not doctype_dir.is_dir():
                continue

            registry_key = f"{account_dir.name}/{doctype_dir.name}"
            parser_cls = registry.get(registry_key)

            if parser_cls is None:
                print(f"Warning: no parser registered for {registry_key!r}, skipping")
                continue

            parser = parser_cls()

            for pdf_path in sorted(doctype_dir.iterdir()):
                if pdf_path.suffix.lower() != ".pdf":
                    continue

                transactions = parser.parse(pdf_path)
                new_count = sum(1 for txn in transactions if repo.insert(txn))
                print(f"{pdf_path.name}: {len(transactions)} parsed, {new_count} new")


def main() -> None:
    arg_parser = argparse.ArgumentParser(
        description="Ingest bank/card statement PDFs into the transaction database."
    )
    arg_parser.add_argument(
        "--db-path",
        default=DEFAULT_DB_PATH,
        help=f"Path to the SQLite database file (default: {DEFAULT_DB_PATH})",
    )
    arg_parser.add_argument(
        "--expense-reports-dir",
        default=DEFAULT_EXPENSE_REPORTS_DIR,
        help=f"Path to the folder containing statement PDFs (default: {DEFAULT_EXPENSE_REPORTS_DIR})",
    )
    args = arg_parser.parse_args()

    repo = TransactionRepository(args.db_path)
    ingest_all(Path(args.expense_reports_dir), repo)


if __name__ == "__main__":
    main()