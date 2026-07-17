"""FastAPI backend serving transaction and spend-report data as JSON.

Mostly read-only: GET /api/months and GET /api/months/{month}/transactions
expose the same data the CLI reports already compute. The one write
endpoint, PATCH /api/transactions/{transaction_id}, reuses the same
update_category + set_merchant_rule pattern every CLI categorization
tool already uses, so a category fixed here behaves identically.

Run with: uvicorn expense_analyser.api:app --reload
"""

from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel

from expense_analyser.categorization import normalize_description
from expense_analyser.models import Transaction
from expense_analyser.reporting import _monthly_breakdown
from expense_analyser.storage import TransactionRepository

DB_PATH = "expenses.db"

app = FastAPI(title="Expense Analyser API")


def get_repo() -> TransactionRepository:
    return TransactionRepository(DB_PATH)


class MonthSummary(BaseModel):
    month: str
    expenditure: int
    separate_totals: dict[str, int]


class UpdateCategoryRequest(BaseModel):
    category: str


@app.get("/api/months", response_model=list[MonthSummary])
def list_months(repo: TransactionRepository = Depends(get_repo)) -> list[MonthSummary]:
    expenditure, separate = _monthly_breakdown(repo)
    return [
        MonthSummary(month=month, expenditure=total, separate_totals=separate.get(month, {}))
        for month, total in sorted(expenditure.items())
    ]


@app.get("/api/months/{month}/transactions", response_model=list[Transaction])
def list_month_transactions(
    month: str, repo: TransactionRepository = Depends(get_repo)
) -> list[Transaction]:
    return repo.fetch_by_month(month)


@app.patch("/api/transactions/{transaction_id}", response_model=Transaction)
def update_transaction_category(
    transaction_id: UUID,
    body: UpdateCategoryRequest,
    repo: TransactionRepository = Depends(get_repo),
) -> Transaction:
    txn = repo.get_by_id(transaction_id)
    if txn is None:
        raise HTTPException(status_code=404, detail="Transaction not found")

    repo.update_category(transaction_id, body.category)
    repo.set_merchant_rule(normalize_description(txn.description), body.category)

    return repo.get_by_id(transaction_id)