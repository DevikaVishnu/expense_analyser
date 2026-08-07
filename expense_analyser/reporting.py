"""Spend-by-category / spend-by-month reports, printed and exported to CSV."""

import argparse
import csv
from pathlib import Path

from expense_analyser.categorization import INCOME_CATEGORY, SEPARATE_CATEGORIES, _group_for_category
from expense_analyser.formatting import format_amount
from expense_analyser.storage import TransactionRepository

DEFAULT_DB_PATH = "expenses.db"
DEFAULT_REPORTS_DIR = "reports"


def _monthly_breakdown(repo: TransactionRepository) -> tuple[dict[str, int], dict[str, dict[str, int]]]:
    """Returns (expenditure_by_month, separate_by_month) — routine
    spend vs SEPARATE_CATEGORIES totals, each month -> total (or
    month -> {category: total} for separate). Income dropped from
    both, it isn't spending."""
    separate_categories = set(SEPARATE_CATEGORIES)
    expenditure: dict[str, int] = {}
    separate: dict[str, dict[str, int]] = {}

    for month, category, total in repo.spend_by_month_and_category():
        if category == INCOME_CATEGORY:
            continue
        if category in separate_categories:
            separate.setdefault(month, {})[category] = total
        else:
            expenditure[month] = expenditure.get(month, 0) + total

    return expenditure, separate


def _format_separate_totals(separate_for_month: dict[str, int] | None) -> str:
    if not separate_for_month:
        return ""
    parts = ", ".join(f"{category}: {format_amount(total)}" for category, total in separate_for_month.items())
    return f"  ({parts})"


def _apply_category_groups(rows: list[tuple[str | None, int]]) -> list[tuple[str | None, int]]:
    """Collapses group members (Subway + Amtrak + LIRR) into one summed
    "Train" row for display — storage keeps the real category."""
    grouped: dict[str | None, int] = {}
    for category, total in rows:
        display_category = _group_for_category(category) if category is not None else category
        grouped[display_category] = grouped.get(display_category, 0) + total
    return sorted(grouped.items(), key=lambda item: item[1])


def print_spend_by_category(repo: TransactionRepository) -> None:
    print("\nSpend by category:")
    for category, total in _apply_category_groups(repo.spend_by_category()):
        label = category or "Uncategorized"
        print(f"  {label:<25} {format_amount(total):>12}")


def print_spend_by_month(repo: TransactionRepository) -> None:
    expenditure, separate = _monthly_breakdown(repo)

    print("\nTotal expenditure by month:")
    for month, total in sorted(expenditure.items()):
        print(f"  {month:<25} {format_amount(total):>12}{_format_separate_totals(separate.get(month))}")


def print_spend_by_month_and_category(repo: TransactionRepository) -> None:
    expenditure, separate = _monthly_breakdown(repo)

    rows_by_month: dict[str, list[tuple[str | None, int]]] = {}
    for month, category, total in repo.spend_by_month_and_category():
        rows_by_month.setdefault(month, []).append((category, total))

    print("\nSpend by month and category:")
    for month in sorted(rows_by_month):
        extra = _format_separate_totals(separate.get(month))
        print(f"\n  {month} (expenditure: {format_amount(expenditure[month])}{extra}):")
        for category, total in _apply_category_groups(rows_by_month[month]):
            label = category or "Uncategorized"
            print(f"    {label:<25} {format_amount(total):>12}")


def write_csv(rows: list[tuple], headers: list[str], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for label, total_cents in rows:
            # Fixed 2-decimal string, not a raw float — no binary
            # floating-point noise in the CSV.
            writer.writerow([label or "Uncategorized", f"{total_cents / 100:.2f}"])


def write_month_category_csv(rows: list[tuple], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["month", "category", "total"])
        for month, category, total_cents in rows:
            writer.writerow([month, category or "Uncategorized", f"{total_cents / 100:.2f}"])


def _grouped_month_category_rows(repo: TransactionRepository) -> list[tuple[str, str | None, int]]:
    rows_by_month: dict[str, list[tuple[str | None, int]]] = {}
    for month, category, total in repo.spend_by_month_and_category():
        rows_by_month.setdefault(month, []).append((category, total))

    return [
        (month, category, total)
        for month in sorted(rows_by_month)
        for category, total in _apply_category_groups(rows_by_month[month])
    ]


def generate_reports(repo: TransactionRepository, reports_dir: Path) -> None:
    print_spend_by_category(repo)
    print_spend_by_month(repo)
    print_spend_by_month_and_category(repo)

    expenditure, _ = _monthly_breakdown(repo)

    write_csv(_apply_category_groups(repo.spend_by_category()), ["category", "total"], reports_dir / "spend_by_category.csv")
    write_csv(sorted(expenditure.items()), ["month", "total"], reports_dir / "spend_by_month.csv")
    write_month_category_csv(_grouped_month_category_rows(repo), reports_dir / "spend_by_month_and_category.csv")

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