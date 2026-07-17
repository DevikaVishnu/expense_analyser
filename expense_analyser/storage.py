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

    def search_by_description(self, search_term: str) -> list[Transaction]:
        return self._fetch(
            "SELECT * FROM transactions WHERE description LIKE ?",
            (f"%{search_term}%",),
        )

    def fetch_by_month(self, month: str) -> list[Transaction]:
        return self._fetch(
            "SELECT * FROM transactions WHERE strftime('%Y-%m', transaction_date) = ? ORDER BY transaction_date",
            (month,),
        )

    def fetch_by_category(self, category: str) -> list[Transaction]:
        # COLLATE NOCASE: category values are already casing-normalized
        # on write (see categorization._resolve_category), but this
        # keeps a lookup like "bank of america" from missing rows
        # stored as "Bank of America" just because the CLI arg's case
        # doesn't match exactly.
        return self._fetch(
            "SELECT * FROM transactions WHERE category = ? COLLATE NOCASE ORDER BY transaction_date",
            (category,),
        )

    def get_all_categories(self) -> list[str]:
        cursor = self.connection.execute(
            "SELECT DISTINCT category FROM transactions WHERE category IS NOT NULL ORDER BY category"
        )
        return [row[0] for row in cursor.fetchall()]

    def _fetch(self, query: str, params: tuple = ()) -> list[Transaction]:
        cursor = self.connection.execute(query, params)
        columns = [col[0] for col in cursor.description]
        return [self._row_to_transaction(dict(zip(columns, row))) for row in cursor.fetchall()]

    def update_category(self, transaction_id: UUID, category: str) -> None:
        self.connection.execute(
            "UPDATE transactions SET category = ? WHERE id = ?",
            (category, str(transaction_id)),
        )
        self.connection.commit()

    def spend_by_category(self) -> list[tuple[str | None, int]]:
        cursor = self.connection.execute(
            "SELECT category, SUM(amount) FROM transactions GROUP BY category ORDER BY SUM(amount) ASC"
        )
        return cursor.fetchall()

    def spend_by_month(self) -> list[tuple[str, int]]:
        cursor = self.connection.execute(
            """
            SELECT strftime('%Y-%m', transaction_date) AS month, SUM(amount)
            FROM transactions
            GROUP BY month
            ORDER BY month
            """
        )
        return cursor.fetchall()

    def spend_by_month_and_category(self) -> list[tuple[str, str | None, int]]:
        cursor = self.connection.execute(
            """
            SELECT strftime('%Y-%m', transaction_date) AS month, category, SUM(amount)
            FROM transactions
            GROUP BY month, category
            ORDER BY month, SUM(amount) ASC
            """
        )
        return cursor.fetchall()

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