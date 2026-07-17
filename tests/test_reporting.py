from datetime import date

from expense_analyser.categorization import INCOME_CATEGORY
from expense_analyser.models import Transaction
from expense_analyser.reporting import (
    _apply_category_groups,
    _monthly_breakdown,
    generate_reports,
    print_spend_by_category,
    print_spend_by_month,
    print_spend_by_month_and_category,
    write_csv,
    write_month_category_csv,
)
from expense_analyser.storage import TransactionRepository


def _make_transaction(**overrides) -> Transaction:
    defaults = dict(
        account_id="test",
        transaction_date=date(2026, 1, 15),
        description="Test",
        amount=-500,
        currency="USD",
        source_file="test.pdf",
    )
    defaults.update(overrides)
    return Transaction(**defaults)


def test_print_spend_by_category_shows_uncategorized_label(capsys):
    repo = TransactionRepository(":memory:")
    repo.insert(_make_transaction(amount=-500, category=None))

    print_spend_by_category(repo)

    out = capsys.readouterr().out
    assert "Uncategorized" in out
    assert "-$5.00" in out


def test_print_spend_by_category_shows_real_category(capsys):
    repo = TransactionRepository(":memory:")
    repo.insert(_make_transaction(amount=-500, category="Groceries"))

    print_spend_by_category(repo)

    out = capsys.readouterr().out
    assert "Groceries" in out
    assert "-$5.00" in out


# --- category groups ---


def test_apply_category_groups_combines_members_into_group_total():
    rows = [("Subway", -500), ("Amtrak", -300), ("LIRR", -200), ("Groceries", -100)]

    grouped = _apply_category_groups(rows)

    assert dict(grouped) == {"Train": -1000, "Groceries": -100}


def test_apply_category_groups_leaves_ungrouped_and_uncategorized_alone():
    rows = [("Groceries", -500), (None, -300)]

    grouped = _apply_category_groups(rows)

    assert dict(grouped) == {"Groceries": -500, None: -300}


def test_print_spend_by_category_shows_train_rollup(capsys):
    repo = TransactionRepository(":memory:")
    repo.insert(_make_transaction(amount=-500, category="Subway"))
    repo.insert(_make_transaction(amount=-300, category="Amtrak"))
    repo.insert(_make_transaction(amount=-200, category="LIRR"))

    print_spend_by_category(repo)

    out = capsys.readouterr().out
    assert "Train" in out
    assert "-$10.00" in out
    assert "Subway" not in out
    assert "Amtrak" not in out
    assert "LIRR" not in out


def test_print_spend_by_month_groups_by_month(capsys):
    repo = TransactionRepository(":memory:")
    repo.insert(_make_transaction(transaction_date=date(2026, 1, 5), amount=-500))
    repo.insert(_make_transaction(transaction_date=date(2026, 2, 5), amount=-300))

    print_spend_by_month(repo)

    out = capsys.readouterr().out
    assert "2026-01" in out
    assert "2026-02" in out


def test_monthly_breakdown_excludes_income_from_expenditure():
    repo = TransactionRepository(":memory:")
    repo.insert(_make_transaction(transaction_date=date(2026, 1, 5), amount=-500, category="Groceries"))
    repo.insert(_make_transaction(transaction_date=date(2026, 1, 10), amount=265000, category=INCOME_CATEGORY))

    expenditure, separate = _monthly_breakdown(repo)

    assert expenditure["2026-01"] == -500
    assert separate == {}


def test_monthly_breakdown_moves_separate_categories_out_of_expenditure():
    repo = TransactionRepository(":memory:")
    repo.insert(_make_transaction(transaction_date=date(2026, 1, 5), amount=-500, category="Groceries"))
    repo.insert(_make_transaction(transaction_date=date(2026, 1, 10), amount=-1190069, category="Stony Brook"))

    expenditure, separate = _monthly_breakdown(repo)

    assert expenditure["2026-01"] == -500
    assert separate["2026-01"] == {"Stony Brook": -1190069}


def test_monthly_breakdown_includes_regular_categories():
    repo = TransactionRepository(":memory:")
    repo.insert(_make_transaction(transaction_date=date(2026, 1, 5), amount=-500, category="Groceries"))
    repo.insert(_make_transaction(transaction_date=date(2026, 1, 10), amount=-300, category="Eat Out"))

    expenditure, _ = _monthly_breakdown(repo)

    assert expenditure["2026-01"] == -800


