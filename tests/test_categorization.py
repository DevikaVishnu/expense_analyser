from datetime import date
from unittest.mock import patch

from expense_analyser.categorization import (
    CATEGORIES,
    INCOME_CATEGORY,
    _group_for_category,
    _known_categories,
    _resolve_category,
    categorize_interactively,
    normalize_description,
    recategorize,
    review_category,
    review_month,
)
from expense_analyser.models import Transaction
from expense_analyser.storage import TransactionRepository


def _make_transaction(**overrides) -> Transaction:
    defaults = dict(
        account_id="test",
        transaction_date=date(2025, 1, 1),
        description="UBER *TRIP 706 MISSION ST",
        amount=-500,
        currency="USD",
        source_file="test.pdf",
    )
    defaults.update(overrides)
    return Transaction(**defaults)


def _no_input_expected(prompt=""):
    raise AssertionError(f"input() should not have been called, but was called with prompt: {prompt!r}")


# --- normalize_description ---


def test_normalize_description_takes_first_two_tokens():
    assert normalize_description("UBER *TRIP 706 MISSION ST") == "UBER *TRIP"


def test_normalize_description_distinguishes_shared_prefix_merchants():
    magnolia = normalize_description("TST*MAGNOLIA BAK 383 W 31st St Space New")
    thai = normalize_description("TST*THAI TANIUM 657 Ctr Point Way Gaithe")
    assert magnolia != thai


def test_normalize_description_is_case_insensitive():
    assert normalize_description("uber *trip 706 mission st") == "UBER *TRIP"


def test_normalize_description_handles_single_token():
    assert normalize_description("STARBUCKS") == "STARBUCKS"


# --- _resolve_category ---


def test_resolve_category_matches_existing_case_insensitively():
    assert _resolve_category("shopping", ["Shopping", "Groceries"]) == "Shopping"


def test_resolve_category_returns_unchanged_when_no_match():
    assert _resolve_category("Rideshare", ["Groceries"]) == "Rideshare"


def test_resolve_category_matches_income_category_despite_exclusion_from_known():
    # INCOME_CATEGORY is deliberately excluded from known_categories, but
    # typing any case variant of it should still resolve to the canonical
    # form rather than creating a separate near-duplicate category.
    assert _resolve_category("income", ["Groceries"]) == INCOME_CATEGORY
    assert _resolve_category("INCOME", ["Groceries"]) == INCOME_CATEGORY


# --- _known_categories ---


def test_known_categories_includes_fixed_categories():
    repo = TransactionRepository(":memory:")
    known = _known_categories(repo)
    assert set(CATEGORIES).issubset(set(known))


def test_known_categories_includes_previously_used_free_text_categories():
    repo = TransactionRepository(":memory:")
    txn = _make_transaction(category="Shopping")
    repo.insert(txn)

    assert "Shopping" in _known_categories(repo)


def test_known_categories_excludes_income_category():
    repo = TransactionRepository(":memory:")
    repo.insert(_make_transaction(description="DEPOSIT Incoming Wire", amount=100, category=INCOME_CATEGORY))

    assert INCOME_CATEGORY not in _known_categories(repo)


def test_known_categories_deduplicates_case_insensitively():
    repo = TransactionRepository(":memory:")
    repo.insert(_make_transaction(category="shopping"))

    known = _known_categories(repo)
    assert known.count("shopping") + known.count("Shopping") == 1


# --- category groups ---


def test_group_for_category_returns_group_name_for_a_member():
    assert _group_for_category("Subway") == "Train"
    assert _group_for_category("Amtrak") == "Train"
    assert _group_for_category("LIRR") == "Train"


def test_group_for_category_returns_unchanged_for_ungrouped_category():
    assert _group_for_category("Groceries") == "Groceries"


def test_train_is_not_in_categories_since_it_became_a_group_name():
    assert "Train" not in CATEGORIES


# --- categorize_interactively ---


def test_categorize_interactively_with_no_uncategorized_transactions(capsys):
    repo = TransactionRepository(":memory:")

    categorize_interactively(repo)

    assert "No uncategorized transactions." in capsys.readouterr().out


def test_categorize_interactively_assigns_category_by_number():
    repo = TransactionRepository(":memory:")
    repo.insert(_make_transaction())

    uber_number = str(CATEGORIES.index("Uber") + 1)
    with patch("builtins.input", lambda prompt="": uber_number):
        categorize_interactively(repo)

    result = repo.fetch_all()[0]
    assert result.category == "Uber"
    assert repo.get_merchant_rule("UBER *TRIP") == "Uber"


