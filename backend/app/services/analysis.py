from pathlib import Path
from typing import Any
import json
import re

import pandas as pd
import numpy as np

from .anomalies import detect_anomalies_frame
from .intent import AnalysisIntent, fallback_intent
from .llm import classify_intent, generate_sql
from .query import execute_read_only


def _date_sql_expression(column: str) -> str:
    quoted = f'"{column}"'
    return (
        "TRY_CAST(CASE "
        f"WHEN regexp_matches(CAST({quoted} AS VARCHAR), '^[0-9]{{4}}-[0-9]{{2}}$') "
        f"THEN CAST({quoted} AS VARCHAR) || '-01' "
        f"ELSE CAST({quoted} AS VARCHAR) END AS DATE)"
    )


def _is_dataset_related(question: str, frame: pd.DataFrame) -> bool:
    lowered = question.lower()
    analytic_keywords = (
        "trend",
        "average",
        "mean",
        "sum",
        "total",
        "count",
        "highest",
        "lowest",
        "top",
        "bottom",
        "group",
        "compare",
        "distribution",
        "anomaly",
        "outlier",
        "missing",
        "null",
        "forecast",
        "predict",
        "data",
        "dataset",
        "summary",
        "summarize",
        "overview",
        "describe",
        "profile",
        "schema",
        "column",
        "row",
    )
    if any(keyword in lowered for keyword in analytic_keywords):
        return True

    question_tokens = {token for token in re.findall(r"[a-z0-9_]+", lowered) if len(token) > 2}
    if not question_tokens:
        return False

    schema_tokens: set[str] = set()
    for column in frame.columns:
        schema_tokens.update(token for token in re.findall(r"[a-z0-9_]+", str(column).lower()) if len(token) > 2)
    return bool(question_tokens & schema_tokens)


def answer_question(path: Path | list[Path], question: str) -> dict[str, Any]:
    paths = [path] if isinstance(path, Path) else path
    frames = [pd.read_csv(item).assign(_source_file=item.name) for item in paths]
    if len(frames) == 1:
        frame = frames[0]
    elif len({tuple(frame.columns) for frame in frames}) == 1:
        frame = pd.concat(frames, ignore_index=True)
    else:
        common = set(frames[0].columns)
        for candidate in frames[1:]:
            common &= set(candidate.columns)
        join_keys = [column for column in common if not pd.api.types.is_numeric_dtype(frames[0][column])]
        if join_keys:
            frame = frames[0]
            for candidate in frames[1:]:
                frame = frame.merge(candidate, on=join_keys, how="outer", suffixes=("", "_joined"))
        else:
            frame = pd.concat(frames, ignore_index=True, sort=False)
    if not _is_dataset_related(question, frame):
        return {
            "answer": "The question is not related to the dataset. Please ask about the uploaded data.",
            "method": "Matched the question against dataset schema and supported analysis intents.",
            "evidence": [],
            "chart": None,
            "intent": {
                "operation": "unrelated",
                "metric": None,
                "group_by": None,
                "time_column": None,
                "direction": "desc",
                "limit": 0,
                "source_files": [item.name for item in paths],
            },
            "skip_refinement": True,
        }
    fallback = fallback_intent(question, frame)
    if fallback.operation in {"data_quality", "anomaly"}:
        classified = None
    else:
        try:
            classified = classify_intent(question, frame)
        except Exception:
            classified = None
    intent = AnalysisIntent.from_payload(classified or fallback.__dict__, frame)
    result = execute_intent(frame, intent)
    if result.get("generated_sql"):
        fallback_sql = result["generated_sql"]
        if not result.get("report"):
            try:
                result["generated_sql"] = generate_sql(
                    question,
                    frame,
                    {
                        "operation": intent.operation,
                        "metric": intent.metric,
                        "group_by": intent.group_by,
                        "time_column": intent.time_column,
                        "direction": intent.direction,
                        "limit": intent.limit,
                    },
                    fallback_sql,
                )
            except Exception:
                result["generated_sql"] = fallback_sql
        try:
            result["sql_result"] = execute_read_only(frame, result["generated_sql"])
        except Exception as exc:
            result["sql_validation"] = f"Generated SQL was not executed after safety validation: {exc}"
    result["intent"] = {
        "operation": intent.operation,
        "metric": intent.metric,
        "group_by": intent.group_by,
        "time_column": intent.time_column,
        "direction": intent.direction,
        "limit": intent.limit,
        "source_files": [item.name for item in paths],
    }
    validate_result(result, intent)
    return result


