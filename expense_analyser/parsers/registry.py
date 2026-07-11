from expense_analyser.parsers.base import StatementParser
from expense_analyser.parsers.island_federal_statement import IslandFederalStatementParser

PARSER_REGISTRY: dict[str, type[StatementParser]] = {"bank_statement": IslandFederalStatementParser}