def test_categorize_interactively_auto_applies_known_merchant_rule_without_prompting():
    repo = TransactionRepository(":memory:")
    repo.set_merchant_rule("UBER *TRIP", "Uber")
    repo.insert(_make_transaction())

    with patch("builtins.input", _no_input_expected):
        categorize_interactively(repo)

    assert repo.fetch_all()[0].category == "Uber"


def test_categorize_interactively_accepts_free_text_category():
    repo = TransactionRepository(":memory:")
    repo.insert(_make_transaction())

    with patch("builtins.input", lambda prompt="": "Rideshare"):
        categorize_interactively(repo)

    result = repo.fetch_all()[0]
    assert result.category == "Rideshare"
    assert repo.get_merchant_rule("UBER *TRIP") == "Rideshare"


def test_categorize_interactively_skips_blank_response_with_no_suggestion():
    repo = TransactionRepository(":memory:")
    repo.insert(_make_transaction())

    with patch("builtins.input", lambda prompt="": ""):
        categorize_interactively(repo)

    assert repo.fetch_all()[0].category is None


def test_categorize_interactively_explicit_skip_command():
    repo = TransactionRepository(":memory:")
    repo.insert(_make_transaction())

    with patch("builtins.input", lambda prompt="": "skip"):
        categorize_interactively(repo)

    assert repo.fetch_all()[0].category is None


def test_categorize_interactively_auto_labels_deposit_as_income():
    repo = TransactionRepository(":memory:")
    repo.insert(_make_transaction(description="DEPOSIT Incoming Wire Transfer-123", amount=265000))

    with patch("builtins.input", _no_input_expected):
        categorize_interactively(repo)

    assert repo.fetch_all()[0].category == INCOME_CATEGORY


def test_categorize_interactively_auto_labels_check_deposit_as_income():
    repo = TransactionRepository(":memory:")
    repo.insert(_make_transaction(description="EFT FISERVIP CHECK DEP Remote Chk Dep 260508", amount=10000))

    with patch("builtins.input", _no_input_expected):
        categorize_interactively(repo)

    assert repo.fetch_all()[0].category == INCOME_CATEGORY


def test_categorize_interactively_refund_is_not_auto_labeled_income():
    repo = TransactionRepository(":memory:")
    # Positive amount, but no INCOME_MARKERS text — same shape as a
    # "DEBIT CARD CREDIT" refund, which should NOT be treated as income.
    repo.insert(_make_transaction(description="IC* INSTACART 50 Beale Street", amount=400))

    with patch("builtins.input", lambda prompt="": "2"):
        categorize_interactively(repo)

    assert repo.fetch_all()[0].category != INCOME_CATEGORY


def test_categorize_interactively_refund_auto_applies_original_purchase_category():
    repo = TransactionRepository(":memory:")
    repo.set_merchant_rule("IC* INSTACART", "Groceries")
    refund = _make_transaction(description="IC* INSTACART 50 Beale Street", amount=400)
    repo.insert(refund)

    with patch("builtins.input", _no_input_expected):
        categorize_interactively(repo)

    assert repo.fetch_all()[0].category == "Groceries"


def test_categorize_interactively_newly_typed_category_available_for_next_transaction():
    repo = TransactionRepository(":memory:")
    repo.insert(_make_transaction(description="DECKERS RETAIL", amount=-9540))
    repo.insert(_make_transaction(description="SOME OTHER SHOP", amount=-1200))

    responses = iter(["Shopping", str(len(CATEGORIES) + 1)])
    with patch("builtins.input", lambda prompt="": next(responses)):
        categorize_interactively(repo)

    categories = {t.description: t.category for t in repo.fetch_all()}
    assert categories["DECKERS RETAIL"] == "Shopping"
    assert categories["SOME OTHER SHOP"] == "Shopping"


def test_categorize_interactively_typing_income_resolves_to_canonical_category():
    repo = TransactionRepository(":memory:")
    # No INCOME_MARKERS text, so this isn't auto-labeled — but the user
    # can still manually type "income" and have it resolve correctly.
    repo.insert(_make_transaction(description="SOME CHECK NO MARKER", amount=10000))

    with patch("builtins.input", lambda prompt="": "income"):
        categorize_interactively(repo)

    assert repo.fetch_all()[0].category == INCOME_CATEGORY


# --- recategorize ---


def test_recategorize_no_matches(capsys):
    repo = TransactionRepository(":memory:")

    recategorize(repo, "nonexistent")

    assert "No transactions found" in capsys.readouterr().out


