from datetime import date

from expense_analyser.parsers.island_federal_statement import IslandFederalStatementParser


def test_normalize_amount():
    assert IslandFederalStatementParser._normalize_amount("300.00-") == "-300.00"
    assert IslandFederalStatementParser._normalize_amount("2,650.00") == "2650.00"
    assert IslandFederalStatementParser._normalize_amount("4.00") == "4.00"


def test_is_money_token():
    assert IslandFederalStatementParser._is_money_token("10.01-") is True
    assert IslandFederalStatementParser._is_money_token("2,493.57") is True
    assert IslandFederalStatementParser._is_money_token("4.00") is True
    assert IslandFederalStatementParser._is_money_token("DEBIT") is False
    assert IslandFederalStatementParser._is_money_token("NEW") is False


def test_build_one_line_transaction():
    parser = IslandFederalStatementParser()
    line = "OCT06 DEPOSIT Incoming Wire Transfer-236775089 2,650.00 3,279.64"
    match = IslandFederalStatementParser.DATE_TOKEN.match(line)
    rest_tokens = match.group("rest").split()

    txn = parser._build_one_line_transaction(match, rest_tokens, "test.pdf", 2025)

    assert txn.transaction_date == date(2025, 10, 6)
    assert txn.amount == 265000
    assert txn.balance == 327964
    assert txn.description == "DEPOSIT Incoming Wire Transfer-236775089"
    assert txn.account_id == "IslandFederal_checking"
    assert txn.source_file == "test.pdf"


def test_build_two_line_transaction():
    parser = IslandFederalStatementParser()
    line = "DEC31E DEBIT CARD DEBIT 10.01- 2,493.57"
    next_line = "000889484674 UBER *TRIP 706 MISSION ST 8005928996 C 12-31-25"
    match = IslandFederalStatementParser.DATE_TOKEN.match(line)
    rest_tokens = match.group("rest").split()

    txn = parser._build_two_line_transaction(match, rest_tokens, next_line, "test.pdf")

    assert txn.transaction_date == date(2025, 12, 31)
    assert txn.amount == -1001
    assert txn.balance == 249357
    assert txn.description == "UBER *TRIP 706 MISSION ST 8005928996 C"


def test_parse_lines_handles_all_known_shapes():
    parser = IslandFederalStatementParser()
    lines = [
        "NON-DIVIDEND CHECK. ACCT ACCT# 2 10-01-25 THRU 10-31-25 PREVIOUS $2,500.00",
        "DEC31E DEBIT CARD DEBIT 10.01- 2,493.57",
        "000889484674 UBER *TRIP 706 MISSION ST 8005928996 C 12-31-25",
        "OCT06 DEPOSIT Incoming Wire Transfer-236775089 2,650.00 3,279.64",
        "OCT31 NEW BALANCE 3,279.64",
        "OCT31 SOMETHING WEIRD WITH NO AMOUNT",
    ]

    transactions, unparsed = parser._parse_lines(lines, "test.pdf")

    assert len(transactions) == 2
    assert len(unparsed) == 1
    assert "SOMETHING WEIRD" in unparsed[0]