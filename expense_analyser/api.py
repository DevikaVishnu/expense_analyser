"""FastAPI backend serving transaction and spend-report data as JSON,
plus the static frontend that consumes it.

Mostly read-only: GET /api/months, GET /api/months/{month}/categories,
and GET /api/months/{month}/transactions expose the same data the CLI
reports already compute. The one write endpoint, PATCH
/api/transactions/{transaction_id}, reuses the same update_category +
set_merchant_rule pattern every CLI categorization tool already uses,
so a category fixed here behaves identically — built but not yet
wired into the frontend (view-only for this first pass).

Run with: uvicorn expense_analyser.api:app --reload
"""

from pathlib import Path
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from expense_analyser.categorization import CATEGORY_GROUPS, INCOME_CATEGORY, SEPARATE_CATEGORIES, normalize_description
from expense_analyser.models import Transaction
from expense_analyser.reporting import _apply_category_groups, _monthly_breakdown
from expense_analyser.storage import TransactionRepository

DB_PATH = "expenses.db"
STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Expense Analyser API")


def get_repo() -> TransactionRepository:
    return TransactionRepository(DB_PATH)


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


@app.get("/api/months/{month}/categories", response_model=list[CategoryTotal])
def list_month_categories(
    month: str, repo: TransactionRepository = Depends(get_repo)
) -> list[CategoryTotal]:
    # This endpoint's only consumer is the spend-by-category chart, so
    # unlike the CLI reports (which deliberately show everything for
    # review), it excludes INCOME_CATEGORY (not spend) and
    # SEPARATE_CATEGORIES (real spend, but large/irregular enough that
    # one bar dwarfs every other category and makes the chart useless).
    # Both stay fully visible elsewhere — the hero figure, the CLI
    # reports, and review_category.
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
    # Empty list (not a 404) for a name that isn't a CATEGORY_GROUPS
    # group — the frontend uses "got nothing back" to mean "this bar
    # isn't a group, don't show a sub-breakdown" rather than treating
    # every ordinary category as an error case.
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