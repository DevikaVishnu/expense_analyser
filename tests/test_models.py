from expense_analyser.models import Transaction
from datetime import date, datetime
from uuid import UUID, uuid4
from pydantic import ValidationError
import pytest


def test_transaction_construction_with_defaults():
    txn = Transaction(
        account_id="IslandFederal_checking",
        transaction_date=date(2026, 6, 1),
        description="Coffee Shop",
        amount=450,
        currency="USD",
        source_file="June_2026.pdf",
        dedup_hash="placeholder",
    )
    assert isinstance(txn.id, UUID)
    assert txn.category is None
    assert txn.balance is None
    assert isinstance(txn.ingested_at, datetime)

def test_transaction_missing_required_field_raises():
    with pytest.raises(ValidationError):
        Transaction(
            transaction_date=date(2026, 6, 1),
            description="Coffee Shop",
            amount=450,
            currency="USD",
            source_file="June_2026.pdf",
            dedup_hash="placeholder",
        )

def test_from_raw_amount():
    assert Transaction.from_raw_amount("19.99") == 1999
    assert Transaction.from_raw_amount("0.01") == 1
    assert Transaction.from_raw_amount("100") == 10000

def test_compute_dedup_hash_deterministic_and_sensitive():
    """
build two Transactions with identical 
account_id/transaction_date/amount/description 
(other required fields can differ or be dummy values — 
they're not part of the hash payload), call .compute_dedup_hash() 
on each, assert equal. Then build a third that differs only in amount, 
assert its hash differs from the first.
    """
    txn1 = Transaction(
        account_id="IslandFederal_checking",
        transaction_date=date(2026, 6, 1),
        description="Coffee Shop",
        amount=450,
        currency="USD",
        source_file="June_2026.pdf",
        dedup_hash="placeholder",
    )
    txn2 = Transaction(
        account_id="IslandFederal_checking",
        transaction_date=date(2026, 6, 1),
        description="Coffee Shop",
        amount=450,
        currency="USD",
        source_file="June_2026.pdf",
        dedup_hash="placeholder",
    )
    txn3 = Transaction(
        account_id="IslandFederal_checking",
        transaction_date=date(2026, 6, 1),
        description="Coffee Shop",
        amount=45,
        currency="USD",
        source_file="June_2026.pdf",
        dedup_hash="placeholder",
    )

    txn1_dedup_hash = txn1.compute_dedup_hash()
    txn2_dedup_hash = txn2.compute_dedup_hash()
    txn3_dedup_hash = txn3.compute_dedup_hash()

    assert txn1_dedup_hash == txn2_dedup_hash
    assert txn1_dedup_hash != txn3_dedup_hash
