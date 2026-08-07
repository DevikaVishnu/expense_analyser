"""FastAPI backend + static frontend for the dashboard.

Run with: uvicorn expense_analyser.api:app --reload
Point at a non-default database with the EXPENSE_DB_PATH env var.
"""

import os
from pathlib import Path
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from contextlib import asynccontextmanager

from expense_analyser.categorization import (
    CATEGORY_GROUPS,
    INCOME_CATEGORY,
    SEPARATE_CATEGORIES,
    _known_categories,
    normalize_description,
)
from expense_analyser.models import Transaction
from expense_analyser.reporting import _apply_category_groups, _monthly_breakdown
from expense_analyser.storage import TransactionRepository

DB_PATH = os.environ.get("EXPENSE_DB_PATH", "expenses.db")
STATIC_DIR = Path(__file__).parent / "static"

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.repo = TransactionRepository(DB_PATH)
    yield
    app.state.repo.connection.close()

app = FastAPI(title="Expense Analyser API", lifespan=lifespan)

def get_repo(request: Request) -> TransactionRepository:
    return request.app.state.repo


class MonthSummary(BaseModel):
    month: str
    expenditure: int
    separate_totals: dict[str, int]


class CategoryTotal(BaseModel):
    category: str
    total: int


class UpdateCategoryRequest(BaseModel):
    category: str


@app.get("/api/months", response_model=list[MonthSummary])
def list_months(repo: TransactionRepository = Depends(get_repo)) -> list[MonthSummary]:
    expenditure, separate = _monthly_breakdown(repo)
    return [
        MonthSummary(month=month, expenditure=total, separate_totals=separate.get(month, {}))
        for month, total in sorted(expenditure.items())
    ]


@app.get("/api/categories", response_model=list[str])
def list_known_categories(repo: TransactionRepository = Depends(get_repo)) -> list[str]:
    # _known_categories never includes group labels like "Train" in
    # practice (nothing is ever stored with that literal category —
    # see CATEGORY_GROUPS), but filter defensively anyway since a group
    # name is never a valid reassignment target.
    return [c for c in _known_categories(repo) if c not in CATEGORY_GROUPS]


@app.get("/api/months/{month}/categories", response_model=list[CategoryTotal])
def list_month_categories(
    month: str, repo: TransactionRepository = Depends(get_repo)
) -> list[CategoryTotal]:
    # Chart-only: excludes Income (not spend) and SEPARATE_CATEGORIES
    # (Stony Brook etc — real spend, but skews the chart). Still shown
    # everywhere else (hero figure, CLI reports, review_category).
    excluded = {INCOME_CATEGORY, *SEPARATE_CATEGORIES}
    return [
        CategoryTotal(category=category or "Uncategorized", total=total)
        for category, total in _apply_category_groups(repo.spend_by_category_for_month(month))
        if category not in excluded
    ]


@app.get("/api/months/{month}/categories/{group}", response_model=list[CategoryTotal])
def list_group_members(
    month: str, group: str, repo: TransactionRepository = Depends(get_repo)
) -> list[CategoryTotal]:
    # Empty list, not 404, when it's not a real group — frontend treats
    # "nothing back" as "no sub-breakdown for this bar".
    members = set(CATEGORY_GROUPS.get(group, []))
    if not members:
        return []
    return [
        CategoryTotal(category=category or "Uncategorized", total=total)
        for category, total in repo.spend_by_category_for_month(month)
        if category in members
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


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")