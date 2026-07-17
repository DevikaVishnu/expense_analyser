from datetime import date
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from expense_analyser.api import app, get_repo
from expense_analyser.categorization import INCOME_CATEGORY
from expense_analyser.models import Transaction
from expense_analyser.storage import TransactionRepository


def _make_transaction(**overrides) -> Transaction:
    defaults = dict(
        account_id="test",
        transaction_date=date(2026, 1, 15),
        description="Test",
        amount=-500,
        currency="USD",
        source_file="test.pdf",
    )
    defaults.update(overrides)
    return Transaction(**defaults)


def _client_with_repo(repo: TransactionRepository) -> TestClient:
    app.dependency_overrides[get_repo] = lambda: repo
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_dependency_overrides():
    yield
    app.dependency_overrides.clear()


def test_list_months_returns_expenditure_and_separate_totals():
    repo = TransactionRepository(":memory:")
    repo.insert(_make_transaction(transaction_date=date(2026, 1, 5), amount=-500, category="Groceries"))
    repo.insert(_make_transaction(transaction_date=date(2026, 1, 10), amount=-1190069, category="Stony Brook"))

    response = _client_with_repo(repo).get("/api/months")

    assert response.status_code == 200
    assert response.json() == [
        {"month": "2026-01", "expenditure": -500, "separate_totals": {"Stony Brook": -1190069}}
    ]


def test_list_month_categories_returns_breakdown_for_that_month():
    repo = TransactionRepository(":memory:")
    repo.insert(_make_transaction(transaction_date=date(2026, 1, 5), amount=-500, category="Groceries"))
    repo.insert(_make_transaction(transaction_date=date(2026, 2, 5), amount=-300, category="Eat Out"))

    response = _client_with_repo(repo).get("/api/months/2026-01/categories")

    assert response.status_code == 200
    assert response.json() == [{"category": "Groceries", "total": -500}]


def test_list_month_categories_labels_null_category_as_uncategorized():
    repo = TransactionRepository(":memory:")
    repo.insert(_make_transaction(transaction_date=date(2026, 1, 5), amount=-500, category=None))

    response = _client_with_repo(repo).get("/api/months/2026-01/categories")

    assert response.status_code == 200
    assert response.json() == [{"category": "Uncategorized", "total": -500}]


def test_list_month_categories_rolls_up_train_group():
    repo = TransactionRepository(":memory:")
    repo.insert(_make_transaction(transaction_date=date(2026, 1, 5), amount=-500, category="Subway"))
    repo.insert(_make_transaction(transaction_date=date(2026, 1, 10), amount=-300, category="Amtrak"))

    response = _client_with_repo(repo).get("/api/months/2026-01/categories")

    assert response.status_code == 200
    assert response.json() == [{"category": "Train", "total": -800}]


def test_list_month_categories_excludes_income():
    repo = TransactionRepository(":memory:")
    repo.insert(_make_transaction(transaction_date=date(2026, 1, 5), amount=-500, category="Groceries"))
    repo.insert(_make_transaction(transaction_date=date(2026, 1, 10), amount=265000, category=INCOME_CATEGORY))

    response = _client_with_repo(repo).get("/api/months/2026-01/categories")

    assert response.status_code == 200
    assert response.json() == [{"category": "Groceries", "total": -500}]


def test_list_month_categories_excludes_separate_categories():
    repo = TransactionRepository(":memory:")
    repo.insert(_make_transaction(transaction_date=date(2026, 1, 5), amount=-500, category="Groceries"))
    repo.insert(_make_transaction(transaction_date=date(2026, 1, 10), amount=-1190069, category="Stony Brook"))

    response = _client_with_repo(repo).get("/api/months/2026-01/categories")

    assert response.status_code == 200
    assert response.json() == [{"category": "Groceries", "total": -500}]


def test_list_group_members_returns_member_breakdown():
    repo = TransactionRepository(":memory:")
    repo.insert(_make_transaction(transaction_date=date(2026, 1, 5), amount=-500, category="Subway"))
    repo.insert(_make_transaction(transaction_date=date(2026, 1, 10), amount=-300, category="Amtrak"))

    response = _client_with_repo(repo).get("/api/months/2026-01/categories/Train")

    assert response.status_code == 200
    body = {row["category"]: row["total"] for row in response.json()}
    assert body == {"Subway": -500, "Amtrak": -300}


def test_list_group_members_empty_for_non_group_category():
    repo = TransactionRepository(":memory:")
    repo.insert(_make_transaction(transaction_date=date(2026, 1, 5), amount=-500, category="Groceries"))

    response = _client_with_repo(repo).get("/api/months/2026-01/categories/Groceries")

    assert response.status_code == 200
    assert response.json() == []


def test_list_month_transactions_returns_only_that_months_transactions():
    repo = TransactionRepository(":memory:")
    repo.insert(_make_transaction(transaction_date=date(2026, 1, 5), description="UBER *TRIP"))
    repo.insert(_make_transaction(transaction_date=date(2026, 2, 5), description="OTHER"))

    response = _client_with_repo(repo).get("/api/months/2026-01/transactions")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["description"] == "UBER *TRIP"


def test_update_transaction_category_updates_category_and_merchant_rule():
    repo = TransactionRepository(":memory:")
    txn = _make_transaction(description="UBER *TRIP 123")
    repo.insert(txn)

    response = _client_with_repo(repo).patch(f"/api/transactions/{txn.id}", json={"category": "Uber"})

    assert response.status_code == 200
    assert response.json()["category"] == "Uber"
    assert repo.get_merchant_rule("UBER *TRIP") == "Uber"


def test_update_transaction_category_404_for_unknown_id():
    repo = TransactionRepository(":memory:")

    response = _client_with_repo(repo).patch(f"/api/transactions/{uuid4()}", json={"category": "Uber"})

    assert response.status_code == 404