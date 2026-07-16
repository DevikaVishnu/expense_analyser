from datetime import date
from pathlib import Path

from expense_analyser.ingest import ingest_all
from expense_analyser.models import Transaction
from expense_analyser.parsers.base import StatementParser
from expense_analyser.storage import TransactionRepository


class FakeParser(StatementParser):
    account_id = "FakeAccount"
    statement_type = "checking"

    def parse(self, pdf_path: Path) -> list[Transaction]:
        return [
            Transaction(
                account_id=self.account_id,
                transaction_date=date(2025, 1, 1),
                description="Fake transaction",
                amount=-500,
                currency="USD",
                source_file=pdf_path.name,
            )
        ]


def _make_statement_folder(tmp_path: Path, account: str, doctype: str, filename: str) -> Path:
    folder = tmp_path / account / doctype
    folder.mkdir(parents=True)
    pdf_path = folder / filename
    pdf_path.touch()
    return pdf_path


def test_ingest_all_routes_to_correct_parser_and_inserts(tmp_path):
    _make_statement_folder(tmp_path, "FakeAccount", "fake_doctype", "statement.pdf")
    registry = {"FakeAccount/fake_doctype": FakeParser}
    repo = TransactionRepository(":memory:")

    ingest_all(tmp_path, repo, registry=registry)

    transactions = repo.fetch_all()
    assert len(transactions) == 1
    assert transactions[0].description == "Fake transaction"


def test_ingest_all_skips_unregistered_folder_without_crashing(tmp_path):
    _make_statement_folder(tmp_path, "UnknownAccount", "unknown_doctype", "statement.pdf")
    registry = {"FakeAccount/fake_doctype": FakeParser}
    repo = TransactionRepository(":memory:")

    ingest_all(tmp_path, repo, registry=registry)

    assert repo.fetch_all() == []


def test_ingest_all_is_idempotent(tmp_path):
    _make_statement_folder(tmp_path, "FakeAccount", "fake_doctype", "statement.pdf")
    registry = {"FakeAccount/fake_doctype": FakeParser}
    repo = TransactionRepository(":memory:")

    ingest_all(tmp_path, repo, registry=registry)
    ingest_all(tmp_path, repo, registry=registry)

    assert len(repo.fetch_all()) == 1


def test_ingest_all_handles_uppercase_pdf_extension(tmp_path):
    _make_statement_folder(tmp_path, "FakeAccount", "fake_doctype", "statement.PDF")
    registry = {"FakeAccount/fake_doctype": FakeParser}
    repo = TransactionRepository(":memory:")

    ingest_all(tmp_path, repo, registry=registry)

    assert len(repo.fetch_all()) == 1