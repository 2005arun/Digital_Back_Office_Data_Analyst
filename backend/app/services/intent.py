from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class AnalysisIntent:
    operation: str
    metric: str | None = None
    group_by: str | None = None
    time_column: str | None = None
    direction: str = "desc"
    limit: int = 5

    @classmethod
    def from_payload(cls, payload: dict[str, Any], frame: pd.DataFrame) -> "AnalysisIntent":
        columns = {str(column) for column in frame.columns}
        numeric = [str(column) for column in frame.select_dtypes(include="number").columns]
        operation = str(payload.get("operation", "summary")).lower()
        if operation not in {"summary", "grouped_rank", "trend", "forecast", "anomaly", "data_quality", "count"}:
            operation = "summary"
        metric = payload.get("metric")
        group_by = payload.get("group_by")
        time_column = payload.get("time_column")
        metric = None if operation == "data_quality" else (str(metric) if metric in columns and metric in numeric else (numeric[0] if numeric else None))
        group_by = str(group_by) if group_by in columns else None
        time_column = str(time_column) if time_column in columns else None
        if operation in {"trend", "forecast"} and metric == time_column:
            alternatives = [column for column in numeric if column != time_column]
            metric = alternatives[0] if alternatives else None
        direction = "asc" if str(payload.get("direction", "desc")).lower() == "asc" else "desc"
        try:
            limit = max(1, min(20, int(payload.get("limit", 5))))
        except (TypeError, ValueError):
            limit = 5
        return cls(operation, metric, group_by, time_column, direction, limit)


def fallback_intent(question: str, frame: pd.DataFrame) -> AnalysisIntent:
    lowered = question.lower()
    columns = [str(column) for column in frame.columns]
    numeric = [str(column) for column in frame.select_dtypes(include="number").columns]
    categorical = [str(column) for column in frame.select_dtypes(exclude="number").columns]
    def find_column(words: tuple[str, ...], pool: list[str]) -> str | None:
        for column in pool:
            normalized = column.lower().replace("_", " ")
            if any(word in normalized for word in words):
                return column
        return None

    metric = next((column for column in numeric if column.lower() in lowered or column.lower().replace("_", " ") in lowered), None)
    metric = metric or find_column(("revenue", "sales", "amount", "profit", "total", "quantity"), numeric) or (numeric[0] if numeric else None)
    group_by = next((column for column in categorical if column.lower() in lowered or column.lower().replace("_", " ") in lowered), None)
    group_by = group_by or find_column(("region", "product", "customer", "category", "segment", "department"), categorical)
    time_column = find_column(("date", "month", "year", "time", "period"), columns)
    if time_column == metric:
        alternatives = [column for column in numeric if column != time_column]
        metric = alternatives[0] if alternatives else None
    direction = "asc" if any(word in lowered for word in ("lowest", "least", "underperforming", "worst", "smallest")) else "desc"
    if any(word in lowered for word in ("summary", "summarize", "overview", "describe", "profile", "schema", "columns")):
        operation = "summary"
    elif any(word in lowered for word in ("null", "missing", "blank", "empty", "data quality", "completeness")):
        operation = "data_quality"
    elif any(word in lowered for word in ("anomal", "outlier", "unusual")):
        operation = "anomaly"
    elif any(word in lowered for word in ("forecast", "predict", "projection", "future")):
        operation = "forecast"
    elif any(word in lowered for word in ("trend", "monthly", "weekly", "over time", "by month")):
        operation = "trend"
    elif any(word in lowered for word in ("highest", "lowest", "top", "bottom", "best", "worst", "underperforming")) and group_by:
        operation = "grouped_rank"
    elif any(word in lowered for word in ("how many", "count", "number of")):
        operation = "count"
    else:
        operation = "summary"
    return AnalysisIntent(operation, metric, group_by, time_column, direction, 5)
