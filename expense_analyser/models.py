from pydantic import BaseModel, Field, model_validator
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4
import hashlib

class Transaction(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    account_id: str
    transaction_date: date
    description: str
    amount: int
    currency: str
    category: str | None = None
    balance: int | None = None
    source_file: str
    ingested_at: datetime = Field(default_factory=datetime.now)
    dedup_hash: str = ""

    @staticmethod
    def from_raw_amount(raw: str) -> int:
        return int(Decimal(raw)*100)

    def compute_dedup_hash(self) -> str:
        # account_id + transaction_date + amount + description [+ balance]
        balance_part = getattr(self, 'balance', '')
        payload = f"{self.account_id}|{self.transaction_date}|{self.amount}|{self.description}"
        if balance_part:
            payload += f"|{balance_part}"
        return hashlib.sha256(payload.encode('utf-8')).hexdigest()
    
    @model_validator(mode="after")
    def _set_dedup_hash(self) -> "Transaction":
        self.dedup_hash = self.compute_dedup_hash()
        return self