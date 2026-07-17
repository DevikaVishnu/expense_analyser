from datetime import date

from expense_analyser.models import Transaction
from expense_analyser.storage import TransactionRepository


def _make_transaction(**overrides) -> Transaction:
    # dedup_hash is intentionally omitted — Transaction's model_validator
    # computes it automatically from the other fields, overwriting
    # anything passed here, so tests that need distinct rows must vary a
    # real content field (amount, description, transaction_date, ...).
    defaults = dict(
        account_id="IslandFederal_checking",
        transaction_date=date(2026, 6, 1),
        description="Coffee Shop",
        amount=450,
        currency="USD",
        source_file="June_2026.pdf",
    )
    defaults.update(overrides)
    return Transaction(**defaults)


def test_insert_and_fetch_round_trip():
    repo = TransactionRepository(":memory:")
    txn = _make_transaction()

    assert repo.insert(txn) is True

    fetched = repo.fetch_all()
    assert len(fetched) == 1
    assert fetched[0].id == txn.id
    assert fetched[0].account_id == txn.account_id
    assert fetched[0].transaction_date == txn.transaction_date
    assert fetched[0].amount == txn.amount
    assert fetched[0].dedup_hash == txn.dedup_hash


def test_insert_duplicate_is_ignored():
    repo = TransactionRepository(":memory:")
    txn = _make_transaction()

    first_insert = repo.insert(txn)
    second_insert = repo.insert(txn)

    assert first_insert is True
    assert second_insert is False
    assert len(repo.fetch_all()) == 1


def test_fetch_uncategorized_excludes_categorized_transactions():
    repo = TransactionRepository(":memory:")
    # dedup_hash is auto-computed from content fields (account_id, date,
    # amount, description...) via Transaction's model_validator, so two
    # rows need a genuinely different content field to avoid colliding —
    # varying amount here, not dedup_hash (which would be overwritten).
    repo.insert(_make_transaction(amount=-100, category="Groceries"))
    repo.insert(_make_transaction(amount=-200, category=None))

    uncategorized = repo.fetch_uncategorized()

    assert len(uncategorized) == 1
    assert uncategorized[0].amount == -200


def test_update_category_sets_category_and_removes_from_uncategorized():
    repo = TransactionRepository(":memory:")
    txn = _make_transaction()
    repo.insert(txn)

    repo.update_category(txn.id, "Groceries")

    assert repo.fetch_all()[0].category == "Groceries"
    assert repo.fetch_uncategorized() == []


def test_merchant_rule_round_trip():
    repo = TransactionRepository(":memory:")

    assert repo.get_merchant_rule("UBER *TRIP") is None

    repo.set_merchant_rule("UBER *TRIP", "Uber")

    assert repo.get_merchant_rule("UBER *TRIP") == "Uber"


def test_set_merchant_rule_upserts_rather_than_erroring_on_conflict():
    repo = TransactionRepository(":memory:")
    repo.set_merchant_rule("UBER *TRIP", "Uber")

    repo.set_merchant_rule("UBER *TRIP", "Transport")

    assert repo.get_merchant_rule("UBER *TRIP") == "Transport"


def test_search_by_description_matches_case_insensitive_substring():
    repo = TransactionRepository(":memory:")
    repo.insert(_make_transaction(description="STARBUCKS LIBRARY"))
    repo.insert(_make_transaction(description="UBER *TRIP"))

    results = repo.search_by_description("starbucks")

    assert len(results) == 1
    assert results[0].description == "STARBUCKS LIBRARY"


def test_search_by_description_no_matches_returns_empty_list():
    repo = TransactionRepository(":memory:")
    repo.insert(_make_transaction())

    assert repo.search_by_description("nonexistent") == []


def test_fetch_by_month_filters_by_year_month():
    repo = TransactionRepository(":memory:")
    repo.insert(_make_transaction(transaction_date=date(2026, 1, 5), amount=-100))
    repo.insert(_make_transaction(transaction_date=date(2026, 1, 20), amount=-200))
    repo.insert(_make_transaction(transaction_date=date(2026, 2, 1), amount=-300))

    january = repo.fetch_by_month("2026-01")

    assert len(january) == 2
    assert {t.amount for t in january} == {-100, -200}


def test_fetch_by_category_filters_case_insensitively():
    repo = TransactionRepository(":memory:")
    repo.insert(_make_transaction(amount=-100, category="Groceries"))
    repo.insert(_make_transaction(amount=-200, category="Uber"))

    results = repo.fetch_by_category("groceries")

    assert len(results) == 1
    assert results[0].amount == -100


def test_get_all_categories_returns_distinct_used_categories():
    repo = TransactionRepository(":memory:")
    repo.insert(_make_transaction(amount=-100, category="Groceries"))
    repo.insert(_make_transaction(amount=-200, category="Groceries"))
    repo.insert(_make_transaction(amount=-300, category="Uber"))
    repo.insert(_make_transaction(amount=-400, category=None))

    assert repo.get_all_categories() == ["Groceries", "Uber"]


def test_spend_by_category_nets_signed_amounts_within_a_category():
    repo = TransactionRepository(":memory:")
    repo.insert(_make_transaction(amount=-5000, category="Groceries"))
    repo.insert(_make_transaction(amount=699, category="Groceries"))  # refund
    repo.insert(_make_transaction(amount=-1000, category=None))

    results = dict(repo.spend_by_category())

    assert results["Groceries"] == -4301
    assert results[None] == -1000


def test_spend_by_month_groups_by_year_month():
    repo = TransactionRepository(":memory:")
    repo.insert(_make_transaction(transaction_date=date(2026, 1, 15), amount=-500))
    repo.insert(_make_transaction(transaction_date=date(2026, 1, 20), amount=-300))
    repo.insert(_make_transaction(transaction_date=date(2026, 2, 1), amount=-100))

    results = dict(repo.spend_by_month())

    assert results["2026-01"] == -800
    assert results["2026-02"] == -100


def test_spend_by_month_and_category_groups_by_both():
    repo = TransactionRepository(":memory:")
    repo.insert(_make_transaction(transaction_date=date(2026, 1, 15), amount=-500, category="Groceries"))
    repo.insert(_make_transaction(transaction_date=date(2026, 1, 20), amount=-300, category="Eat Out"))
    repo.insert(_make_transaction(transaction_date=date(2026, 2, 1), amount=-100, category="Groceries"))

    results = {(month, category): total for month, category, total in repo.spend_by_month_and_category()}

    assert results[("2026-01", "Groceries")] == -500
    assert results[("2026-01", "Eat Out")] == -300
    assert results[("2026-02", "Groceries")] == -100


def test_spend_by_category_for_month_filters_to_that_month_only():
    repo = TransactionRepository(":memory:")
    repo.insert(_make_transaction(transaction_date=date(2026, 1, 15), amount=-500, category="Groceries"))
    repo.insert(_make_transaction(transaction_date=date(2026, 1, 20), amount=-300, category="Eat Out"))
    repo.insert(_make_transaction(transaction_date=date(2026, 2, 1), amount=-100, category="Groceries"))

    results = dict(repo.spend_by_category_for_month("2026-01"))

    assert results == {"Groceries": -500, "Eat Out": -300}