"""Spend reports derived from categorized transactions.

Prints spend-by-category and spend-by-month summaries to the terminal,
and writes the same data out as CSV files for anyone who wants to
pivot on it in a spreadsheet.
"""

import argparse
import csv
from pathlib import Path

from expense_analyser.storage import TransactionRepository

DEFAULT_DB_PATH = "expenses.db"
DEFAULT_REPORTS_DIR = "reports"


def _format_amount(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    return f"{sign}${abs(cents) / 100:.2f}"


def print_spend_by_category(repo: TransactionRepository) -> None:
    print("\nSpend by category:")
    for category, total in repo.spend_by_category():
        label = category or "Uncategorized"
        print(f"  {label:<25} {_format_amount(total):>12}")


def print_spend_by_month(repo: TransactionRepository) -> None:
    print("\nSpend by month:")
    for month, total in repo.spend_by_month():
        print(f"  {month:<25} {_format_amount(total):>12}")


def write_csv(rows: list[tuple], headers: list[str], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for label, total_cents in rows:
            # Cents -> dollars only for this final text export, formatted
            # as a fixed 2-decimal string rather than a raw float, so no
            # binary floating-point noise ends up in the CSV.
            writer.writerow([label or "Uncategorized", f"{total_cents / 100:.2f}"])


def generate_reports(repo: TransactionRepository, reports_dir: Path) -> None:
    print_spend_by_category(repo)
    print_spend_by_month(repo)

    write_csv(repo.spend_by_category(), ["category", "total"], reports_dir / "spend_by_category.csv")
    write_csv(repo.spend_by_month(), ["month", "total"], reports_dir / "spend_by_month.csv")

    print(f"\nCSV reports written to {reports_dir}/")


def main() -> None:
    arg_parser = argparse.ArgumentParser(description="Generate spend reports from the transaction database.")
    arg_parser.add_argument(
        "--db-path",
        default=DEFAULT_DB_PATH,
        help=f"Path to the SQLite database file (default: {DEFAULT_DB_PATH})",
    )
    arg_parser.add_argument(
        "--reports-dir",
        default=DEFAULT_REPORTS_DIR,
        help=f"Directory to write CSV reports to (default: {DEFAULT_REPORTS_DIR})",
    )
    args = arg_parser.parse_args()

    repo = TransactionRepository(args.db_path)
    generate_reports(repo, Path(args.reports_dir))


if __name__ == "__main__":
    main()