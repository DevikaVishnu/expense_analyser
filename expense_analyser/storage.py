import sqlite3
from datetime import date, datetime
from uuid import UUID

from expense_analyser.models import Transaction


class TransactionRepository:
    def __init__(self, db_path: str):
        self.connection = sqlite3.connect(db_path)
        self._create_table()

    def _create_table(self) -> None:
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS transactions (
                id TEXT PRIMARY KEY,
                account_id TEXT NOT NULL,
                transaction_date TEXT NOT NULL,
                description TEXT NOT NULL,
                amount INTEGER NOT NULL,
                currency TEXT NOT NULL,
                category TEXT,
                balance INTEGER,
                source_file TEXT NOT NULL,
                dedup_hash TEXT NOT NULL UNIQUE,
                ingested_at TEXT NOT NULL
            )
            """
        )
        self.connection.commit()

    def insert(self, txn: Transaction) -> bool:
        cursor = self.connection.execute(
            """
            INSERT OR IGNORE INTO transactions (
                id, account_id, transaction_date, description, amount,
                currency, category, balance, source_file, dedup_hash, ingested_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(txn.id),
                txn.account_id,
                txn.transaction_date.isoformat(),
                txn.description,
                txn.amount,
                txn.currency,
                txn.category,
                txn.balance,
                txn.source_file,
                txn.dedup_hash,
                txn.ingested_at.isoformat(),
            ),
        )
        self.connection.commit()
        return cursor.rowcount > 0

    def fetch_all(self) -> list[Transaction]:
        cursor = self.connection.execute("SELECT * FROM transactions")
        columns = [col[0] for col in cursor.description]
        return [self._row_to_transaction(dict(zip(columns, row))) for row in cursor.fetchall()]

    @staticmethod
    def _row_to_transaction(row: dict) -> Transaction:
        return Transaction(
            id=UUID(row["id"]),
            account_id=row["account_id"],
            transaction_date=date.fromisoformat(row["transaction_date"]),
            description=row["description"],
            amount=row["amount"],
            currency=row["currency"],
            category=row["category"],
            balance=row["balance"],
            source_file=row["source_file"],
            dedup_hash=row["dedup_hash"],
            ingested_at=datetime.fromisoformat(row["ingested_at"]),
        )

    def close(self) -> None:
        self.connection.close()