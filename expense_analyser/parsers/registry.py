from expense_analyser.parsers.base import StatementParser

PARSER_REGISTRY: dict[str, type[StatementParser]] = {}