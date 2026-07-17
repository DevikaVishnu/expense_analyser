"""Interactive categorization of parsed transactions.

Transactions land in the database with category=None after ingestion.
This module walks a user through the uncategorized ones from the
command line, assigning a category to each — and remembers each choice
as a "merchant rule" so the same merchant doesn't need to be manually
categorized every single time it shows up in a future statement.
"""

import argparse

from expense_analyser.formatting import format_amount
from expense_analyser.models import Transaction
from expense_analyser.storage import TransactionRepository

DEFAULT_DB_PATH = "expenses.db"

# Auto-assigned to credits (deposits, refunds, incoming transfers) without
# prompting — there's nothing meaningful to ask about a deposit from an
# expense category list. Kept separate from CATEGORIES since it's never
# something the user picks interactively.
INCOME_CATEGORY = "Income"

# A credit (amount >= 0) is auto-labeled INCOME_CATEGORY if its
# description contains any of these markers; otherwise it falls
# through to the normal prompt (which is how refunds — no marker,
# same description as the original purchase — get routed to the
# original purchase's category instead of being miscounted as income).
# Extend this list as new genuine-income statement formats show up.
INCOME_MARKERS = ["DEPOSIT", "CHECK DEP"]

CATEGORIES = [
    "Eat Out",
    "Groceries",
    "Uber",
    "Train",
    "Online purchases",
    "Medicines",
    "Miscellaneous",
]


def _known_categories(repo: TransactionRepository) -> list[str]:
    """The fixed CATEGORIES list, extended with any category that has
    ever actually been assigned to a transaction (e.g. a free-text
    category typed in a previous run). INCOME_CATEGORY is excluded —
    it's auto-assigned only, never something to pick manually.

    Merging is case-insensitive, so a category already present as
    "Shopping" won't also show up as a second, separate "shopping".
    """
    known = list(CATEGORIES)
    for category in repo.get_all_categories():
        if category == INCOME_CATEGORY:
            continue
        if not any(existing.lower() == category.lower() for existing in known):
            known.append(category)
    return known


def _resolve_category(response: str, known_categories: list[str]) -> str:
    """Match a typed category against known_categories case-insensitively.

    If response matches an existing category except for case, reuse
    that existing entry's exact spelling/casing rather than creating a
    second, differently-cased category — whoever types a category
    first effectively sets its canonical casing. Returns response
    unchanged if nothing matches, which then becomes the canonical
    form for anyone who reuses it later.

    INCOME_CATEGORY is checked explicitly even though it's excluded
    from known_categories (so it never shows up as a numbered option)
    — otherwise typing "income" manually for a credit that the
    auto-detection missed (e.g. a check deposit, which doesn't say
    "DEPOSIT") would create a separate "income" category instead of
    joining the auto-labeled "Income" bucket.
    """
    if response.lower() == INCOME_CATEGORY.lower():
        return INCOME_CATEGORY
    for existing in known_categories:
        if existing.lower() == response.lower():
            return existing
    return response


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
    """Prompt the user to categorize every genuinely new uncategorized expense.

    Three kinds of transactions never require a prompt:

    1. Genuine income (amount >= 0 AND the description contains one of
       INCOME_MARKERS) is auto-labeled INCOME_CATEGORY.
    2. Anything whose merchant key already has a saved rule from a
       previous categorization is auto-applied that rule directly —
       once you've told the system WEEE is Groceries, it applies that
       to every WEEE transaction without asking again. Printed as an
       FYI line, not a prompt, so you still see what happened.
    3. Refunds fall under (2) automatically: a refund's description
       looks identical to the original purchase's (e.g. a "DEBIT CARD
       CREDIT" refund carries the same description as a normal
       purchase from that merchant — the word "credit" never survives
       into the stored description), so it shares the same merchant
       key and picks up the same rule, keeping per-category totals
       netted correctly rather than miscounted as unrelated income.

    Only a transaction whose merchant key has *no* existing rule yet
    actually stops and asks — show the known category list, accept a
    number, a freely typed category name, or 'skip' to leave it
    uncategorized for now. Every real answer saves both the
    transaction's category and a new merchant rule for that key, so
    the *next* transaction from that merchant no longer needs to ask.

    If a rule later turns out to be wrong, use recategorize() to fix
    every affected transaction at once rather than reviewing them
    individually here.
    """
    uncategorized = repo.fetch_uncategorized()

    if not uncategorized:
        print("No uncategorized transactions.")
        return

    known_categories = _known_categories(repo)
    categorized_count = 0
    auto_applied_count = 0
    income_count = 0

    for txn in uncategorized:
        is_income = txn.amount >= 0 and any(
            marker in txn.description.upper() for marker in INCOME_MARKERS
        )
        if is_income:
            repo.update_category(txn.id, INCOME_CATEGORY)
            income_count += 1
            continue

        key = normalize_description(txn.description)
        suggested = repo.get_merchant_rule(key)

        amount_display = format_amount(txn.amount)

        if suggested:
            repo.update_category(txn.id, suggested)
            auto_applied_count += 1
            print(f"{txn.transaction_date} | {amount_display} | {txn.description} -> {suggested} (auto)")
            continue

        print(f"\n{txn.transaction_date} | {amount_display} | {txn.description}")
        options = ", ".join(f"{i + 1}) {c}" for i, c in enumerate(known_categories))
        print(f"Categories: {options}")
        response = input("Category (number, new name, or 'skip'): ").strip()

        if response.lower() == "skip":
            print("Skipped — will remain uncategorized.")
            continue
        elif response.isdigit() and 1 <= int(response) <= len(known_categories):
            # A number selects from the known-categories list.
            category = known_categories[int(response) - 1]
        elif response:
            # Reuse an existing category's casing if this matches one
            # case-insensitively; otherwise it's genuinely new — either
            # way, remember it so it's numbered for the rest of this run.
            category = _resolve_category(response, known_categories)
            if category not in known_categories:
                known_categories.append(category)
        else:
            # Blank response with nothing to default to: leave this
            # transaction uncategorized rather than forcing a choice.
            print("No category entered, skipping.")
            continue

        repo.update_category(txn.id, category)
        repo.set_merchant_rule(key, category)
        categorized_count += 1

    print(
        f"\nCategorized {categorized_count} new expense(s), auto-applied "
        f"{auto_applied_count} known merchant transaction(s), and "
        f"auto-labeled {income_count} income transaction(s), out of "
        f"{len(uncategorized)} total."
    )


