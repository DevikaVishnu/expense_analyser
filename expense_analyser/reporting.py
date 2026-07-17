"""Spend reports derived from categorized transactions.

Prints spend-by-category and spend-by-month summaries to the terminal,
and writes the same data out as CSV files for anyone who wants to
pivot on it in a spreadsheet.
"""

import argparse
import csv
from pathlib import Path

from expense_analyser.categorization import INCOME_CATEGORY, SEPARATE_CATEGORIES
from expense_analyser.formatting import format_amount
from expense_analyser.storage import TransactionRepository

DEFAULT_DB_PATH = "expenses.db"
DEFAULT_REPORTS_DIR = "reports"


def _monthly_expenditure(repo: TransactionRepository) -> dict[str, int]:
    """Total spend per month, counting only actual routine expenses —
    excludes INCOME_CATEGORY (not spending at all, so netting it in
    would understate how much actually went out) and
    SEPARATE_CATEGORIES (real spending, but tracked apart from
    routine expenditure since it's large and irregular).
    """
    excluded = {INCOME_CATEGORY, *SEPARATE_CATEGORIES}
    totals: dict[str, int] = {}
    for month, category, total in repo.spend_by_month_and_category():
        if category in excluded:
            continue
        totals[month] = totals.get(month, 0) + total
    return totals


def print_spend_by_category(repo: TransactionRepository) -> None:
    print("\nSpend by category:")
    for category, total in repo.spend_by_category():
        label = category or "Uncategorized"
        print(f"  {label:<25} {format_amount(total):>12}")


def print_spend_by_month(repo: TransactionRepository) -> None:
    print("\nTotal expenditure by month:")
    for month, total in sorted(_monthly_expenditure(repo).items()):
        print(f"  {month:<25} {format_amount(total):>12}")


def print_spend_by_month_and_category(repo: TransactionRepository) -> None:
    monthly_totals = _monthly_expenditure(repo)

    print("\nSpend by month and category:")
    current_month = None
    # Rows arrive pre-sorted by month (spend_by_month_and_category's SQL
    # does GROUP BY month, category ORDER BY month, ...), so a month
    # header only needs printing when the month actually changes.
    for month, category, total in repo.spend_by_month_and_category():
        if month != current_month:
            print(f"\n  {month} (expenditure: {format_amount(monthly_totals[month])}):")
            current_month = month
        label = category or "Uncategorized"
        print(f"    {label:<25} {format_amount(total):>12}")


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


def write_month_category_csv(rows: list[tuple], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["month", "category", "total"])
        for month, category, total_cents in rows:
            writer.writerow([month, category or "Uncategorized", f"{total_cents / 100:.2f}"])


def generate_reports(repo: TransactionRepository, reports_dir: Path) -> None:
    print_spend_by_category(repo)
    print_spend_by_month(repo)
    print_spend_by_month_and_category(repo)

    write_csv(repo.spend_by_category(), ["category", "total"], reports_dir / "spend_by_category.csv")
    write_csv(sorted(_monthly_expenditure(repo).items()), ["month", "total"], reports_dir / "spend_by_month.csv")
    write_month_category_csv(repo.spend_by_month_and_category(), reports_dir / "spend_by_month_and_category.csv")

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