def execute_intent(frame: pd.DataFrame, intent: AnalysisIntent) -> dict[str, Any]:
    if intent.operation == "summary":
        return build_summary_result(frame)
    if intent.operation == "data_quality":
        columns = [column for column in frame.columns if not str(column).startswith("_")]
        null_counts = frame[columns].isna().sum().sort_values(ascending=False)
        findings = [{"label": str(column), "value": int(count), "percent": round(float(count / len(frame) * 100), 2)} for column, count in null_counts.items() if count > 0]
        total_missing = int(null_counts.sum())
        if not findings:
            answer = f"No NULL or missing values were found across {len(columns)} columns and {len(frame):,} rows."
        else:
            affected_columns = len(findings)
            answer = f"I found {total_missing:,} missing cells across {affected_columns} columns. The most affected column is {findings[0]['label']} with {findings[0]['value']:,} missing values ({findings[0]['percent']:.2f}% of rows)."
        return {
            "answer": answer,
            "method": "Counted pandas NULL values per column and calculated each column's missing-row percentage.",
            "evidence": findings,
            "chart": {"type": "bar", "xKey": "label", "yKey": "value", "data": findings, "title": "Missing values by column"} if findings else None,
        }
    if intent.operation == "anomaly":
        anomaly_result = detect_anomalies_frame(frame)
        return {
            "answer": f"I flagged {anomaly_result['count']} potential anomal{'y' if anomaly_result['count'] == 1 else 'ies'} using the interquartile range rule.",
            "method": anomaly_result["method"],
            "evidence": [{"label": item["column"], "value": item["value"]} for item in anomaly_result["findings"][:8]],
            "anomalies": anomaly_result["findings"],
            "chart": None,
        }
    if intent.operation == "count":
        return {
            "answer": f"The dataset contains {len(frame):,} rows.",
            "method": "Counted parsed data rows after CSV validation.",
            "evidence": [{"label": "rows", "value": len(frame)}],
            "chart": None,
            "generated_sql": "SELECT COUNT(*) AS row_count FROM dataset;",
        }
    if intent.operation in {"trend", "forecast"} and intent.time_column and intent.metric:
        dated = frame[[intent.time_column, intent.metric]].copy()
        dated[intent.time_column] = pd.to_datetime(dated[intent.time_column], format="mixed", errors="coerce")
        dated = dated.dropna().assign(period=lambda values: values[intent.time_column].dt.to_period("M").astype(str))
        grouped = dated.groupby("period")[intent.metric].sum().sort_index().tail(12)
        if grouped.empty:
            return {
                "answer": f"I could not build a trend because no valid date and numeric-measure pairs were found for {intent.time_column} and {intent.metric}.",
                "method": "Trend validation removed rows with invalid dates or missing measures.",
                "evidence": [],
                "chart": None,
            }
        evidence = [{"label": str(index), "value": round(float(value), 2)} for index, value in grouped.items()]
        if intent.operation == "forecast":
            if len(grouped) < 2:
                return {"answer": "I need at least two time periods to produce a forecast.", "method": "Forecast validation", "evidence": [], "chart": None}
            x_values = np.arange(len(grouped), dtype=float)
            slope, intercept = np.polyfit(x_values, grouped.to_numpy(dtype=float), 1)
            forecast_data = [{"label": str(index), "value": round(float(value), 2), "kind": "actual"} for index, value in grouped.items()]
            last_period = pd.Period(grouped.index[-1], freq="M")
            for step in range(1, 4):
                period = last_period + step
                forecast_data.append({"label": str(period), "value": round(float(slope * (len(grouped) - 1 + step) + intercept), 2), "kind": "forecast"})
            return {
                "answer": f"The projected {intent.metric} value for {forecast_data[-1]['label']} is {forecast_data[-1]['value']:,.2f} based on the historical monthly trend.",
                "method": f"Monthly aggregation followed by a transparent least-squares linear trend projection for three periods.",
                "evidence": forecast_data[-3:],
                "chart": {"type": "line", "xKey": "label", "yKey": "value", "data": forecast_data, "title": f"{intent.metric} forecast"},
                "generated_sql": f"SELECT DATE_TRUNC('month', {_date_sql_expression(intent.time_column)}) AS month, SUM(\"{intent.metric}\") AS total FROM dataset WHERE {_date_sql_expression(intent.time_column)} IS NOT NULL GROUP BY month ORDER BY month;",
            }
        return {
            "answer": f"{intent.metric} totals {grouped.iloc[0]:,.2f} in {grouped.index[0]} and {grouped.iloc[-1]:,.2f} in {grouped.index[-1]}.",
            "method": f"Parsed {intent.time_column} as dates and summed {intent.metric} by month.",
            "evidence": evidence,
            "chart": {"type": "line", "xKey": "label", "yKey": "value", "data": evidence, "title": f"Monthly {intent.metric}"},
            "generated_sql": f"SELECT DATE_TRUNC('month', {_date_sql_expression(intent.time_column)}) AS month, SUM(\"{intent.metric}\") AS total FROM dataset WHERE {_date_sql_expression(intent.time_column)} IS NOT NULL GROUP BY month ORDER BY month;",
        }
    if intent.operation in {"trend", "forecast"}:
        return {
            "answer": "I could not find a separate numeric measure and time column for a trend analysis. This dataset has a year field, but no other numeric measure to trend.",
            "method": "Schema validation for trend analysis.",
            "evidence": [],
            "chart": None,
        }
    if intent.operation == "grouped_rank" and intent.group_by and intent.metric:
        grouped = frame.groupby(intent.group_by, dropna=False)[intent.metric].sum().sort_values(ascending=intent.direction == "asc").head(intent.limit)
        direction_label = "lowest" if intent.direction == "asc" else "highest"
        evidence = [{"label": str(index), "value": round(float(value), 2)} for index, value in grouped.items()]
        return {
            "answer": f"{grouped.index[0]} has the {direction_label} total {intent.metric}: {grouped.iloc[0]:,.2f}.",
            "method": f"Grouped sum of {intent.metric} by {intent.group_by}, sorted {intent.direction}ending.",
            "evidence": evidence,
            "chart": {"type": "bar", "xKey": "label", "yKey": "value", "data": evidence, "title": f"{intent.metric} by {intent.group_by}"},
            "generated_sql": f'SELECT "{intent.group_by}", SUM("{intent.metric}") AS total FROM dataset GROUP BY "{intent.group_by}" ORDER BY total {"ASC" if intent.direction == "asc" else "DESC"} LIMIT {intent.limit};',
        }
    if not intent.metric:
        return {"answer": "I could not find a numeric measure for that question.", "method": "Schema validation", "evidence": [], "chart": None}
    values = pd.to_numeric(frame[intent.metric], errors="coerce").dropna()
    if values.empty:
        return {
            "answer": f"I could not calculate statistics for {intent.metric} because it has no valid numeric values.",
            "method": f"Validated numeric values for the requested metric {intent.metric}.",
            "evidence": [],
            "chart": None,
        }
    summary = values.describe().round(2)
    evidence = [{"label": "mean", "value": float(summary["mean"])}]
    return {
        "answer": f"The dataset contains {len(frame):,} rows. Average {intent.metric}: {values.mean():,.2f}.",
        "method": f"Descriptive statistics for the requested metric {intent.metric}.",
        "evidence": evidence,
        "chart": None,
        "generated_sql": f'SELECT COUNT(*) AS rows, AVG("{intent.metric}") AS average FROM dataset;',
    }


