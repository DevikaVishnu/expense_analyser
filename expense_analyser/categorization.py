"""Interactive categorization CLI.

Walks through uncategorized transactions and remembers each merchant
choice as a rule, so the same merchant isn't asked about twice.
"""

import argparse

from expense_analyser.formatting import format_amount
from expense_analyser.models import Transaction
from expense_analyser.storage import TransactionRepository

DEFAULT_DB_PATH = "expenses.db"

# Auto-assigned to credits, never prompted for — doesn't belong in the
# interactive CATEGORIES list.
INCOME_CATEGORY = "Income"

# Credits matching one of these get auto-labeled Income. Anything else
# falls through to the normal prompt — that's how refunds (no marker,
# same description as the original purchase) end up back in the right
# category instead of counted as income.
INCOME_MARKERS = ["DEPOSIT", "CHECK DEP"]

CATEGORIES = [
    "Eat Out",
    "Groceries",
    "Uber",
    "Online purchases",
    "Medicines",
    "Miscellaneous",
]

# Display-only rollup — transactions keep their real category (Subway,
# Amtrak...), reports show the group total too. "Train" isn't in
# CATEGORIES anymore since it's a group name now, not a pickable one.
CATEGORY_GROUPS = {
    "Train": ["Subway", "Amtrak", "LIRR"],
}


def _group_for_category(category: str) -> str:
    """Group name if category belongs to one, else category unchanged."""
    for group, members in CATEGORY_GROUPS.items():
        if category in members:
            return group
    return category

# Real spend, but excluded from the headline expenditure total — large
# one-off payments (tuition) that'd swamp normal month-to-month
# comparisons. Still shown as their own line elsewhere.
SEPARATE_CATEGORIES = ["Stony Brook"]


def _known_categories(repo: TransactionRepository) -> list[str]:
    """CATEGORIES plus any free-text category actually in use, minus
    Income. Case-insensitive merge so "shopping" doesn't duplicate
    "Shopping"."""
    known = list(CATEGORIES)
    for category in repo.get_all_categories():
        if category == INCOME_CATEGORY:
            continue
        if not any(existing.lower() == category.lower() for existing in known):
            known.append(category)
    return known


def _resolve_category(response: str, known_categories: list[str]) -> str:
    """Match response against known_categories case-insensitively,
    reusing the existing casing if found. Falls through to Income even
    though it's not in known_categories, so a manually-typed "income"
    (e.g. for a check deposit the auto-detect missed) still joins the
    same bucket instead of forking a new category."""
    if response.lower() == INCOME_CATEGORY.lower():
        return INCOME_CATEGORY
    for existing in known_categories:
        if existing.lower() == response.lower():
            return existing
    return response


def normalize_description(description: str) -> str:
    """First two tokens, uppercased, as a merchant key. Two tokens
    because processor prefixes like "TST*" collide on the first
    token alone."""
    tokens = description.upper().split()
    return " ".join(tokens[:2])


