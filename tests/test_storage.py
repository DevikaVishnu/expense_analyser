from datetime import date

from expense_analyser.models import Transaction
from expense_analyser.storage import TransactionRepository


def _make_transaction(**overrides) -> Transaction:
    defaults = dict(
        account_id="IslandFederal_checking",
        transaction_date=date(2026, 6, 1),
        description="Coffee Shop",
        amount=450,
        currency="USD",
        source_file="June_2026.pdf",
        dedup_hash="placeholder-hash",
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