from expense_analyser.formatting import format_amount


def test_format_amount_negative():
    assert format_amount(-1234) == "-$12.34"


def test_format_amount_positive():
    assert format_amount(1234) == "$12.34"


def test_format_amount_zero():
    assert format_amount(0) == "$0.00"