def build_summary_result(frame: pd.DataFrame) -> dict[str, Any]:
    public_frame = frame[[column for column in frame.columns if not str(column).startswith("_")]]
    columns = []
    numeric_statistics = []
    categorical_statistics = []
    for name in public_frame.columns:
        series = public_frame[name]
        detail = {
            "name": str(name),
            "dtype": str(series.dtype),
            "rows": int(len(public_frame)),
            "non_null": int(series.notna().sum()),
            "nulls": int(series.isna().sum()),
            "null_rate": round(float(series.isna().mean() * 100), 2),
            "unique": int(series.nunique(dropna=True)),
            "sample": [str(value) for value in series.dropna().head(3).tolist()],
        }
        columns.append(detail)
        if pd.api.types.is_numeric_dtype(series):
            values = pd.to_numeric(series, errors="coerce").dropna()
            if not values.empty:
                numeric_statistics.append({
                    "column": str(name),
                    "count": int(values.count()),
                    "mean": round(float(values.mean()), 2),
                    "median": round(float(values.median()), 2),
                    "min": round(float(values.min()), 2),
                    "max": round(float(values.max()), 2),
                    "std": round(float(values.std()) if len(values) > 1 else 0.0, 2),
                })
        else:
            top_values = series.dropna().astype(str).value_counts().head(5)
            if not top_values.empty:
                categorical_statistics.append({
                    "column": str(name),
                    "unique": int(series.nunique(dropna=True)),
                    "top_values": [{"value": str(value), "count": int(count)} for value, count in top_values.items()],
                })

    report = {
        "overview": {
            "rows": int(len(frame)),
            "columns": int(len(frame.columns)),
            "duplicate_rows": int(frame.duplicated().sum()),
            "missing_cells": int(frame.isna().sum().sum()),
        },
        "schema": columns,
        "numeric_statistics": numeric_statistics,
        "categorical_statistics": categorical_statistics,
        "sample_rows": json.loads(public_frame.head(10).to_json(orient="records", date_format="iso")),
    }
    overview = report["overview"]
    if not numeric_statistics and not categorical_statistics:
        answer = (
            f"The dataset contains {overview['rows']:,} rows and {overview['columns']} columns, "
            "but no valid numeric values were available to calculate detailed statistics."
        )
    else:
        answer = (
            f"The dataset contains {overview['rows']:,} rows and {overview['columns']} columns. "
            f"It has {overview['missing_cells']:,} missing cells and {overview['duplicate_rows']:,} duplicate rows. "
            f"I processed the full schema, numeric statistics for {len(numeric_statistics)} columns, "
            f"and categorical distributions for {len(categorical_statistics)} columns."
        )
    evidence = [] if not numeric_statistics and not categorical_statistics else [
        {"label": "rows", "value": overview["rows"]},
        {"label": "columns", "value": overview["columns"]},
        {"label": "missing cells", "value": overview["missing_cells"]},
        {"label": "duplicate rows", "value": overview["duplicate_rows"]},
    ]
    return {
        "answer": answer,
        "method": "Processed the complete dataset schema, quality indicators, first 10 sample rows, numeric statistics, and categorical value distributions.",
        "evidence": evidence,
        "chart": None,
        "report": report,
        "generated_sql": "SELECT COUNT(*) AS rows FROM dataset;",
    }


def validate_result(result: dict[str, Any], intent: AnalysisIntent) -> None:
    valid_empty_explanation = result.get("method") in {"Schema validation for trend analysis.", "Trend validation removed rows with invalid dates or missing measures."}
    if intent.operation in {"grouped_rank", "trend", "forecast"} and not result.get("evidence") and not valid_empty_explanation:
        raise ValueError(f"No valid evidence was produced for {intent.operation} intent")
