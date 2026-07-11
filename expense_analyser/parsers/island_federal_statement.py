import re
from datetime import datetime
from decimal import InvalidOperation
from pathlib import Path

import pdfplumber
from pydantic import ValidationError

from expense_analyser.models import Transaction
from expense_analyser.parsers.base import StatementParser


class IslandFederalStatementParser(StatementParser):
    account_id = "IslandFederal_checking"
    statement_type = "checking"
    currency = "USD"

    DATE_TOKEN = re.compile(
        r"^(?P<month>JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)"
        r"(?P<day>\d{1,2})[A-Z]?\s+(?P<rest>.+)$"
    )
    MONEY_TOKEN = re.compile(r"^[\d,]+\.\d{2}-?$")
    STATEMENT_PERIOD = re.compile(r"THRU\s+\d{2}-\d{2}-(?P<year>\d{2})")

    def parse(self, pdf_path: Path) -> list[Transaction]:
        lines: list[str] = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                lines.extend(text.split("\n"))

        transactions, unparsed = self._parse_lines(lines, pdf_path.name)
        for warning in unparsed:
            print(f"Warning: could not parse in {pdf_path.name}: {warning}")

        return transactions

    def _parse_lines(self, lines: list[str], source_file: str) -> tuple[list[Transaction], list[str]]:
        full_text = "\n".join(lines)
        period_match = self.STATEMENT_PERIOD.search(full_text)
        if not period_match:
            raise ValueError(f"Could not find statement period in {source_file}")
        year = 2000 + int(period_match.group("year"))

        transactions: list[Transaction] = []
        unparsed: list[str] = []
        i = 0

        while i < len(lines):
            line = lines[i].strip()
            match = self.DATE_TOKEN.match(line)

            if not match:
                i += 1  # doesn't start with a date token — boilerplate
                continue

            rest_tokens = match.group("rest").split()

            if rest_tokens[:2] == ["NEW", "BALANCE"]:
                i += 1  # known, expected non-transaction line
                continue

            elif rest_tokens[:2] == ["DEBIT", "CARD"] and i + 1 < len(lines):
                try:
                    transactions.append(
                        self._build_two_line_transaction(match, rest_tokens, lines[i + 1], source_file)
                    )
                except (ValueError, ValidationError, InvalidOperation) as e:
                    unparsed.append(f"lines {i}-{i + 1}: {line!r} / {lines[i + 1]!r} ({e})")
                i += 2

            elif len(rest_tokens) >= 2 and self._is_money_token(rest_tokens[-1]) and self._is_money_token(rest_tokens[-2]):
                try:
                    transactions.append(
                        self._build_one_line_transaction(match, rest_tokens, source_file, year)
                    )
                except (ValueError, ValidationError, InvalidOperation) as e:
                    unparsed.append(f"line {i}: {line!r} ({e})")
                i += 1

            else:
                unparsed.append(f"line {i}: {line!r} (unrecognized shape)")
                i += 1

        return transactions, unparsed

    def _build_one_line_transaction(self, match, rest_tokens, source_file, year) -> Transaction:
        transaction_date = datetime.strptime(
            f"{match.group('month')} {match.group('day')} {year}", "%b %d %Y"
        ).date()

        amount_str = rest_tokens[-2]
        balance_str = rest_tokens[-1]
        description = " ".join(rest_tokens[:-2])

        txn = Transaction(
            account_id=self.account_id,
            transaction_date=transaction_date,
            description=description,
            amount=Transaction.from_raw_amount(self._normalize_amount(amount_str)),
            currency=self.currency,
            balance=Transaction.from_raw_amount(self._normalize_amount(balance_str)),
            source_file=source_file,
            dedup_hash="",
        )
        return txn

    def _build_two_line_transaction(self, match, rest_tokens, next_line, source_file) -> Transaction:
        amount_str = rest_tokens[-2]
        balance_str = rest_tokens[-1]

        next_tokens = next_line.strip().split()
        date_str = next_tokens[-1]
        description = " ".join(next_tokens[1:-1])

        transaction_date = datetime.strptime(date_str, "%m-%d-%y").date()

        txn = Transaction(
            account_id=self.account_id,
            transaction_date=transaction_date,
            description=description,
            amount=Transaction.from_raw_amount(self._normalize_amount(amount_str)),
            currency=self.currency,
            balance=Transaction.from_raw_amount(self._normalize_amount(balance_str)),
            source_file=source_file,
            dedup_hash="",
        )
        return txn

    @classmethod
    def _is_money_token(cls, token: str) -> bool:
        return bool(cls.MONEY_TOKEN.match(token))

    @staticmethod
    def _normalize_amount(raw: str) -> str:
        cleaned = raw.replace(",", "")
        if cleaned.endswith("-"):
            cleaned = "-" + cleaned[:-1]
        return cleaned