def recategorize(repo: TransactionRepository, search_term: str) -> None:
    """Bulk-reassign the category of every transaction whose description
    contains search_term (case-insensitive substring match), including
    ones that already have a category — unlike categorize_interactively,
    which only ever looks at uncategorized transactions.

    Also refreshes the merchant rule for each matched transaction's own
    normalized key, so future transactions from the same merchant(s)
    get suggested the corrected category too.
    """
    matches = repo.search_by_description(search_term)

    if not matches:
        print(f"No transactions found matching {search_term!r}.")
        return

    print(f"\nFound {len(matches)} transaction(s) matching {search_term!r}:")
    for txn in matches:
        current = txn.category or "Uncategorized"
        print(f"  {txn.transaction_date} | {format_amount(txn.amount)} | {txn.description} | currently: {current}")

    known_categories = _known_categories(repo)
    options = ", ".join(f"{i + 1}) {c}" for i, c in enumerate(known_categories))
    print(f"\nCategories: {options}")
    response = input("New category for all of these (number or new name): ").strip()

    if response.isdigit() and 1 <= int(response) <= len(known_categories):
        new_category = known_categories[int(response) - 1]
    elif response:
        new_category = _resolve_category(response, known_categories)
    else:
        print("No category entered, nothing changed.")
        return

    for txn in matches:
        repo.update_category(txn.id, new_category)
        repo.set_merchant_rule(normalize_description(txn.description), new_category)

    print(f"\nUpdated {len(matches)} transaction(s) to {new_category!r}.")


def review_month(repo: TransactionRepository, month: str) -> None:
    """Show the total spend and every individual transaction for month
    (format "YYYY-MM"), then let the user selectively change the
    category of any of them by number — as many times as needed, not
    a forced one-by-one pass through every transaction.
    """
    transactions = repo.fetch_by_month(month)

    if not transactions:
        print(f"No transactions found for {month}.")
        return

    total = sum(txn.amount for txn in transactions)
    print(f"\n{month} total: {format_amount(total)}")

    print(f"\nTransactions for {month}:")
    for i, txn in enumerate(transactions, start=1):
        category = txn.category or "Uncategorized"
        print(f"  {i}. {txn.transaction_date} | {format_amount(txn.amount):>10} | {txn.description} | {category}")

    known_categories = _known_categories(repo)

    while True:
        choice = input("\nEnter a number to change its category (or press Enter to finish): ").strip()
        if not choice:
            break

        if not choice.isdigit() or not (1 <= int(choice) <= len(transactions)):
            print("Not a valid transaction number.")
            continue

        txn = transactions[int(choice) - 1]
        options = ", ".join(f"{i + 1}) {c}" for i, c in enumerate(known_categories))
        print(f"Categories: {options}")
        response = input(f"New category for {txn.description!r} (number or new name): ").strip()

        if response.isdigit() and 1 <= int(response) <= len(known_categories):
            new_category = known_categories[int(response) - 1]
        elif response:
            new_category = _resolve_category(response, known_categories)
            if new_category not in known_categories:
                known_categories.append(new_category)
        else:
            print("No category entered, unchanged.")
            continue

        repo.update_category(txn.id, new_category)
        repo.set_merchant_rule(normalize_description(txn.description), new_category)
        txn.category = new_category
        print(f"Updated to {new_category!r}.")


def main() -> None:
    arg_parser = argparse.ArgumentParser(description="Interactively categorize uncategorized transactions.")
    arg_parser.add_argument(
        "--db-path",
        default=DEFAULT_DB_PATH,
        help=f"Path to the SQLite database file (default: {DEFAULT_DB_PATH})",
    )
    arg_parser.add_argument(
        "--recategorize",
        metavar="SEARCH_TERM",
        help=(
            "Bulk-reassign category for every transaction (categorized or not) "
            "whose description contains SEARCH_TERM, instead of the normal "
            "uncategorized-only flow."
        ),
    )
    arg_parser.add_argument(
        "--review",
        metavar="MONTH",
        help=(
            "Show the total spend and every transaction for MONTH (YYYY-MM), "
            "and optionally change any of their categories, instead of the "
            "normal uncategorized-only flow."
        ),
    )
    args = arg_parser.parse_args()

    repo = TransactionRepository(args.db_path)

    if args.recategorize:
        recategorize(repo, args.recategorize)
    elif args.review:
        review_month(repo, args.review)
    else:
        categorize_interactively(repo)


if __name__ == "__main__":
    main()