def test_recategorize_bulk_applies_to_all_matches_by_number():
    repo = TransactionRepository(":memory:")
    txn1 = _make_transaction(description="STARBUCKS LIBRAR", amount=-450, category="Eat Out")
    txn2 = _make_transaction(description="STARBUCKS DOWNTOWN", amount=-500, category="Eat Out")
    repo.insert(txn1)
    repo.insert(txn2)

    groceries_number = str(CATEGORIES.index("Groceries") + 1)
    with patch("builtins.input", lambda prompt="": groceries_number):
        recategorize(repo, "starbucks")

    assert all(t.category == "Groceries" for t in repo.fetch_all())


def test_recategorize_updates_merchant_rule():
    repo = TransactionRepository(":memory:")
    repo.insert(_make_transaction(description="STARBUCKS LIBRAR", amount=-450, category="Eat Out"))

    with patch("builtins.input", lambda prompt="": "Groceries"):
        recategorize(repo, "starbucks")

    assert repo.get_merchant_rule("STARBUCKS LIBRAR") == "Groceries"


def test_recategorize_blank_response_makes_no_changes():
    repo = TransactionRepository(":memory:")
    repo.insert(_make_transaction(description="STARBUCKS LIBRAR", amount=-450, category="Eat Out"))

    with patch("builtins.input", lambda prompt="": ""):
        recategorize(repo, "starbucks")

    assert repo.fetch_all()[0].category == "Eat Out"


# --- review_month ---


def test_review_month_no_transactions(capsys):
    repo = TransactionRepository(":memory:")

    review_month(repo, "2026-01")

    assert "No transactions found for 2026-01" in capsys.readouterr().out


def test_review_month_prints_total_and_transaction_list(capsys):
    repo = TransactionRepository(":memory:")
    repo.insert(_make_transaction(transaction_date=date(2026, 1, 5), amount=-500, category="Uber"))
    repo.insert(_make_transaction(transaction_date=date(2026, 1, 10), amount=-2000, category="Groceries"))

    with patch("builtins.input", lambda prompt="": ""):
        review_month(repo, "2026-01")

    out = capsys.readouterr().out
    assert "2026-01 total: -$25.00" in out
    assert "Uber" in out
    assert "Groceries" in out


def test_review_month_total_excludes_income_and_separate_categories_but_still_lists_them(capsys):
    repo = TransactionRepository(":memory:")
    repo.insert(_make_transaction(transaction_date=date(2026, 1, 5), amount=-500, category="Groceries"))
    repo.insert(_make_transaction(transaction_date=date(2026, 1, 10), amount=265000, category=INCOME_CATEGORY))
    repo.insert(_make_transaction(transaction_date=date(2026, 1, 15), amount=-1190069, category="Stony Brook"))

    with patch("builtins.input", lambda prompt="": ""):
        review_month(repo, "2026-01")

    out = capsys.readouterr().out
    assert "2026-01 total: -$5.00  (Stony Brook: -$11900.69)" in out
    assert INCOME_CATEGORY in out
    assert "Stony Brook" in out


def test_review_month_changes_category_by_number():
    repo = TransactionRepository(":memory:")
    repo.insert(_make_transaction(transaction_date=date(2026, 1, 5), description="UBER *TRIP", amount=-500, category="Uber"))

    eat_out_number = str(CATEGORIES.index("Eat Out") + 1)
    responses = iter(["1", eat_out_number, ""])
    with patch("builtins.input", lambda prompt="": next(responses)):
        review_month(repo, "2026-01")

    assert repo.fetch_all()[0].category == "Eat Out"
    assert repo.get_merchant_rule("UBER *TRIP") == "Eat Out"


def test_review_month_reprints_list_with_updated_category(capsys):
    repo = TransactionRepository(":memory:")
    repo.insert(_make_transaction(transaction_date=date(2026, 1, 5), description="UBER *TRIP", amount=-500, category="Uber"))

    eat_out_number = str(CATEGORIES.index("Eat Out") + 1)
    responses = iter(["1", eat_out_number, ""])
    with patch("builtins.input", lambda prompt="": next(responses)):
        review_month(repo, "2026-01")

    out = capsys.readouterr().out
    # The transaction list should be printed twice — once initially
    # showing "Uber", once again after the change showing "Eat Out".
    assert out.count("Transactions for 2026-01:") == 2
    assert "| Uber" in out
    assert "| Eat Out" in out


def test_review_month_invalid_transaction_number_does_not_crash():
    repo = TransactionRepository(":memory:")
    repo.insert(_make_transaction(transaction_date=date(2026, 1, 5), amount=-500, category="Uber"))

    responses = iter(["99", ""])
    with patch("builtins.input", lambda prompt="": next(responses)):
        review_month(repo, "2026-01")

    assert repo.fetch_all()[0].category == "Uber"


