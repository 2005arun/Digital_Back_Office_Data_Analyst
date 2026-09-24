import re
from typing import Any

import duckdb
import pandas as pd


_FORBIDDEN = re.compile(r"\b(insert|update|delete|drop|alter|create|copy|attach|install|load|pragma)\b", re.IGNORECASE)
_TABLE_REFERENCE = re.compile(r"\b(?:from|join)\s+([`\"\w.]+)", re.IGNORECASE)


def validate_read_only_sql(frame: pd.DataFrame, sql: str) -> None:
    statement = sql.strip()
    if not statement:
        raise ValueError("Generated SQL is empty")
    if statement.count(";") > 1 or (";" in statement and not statement.rstrip().endswith(";")):
        raise ValueError("Only one read-only SQL statement is allowed")
    if not re.match(r"^(select|with)\b", statement, re.IGNORECASE):
        raise ValueError("Only SELECT or WITH SQL is allowed")
    if _FORBIDDEN.search(statement):
        raise ValueError("Only read-only analytical SQL is allowed")

    references = _TABLE_REFERENCE.findall(statement)
    tables = {reference.strip("`\"").split(".")[-1].lower() for reference in references}
    if tables and tables != {"dataset"}:
        raise ValueError("SQL may only query the uploaded dataset")

    connection = duckdb.connect(database=":memory:")
    try:
        connection.register("dataset", frame)
        connection.execute(f"EXPLAIN {statement.rstrip(';')}")
    finally:
        connection.close()


def execute_read_only(frame: pd.DataFrame, sql: str) -> list[dict[str, Any]]:
    validate_read_only_sql(frame, sql)
    connection = duckdb.connect(database=":memory:")
    try:
        connection.register("dataset", frame)
        result = connection.execute(sql.rstrip(";")).fetchdf()
        return result.where(pd.notna(result), None).to_dict(orient="records")
    finally:
        connection.close()
