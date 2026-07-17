import sqlite3
from datetime import date, datetime
from uuid import UUID

from expense_analyser.models import Transaction


class TransactionRepository:
    def __init__(self, db_path: str):
        self.connection = sqlite3.connect(db_path)
        self._create_tables()

    def _create_tables(self) -> None:
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
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS merchant_rules (
                normalized_description TEXT PRIMARY KEY,
                category TEXT NOT NULL
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
        return self._fetch("SELECT * FROM transactions")

    def fetch_uncategorized(self) -> list[Transaction]:
        return self._fetch("SELECT * FROM transactions WHERE category IS NULL")

    def _fetch(self, query: str) -> list[Transaction]:
        cursor = self.connection.execute(query)
        columns = [col[0] for col in cursor.description]
        return [self._row_to_transaction(dict(zip(columns, row))) for row in cursor.fetchall()]

    def update_category(self, transaction_id: UUID, category: str) -> None:
        self.connection.execute(
            "UPDATE transactions SET category = ? WHERE id = ?",
            (category, str(transaction_id)),
        )
        self.connection.commit()

    def get_merchant_rule(self, normalized_description: str) -> str | None:
        cursor = self.connection.execute(
            "SELECT category FROM merchant_rules WHERE normalized_description = ?",
            (normalized_description,),
        )
        row = cursor.fetchone()
        return row[0] if row else None

    def set_merchant_rule(self, normalized_description: str, category: str) -> None:
        self.connection.execute(
            """
            INSERT INTO merchant_rules (normalized_description, category)
            VALUES (?, ?)
            ON CONFLICT(normalized_description) DO UPDATE SET category = excluded.category
            """,
            (normalized_description, category),
        )
        self.connection.commit()

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