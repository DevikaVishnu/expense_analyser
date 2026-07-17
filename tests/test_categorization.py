from datetime import date
from unittest.mock import patch

from expense_analyser.categorization import CATEGORIES, categorize_interactively, normalize_description
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


def test_categorize_interactively_with_no_uncategorized_transactions(capsys):
    repo = TransactionRepository(":memory:")

    categorize_interactively(repo)

    assert "No uncategorized transactions." in capsys.readouterr().out


def test_categorize_interactively_assigns_category_by_number():
    repo = TransactionRepository(":memory:")
    txn = _make_transaction()
    repo.insert(txn)

    uber_number = str(CATEGORIES.index("Uber") + 1)
    with patch("builtins.input", lambda prompt="": uber_number):
        categorize_interactively(repo)

    result = repo.fetch_all()[0]
    assert result.category == "Uber"
    assert repo.get_merchant_rule("UBER *TRIP") == "Uber"


def test_categorize_interactively_uses_suggested_rule_on_enter():
    repo = TransactionRepository(":memory:")
    repo.set_merchant_rule("UBER *TRIP", "Uber")
    repo.insert(_make_transaction())

    with patch("builtins.input", lambda prompt="": ""):
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

    result = repo.fetch_all()[0]
    assert result.category is None