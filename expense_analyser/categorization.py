"""Interactive categorization of parsed transactions.

Transactions land in the database with category=None after ingestion.
This module walks a user through the uncategorized ones from the
command line, assigning a category to each — and remembers each choice
as a "merchant rule" so the same merchant doesn't need to be manually
categorized every single time it shows up in a future statement.
"""

import argparse

from expense_analyser.models import Transaction
from expense_analyser.storage import TransactionRepository

DEFAULT_DB_PATH = "expenses.db"

CATEGORIES = [
    "Eat Out",
    "Groceries",
    "Uber",
    "Train",
    "Online purchases",
    "Medicines",
    "Miscellaneous",
]


def normalize_description(description: str) -> str:
    """Reduce a raw transaction description to a stable merchant key.

    Uses the first two whitespace-separated tokens, uppercased. Two
    tokens rather than one: several merchants share a single-word
    payment-processor prefix (e.g. "TST*MAGNOLIA BAK" and "TST*THAI
    TANIUM" both start with "TST*"), so a one-token key would
    incorrectly treat different merchants as the same one.
    """
    tokens = description.upper().split()
    return " ".join(tokens[:2])


def categorize_interactively(repo: TransactionRepository) -> None:
    """Prompt the user to categorize every uncategorized transaction.

    For each transaction: look up whether its merchant key already has
    a saved rule from a previous categorization. If so, offer it as a
    default the user can accept by pressing Enter; otherwise show the
    fixed category list and accept either a number, a freely typed
    category name, or a blank response to skip. Every answer updates
    both the transaction's own category and the merchant rule for that
    key, so future transactions from the same merchant get suggested
    automatically.
    """
    uncategorized = repo.fetch_uncategorized()

    if not uncategorized:
        print("No uncategorized transactions.")
        return

    categorized_count = 0

    for txn in uncategorized:
        key = normalize_description(txn.description)
        suggested = repo.get_merchant_rule(key)

        # Amounts are stored as signed integer cents; render as a
        # human-readable signed dollar string for the prompt.
        sign = "-" if txn.amount < 0 else ""
        amount_display = f"{sign}${abs(txn.amount) / 100:.2f}"
        print(f"\n{txn.transaction_date} | {amount_display} | {txn.description}")

        if suggested:
            prompt = f"Category [{suggested}]: "
        else:
            options = ", ".join(f"{i + 1}) {c}" for i, c in enumerate(CATEGORIES))
            print(f"Categories: {options}")
            prompt = "Category (number or new name): "

        response = input(prompt).strip()

        if not response and suggested:
            # Blank response with a suggestion on offer = accept it.
            category = suggested
        elif response.isdigit() and 1 <= int(response) <= len(CATEGORIES):
            # A number selects from the fixed CATEGORIES list.
            category = CATEGORIES[int(response) - 1]
        elif response:
            # Any other non-blank text becomes a new category as-is,
            # even if it isn't already in CATEGORIES.
            category = response
        else:
            # Blank response with nothing to default to: leave this
            # transaction uncategorized rather than forcing a choice.
            print("No category entered, skipping.")
            continue

        repo.update_category(txn.id, category)
        repo.set_merchant_rule(key, category)
        categorized_count += 1

    print(f"\nCategorized {categorized_count} of {len(uncategorized)} transactions.")


def main() -> None:
    arg_parser = argparse.ArgumentParser(description="Interactively categorize uncategorized transactions.")
    arg_parser.add_argument(
        "--db-path",
        default=DEFAULT_DB_PATH,
        help=f"Path to the SQLite database file (default: {DEFAULT_DB_PATH})",
    )
    args = arg_parser.parse_args()

    repo = TransactionRepository(args.db_path)
    categorize_interactively(repo)


if __name__ == "__main__":
    main()
