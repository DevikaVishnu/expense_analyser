from abc import ABC, abstractmethod
from pathlib import Path
from expense_analyser.models import Transaction


class StatementParser(ABC):
    account_id: str
    statement_type: str

    @abstractmethod
    def parse(self, pdf_path: Path) -> list[Transaction]:
        pass