def test_print_spend_by_month_shows_separate_category_total(capsys):
    repo = TransactionRepository(":memory:")
    repo.insert(_make_transaction(transaction_date=date(2026, 1, 5), amount=-500, category="Groceries"))
    repo.insert(_make_transaction(transaction_date=date(2026, 1, 10), amount=-1190069, category="Stony Brook"))

    print_spend_by_month(repo)

    out = capsys.readouterr().out
    assert "-$5.00" in out
    assert "Stony Brook: -$11900.69" in out


def test_print_spend_by_category_still_shows_income_and_separate_categories(capsys):
    # The per-category breakdown is unaffected by the expenditure
    # exclusion — Income and Stony Brook still appear as their own
    # rows there, just not folded into the monthly headline total.
    repo = TransactionRepository(":memory:")
    repo.insert(_make_transaction(transaction_date=date(2026, 1, 5), amount=265000, category=INCOME_CATEGORY))
    repo.insert(_make_transaction(transaction_date=date(2026, 1, 10), amount=-1190069, category="Stony Brook"))

    print_spend_by_category(repo)

    out = capsys.readouterr().out
    assert INCOME_CATEGORY in out
    assert "Stony Brook" in out


def test_print_spend_by_month_and_category_prints_month_header_once_per_month(capsys):
    repo = TransactionRepository(":memory:")
    repo.insert(_make_transaction(transaction_date=date(2026, 1, 5), amount=-500, category="Groceries"))
    repo.insert(_make_transaction(transaction_date=date(2026, 1, 10), amount=-300, category="Eat Out"))

    print_spend_by_month_and_category(repo)

    out = capsys.readouterr().out
    assert out.count("2026-01 (expenditure:") == 1
    assert "Groceries" in out
    assert "Eat Out" in out


def test_print_spend_by_month_and_category_shows_month_total(capsys):
    repo = TransactionRepository(":memory:")
    repo.insert(_make_transaction(transaction_date=date(2026, 1, 5), amount=-500, category="Groceries"))
    repo.insert(_make_transaction(transaction_date=date(2026, 1, 10), amount=-300, category="Eat Out"))

    print_spend_by_month_and_category(repo)

    out = capsys.readouterr().out
    assert "2026-01 (expenditure: -$8.00):" in out


def test_print_spend_by_month_and_category_separates_multiple_months(capsys):
    repo = TransactionRepository(":memory:")
    repo.insert(_make_transaction(transaction_date=date(2026, 1, 5), amount=-500, category="Groceries"))
    repo.insert(_make_transaction(transaction_date=date(2026, 2, 5), amount=-300, category="Groceries"))

    print_spend_by_month_and_category(repo)

    out = capsys.readouterr().out
    assert out.count("2026-01 (expenditure:") == 1
    assert out.count("2026-02 (expenditure:") == 1


def test_print_spend_by_month_and_category_shows_train_rollup(capsys):
    repo = TransactionRepository(":memory:")
    repo.insert(_make_transaction(transaction_date=date(2026, 1, 5), amount=-500, category="Subway"))
    repo.insert(_make_transaction(transaction_date=date(2026, 1, 10), amount=-300, category="Amtrak"))

    print_spend_by_month_and_category(repo)

    out = capsys.readouterr().out
    assert "Train" in out
    assert "-$8.00" in out
    assert "Subway" not in out
    assert "Amtrak" not in out


def test_write_csv_creates_directory_and_file(tmp_path):
    path = tmp_path / "nested" / "spend_by_category.csv"

    write_csv([("Groceries", -500), (None, -300)], ["category", "total"], path)

    content = path.read_text()
    assert "category,total" in content
    assert "Groceries,-5.00" in content
    assert "Uncategorized,-3.00" in content


def test_write_month_category_csv(tmp_path):
    path = tmp_path / "spend_by_month_and_category.csv"

    write_month_category_csv([("2026-01", "Groceries", -500), ("2026-01", None, -300)], path)

    content = path.read_text()
    assert "month,category,total" in content
    assert "2026-01,Groceries,-5.00" in content
    assert "2026-01,Uncategorized,-3.00" in content


def test_generate_reports_writes_all_three_csv_files(tmp_path):
    repo = TransactionRepository(":memory:")
    repo.insert(_make_transaction(amount=-500, category="Groceries"))

    generate_reports(repo, tmp_path)

    assert (tmp_path / "spend_by_category.csv").exists()
    assert (tmp_path / "spend_by_month.csv").exists()
    assert (tmp_path / "spend_by_month_and_category.csv").exists()