def test_review_month_blank_response_finishes_without_changes():
    repo = TransactionRepository(":memory:")
    repo.insert(_make_transaction(transaction_date=date(2026, 1, 5), amount=-500, category="Uber"))

    with patch("builtins.input", lambda prompt="": ""):
        review_month(repo, "2026-01")

    assert repo.fetch_all()[0].category == "Uber"


# --- review_category ---


def test_review_category_no_transactions(capsys):
    repo = TransactionRepository(":memory:")

    review_category(repo, "Bank of America Expenses")

    assert "No transactions found for Bank of America Expenses" in capsys.readouterr().out


def test_review_category_shows_total_and_list(capsys):
    repo = TransactionRepository(":memory:")
    repo.insert(_make_transaction(description="EFT A", amount=-300, category="Bank of America Expenses"))
    repo.insert(_make_transaction(description="EFT B", amount=-11900, category="Bank of America Expenses"))

    with patch("builtins.input", lambda prompt="": ""):
        review_category(repo, "Bank of America Expenses")

    out = capsys.readouterr().out
    assert "Bank of America Expenses total: -$122.00" in out
    assert "EFT A" in out
    assert "EFT B" in out


def test_review_category_moving_outlier_removes_it_from_list_and_updates_total():
    repo = TransactionRepository(":memory:")
    repo.insert(_make_transaction(
        transaction_date=date(2025, 1, 1), description="EFT CKTRANSFER", amount=-300, category="Bank of America Expenses"
    ))
    repo.insert(_make_transaction(
        transaction_date=date(2025, 1, 2), description="EFT SBUFEESDEPOSIT", amount=-1190000, category="Bank of America Expenses"
    ))

    misc_number = str(CATEGORIES.index("Miscellaneous") + 1)
    # fetch_by_category orders by transaction_date, so transaction 2 is
    # the later-dated outlier — move it to Miscellaneous, then finish.
    responses = iter(["2", misc_number, ""])
    with patch("builtins.input", lambda prompt="": next(responses)):
        review_category(repo, "Bank of America Expenses")

    remaining = repo.fetch_by_category("Bank of America Expenses")
    assert len(remaining) == 1
    assert remaining[0].description == "EFT CKTRANSFER"
    assert repo.fetch_by_category("Miscellaneous")[0].description == "EFT SBUFEESDEPOSIT"


def test_review_category_reselecting_same_category_keeps_it_in_list():
    repo = TransactionRepository(":memory:")
    repo.insert(_make_transaction(description="EFT CKTRANSFER", amount=-300, category="Bank of America Expenses"))

    responses = iter(["1", "Bank of America Expenses", ""])
    with patch("builtins.input", lambda prompt="": next(responses)):
        review_category(repo, "Bank of America Expenses")

    assert len(repo.fetch_by_category("Bank of America Expenses")) == 1


def test_review_category_with_group_name_shows_combined_members(capsys):
    repo = TransactionRepository(":memory:")
    repo.insert(_make_transaction(transaction_date=date(2026, 1, 5), description="MTA*NYCT", amount=-300, category="Subway"))
    repo.insert(_make_transaction(transaction_date=date(2026, 1, 10), description="AMTRAK.COM", amount=-10000, category="Amtrak"))

    with patch("builtins.input", lambda prompt="": ""):
        review_category(repo, "Train")

    out = capsys.readouterr().out
    assert "Train total: -$103.00" in out
    assert "MTA*NYCT" in out
    assert "AMTRAK.COM" in out


def test_review_category_group_moving_within_group_stays_in_list(capsys):
    # Both the message printed and the fact a second iteration of the
    # loop happens (rather than the function returning) distinguish
    # "stayed in list" from "removed" — the final category alone would
    # be the same either way.
    repo = TransactionRepository(":memory:")
    repo.insert(_make_transaction(description="MTA*NYCT", amount=-300, category="Subway"))

    responses = iter(["1", "Amtrak", ""])
    with patch("builtins.input", lambda prompt="": next(responses)):
        review_category(repo, "Train")

    out = capsys.readouterr().out
    assert "Updated to 'Amtrak'." in out
    assert "removed from this list" not in out
    assert repo.fetch_all()[0].category == "Amtrak"


def test_review_category_group_moving_out_of_group_removes_from_list(capsys):
    repo = TransactionRepository(":memory:")
    repo.insert(_make_transaction(description="MTA*NYCT", amount=-300, category="Subway"))

    # No trailing "" needed: removing the only transaction empties the
    # list, which the loop detects and breaks out of on its own.
    responses = iter(["1", "Groceries"])
    with patch("builtins.input", lambda prompt="": next(responses)):
        review_category(repo, "Train")

    out = capsys.readouterr().out
    assert "Moved to 'Groceries' — removed from this list." in out
    assert repo.fetch_all()[0].category == "Groceries"