def categorize_interactively(repo: TransactionRepository) -> None:
    """Prompt for every genuinely new uncategorized expense.

    Income and known merchants (rule already saved) get auto-labeled
    without asking — refunds ride along here too since they share a
    description with the original purchase. Only a truly new merchant
    stops and asks; the answer saves a merchant rule so it isn't asked
    again. Use recategorize() to fix a rule that was wrong, instead of
    reviewing transactions one by one here.
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
            category = known_categories[int(response) - 1]
        elif response:
            # Match existing casing if this is a dupe, else it's new —
            # remember it either way so it's numbered going forward.
            category = _resolve_category(response, known_categories)
            if category not in known_categories:
                known_categories.append(category)
        else:
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
    """Bulk-reassign every transaction matching search_term (substring,
    case-insensitive), categorized or not, and refresh the merchant
    rule so future transactions get the fix too."""
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


def _review_transactions(
    repo: TransactionRepository,
    transactions: list[Transaction],
    label: str,
    category_filter: str | None = None,
    exclude_from_total: set[str] | None = None,
    separate_totals_for: set[str] | None = None,
) -> None:
    """Print a running total + numbered list, then let the user fix
    categories by number until they hit Enter. Shared by review_month
    and review_category.

    category_filter (review_category's case) drops a transaction from
    the list once it's moved elsewhere, since it no longer belongs;
    review_month just relabels in place since the month never changes.

    exclude_from_total (e.g. Income) drops out of the total silently;
    separate_totals_for (e.g. Stony Brook) drops out too but gets its
    own printed value. Nothing disappears from the list either way —
    only from the headline number.
    """
    if not transactions:
        print(f"No transactions found for {label}.")
        return

    def print_state() -> None:
        excluded = (exclude_from_total or set()) | (separate_totals_for or set())
        total = sum(txn.amount for txn in transactions if txn.category not in excluded)

        extra = ""
        if separate_totals_for:
            separate_amounts = {}
            for txn in transactions:
                if txn.category in separate_totals_for:
                    separate_amounts[txn.category] = separate_amounts.get(txn.category, 0) + txn.amount
            if separate_amounts:
                parts = ", ".join(f"{cat}: {format_amount(amt)}" for cat, amt in separate_amounts.items())
                extra = f"  ({parts})"

        print(f"\n{label} total: {format_amount(total)}{extra}")
        print(f"Transactions for {label}:")
        for i, txn in enumerate(transactions, start=1):
            category = txn.category or "Uncategorized"
            print(f"  {i}. {txn.transaction_date} | {format_amount(txn.amount):>10} | {txn.description} | {category}")

    print_state()

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

        if category_filter is not None:
            # _group_for_category so moving Subway -> Amtrak still
            # counts as "still Train" when reviewing the group.
            still_belongs = _group_for_category(new_category).lower() == category_filter.lower()
        else:
            still_belongs = True

        if category_filter is not None and not still_belongs:
            transactions.remove(txn)
            print(f"Moved to {new_category!r} — removed from this list.")
        else:
            txn.category = new_category
            print(f"Updated to {new_category!r}.")

        if not transactions:
            print(f"\nNo transactions left for {label}.")
            break

        print_state()


def review_month(repo: TransactionRepository, month: str) -> None:
    """Show the total expenditure and every individual transaction for
    month ("YYYY-MM"), same expenditure definition as the reports —
    Income excluded, Stony Brook called out separately but still
    visible in the list.
    """
    _review_transactions(
        repo,
        repo.fetch_by_month(month),
        label=month,
        exclude_from_total={INCOME_CATEGORY},
        separate_totals_for=set(SEPARATE_CATEGORIES),
    )


def review_category(repo: TransactionRepository, category: str) -> None:
    """Everything currently in category + running total — for tracking
    down why a category's report total looks wrong. Group names (e.g.
    "Train") pull in every member category's transactions, since
    nothing's ever literally stored as "Train".
    """
    if category in CATEGORY_GROUPS:
        transactions = [
            txn for member in CATEGORY_GROUPS[category] for txn in repo.fetch_by_category(member)
        ]
        transactions.sort(key=lambda txn: txn.transaction_date)
    else:
        transactions = repo.fetch_by_category(category)

    _review_transactions(repo, transactions, label=category, category_filter=category)


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
        "--review-month",
        metavar="MONTH",
        help=(
            "Show the total spend and every transaction for MONTH (YYYY-MM), "
            "and optionally change any of their categories, instead of the "
            "normal uncategorized-only flow."
        ),
    )
    arg_parser.add_argument(
        "--review-category",
        metavar="CATEGORY",
        help=(
            "Show every transaction currently in CATEGORY and its running "
            "total, and optionally move any outliers to a different "
            "category — for tracking down why a category's report total "
            "looks wrong."
        ),
    )
    args = arg_parser.parse_args()

    repo = TransactionRepository(args.db_path)

    if args.recategorize:
        recategorize(repo, args.recategorize)
    elif args.review_month:
        review_month(repo, args.review_month)
    elif args.review_category:
        review_category(repo, args.review_category)
    else:
        categorize_interactively(repo)


if __name__ == "__main__":
    main()
