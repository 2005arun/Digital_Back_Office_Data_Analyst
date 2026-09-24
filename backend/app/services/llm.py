import json
import re
from typing import Any

from openai import OpenAI

from ..config import get_settings


def classify_intent(question: str, frame: Any) -> dict[str, Any] | None:
    settings = get_settings()
    if not settings.groq_api_key:
        return None
    columns = [{"name": str(column), "dtype": str(frame[column].dtype)} for column in frame.columns]
    client = OpenAI(api_key=settings.groq_api_key, base_url="https://api.groq.com/openai/v1")
    prompt = (
        "Classify the user's data question into exactly one analysis plan. Return JSON only, with these keys: "
        "operation (summary|grouped_rank|trend|forecast|anomaly|data_quality|count), metric (column name or null), "
        "group_by (column name or null), time_column (column name or null), direction (asc|desc), limit (integer). "
        "Use only column names from the schema. Never invent a column. For highest/top use desc; for lowest/bottom use asc. "
        "Use grouped_rank for questions comparing categories, trend for time changes, forecast for future projections, anomaly for outliers, data_quality for null/missing/blank values, and count for row/category counts.\n\n"
        f"Schema: {json.dumps(columns)}\nQuestion: {question}"
    )
    response = client.chat.completions.create(
        model=settings.groq_model,
        temperature=0,
        max_tokens=180,
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": prompt}],
    )
    content = response.choices[0].message.content
    if not content:
        return None
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def generate_sql(question: str, frame: Any, intent: dict[str, Any], fallback_sql: str | None) -> str | None:
    settings = get_settings()
    if not settings.groq_api_key or not fallback_sql:
        return fallback_sql
    columns = [{"name": str(column), "dtype": str(frame[column].dtype)} for column in frame.columns]
    client = OpenAI(api_key=settings.groq_api_key, base_url="https://api.groq.com/openai/v1")
    prompt = (
        "Generate exactly one safe DuckDB SQL query. Return only the SQL text, without JSON, markdown, or explanation. "
        "The query must be read-only SELECT or WITH SQL and may query only the table dataset. "
        "Use only columns from the supplied schema. Do not include markdown fences or explanations. "
        "For CSV date strings, use TRY_CAST where needed. Preserve the requested analysis intent.\n\n"
        f"Schema: {json.dumps(columns)}\n"
        f"Intent: {json.dumps(intent)}\n"
        f"Question: {question}\n"
        f"Fallback plan SQL shape: {fallback_sql}"
    )
    response = client.chat.completions.create(
        model=settings.groq_model,
        temperature=0,
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    content = response.choices[0].message.content
    if not content:
        return fallback_sql
    text = content.strip()
    try:
        parsed = json.loads(text)
        text = parsed.get("sql", "") if isinstance(parsed, dict) else ""
    except json.JSONDecodeError:
        match = re.search(r"```(?:sql)?\s*(.*?)```", text, re.IGNORECASE | re.DOTALL)
        text = match.group(1).strip() if match else text
    return text if re.match(r"^(select|with)\b", text, re.IGNORECASE) else fallback_sql


def refine_answer(question: str, deterministic_result: dict[str, Any]) -> str | None:
    settings = get_settings()
    if not settings.groq_api_key:
        return None
    client = OpenAI(api_key=settings.groq_api_key, base_url="https://api.groq.com/openai/v1")
    evidence = deterministic_result.get("evidence", [])
    prompt = (
        "You are a careful business analyst. Rewrite the supplied result in 2-4 concise sentences. "
        "Use only the evidence provided, state the method briefly, and mention uncertainty if relevant. "
        "Do not invent values, hidden reasoning, or unsupported causes.\n\n"
        f"Question: {question}\nResult: {deterministic_result.get('answer')}\n"
        f"Method: {deterministic_result.get('method')}\nEvidence: {evidence}\n"
        f"Verified SQL result: {deterministic_result.get('sql_result', [])}"
    )
    response = client.chat.completions.create(
        model=settings.groq_model,
        temperature=0.1,
        max_tokens=220,
        messages=[{"role": "user", "content": prompt}],
    )
    content = response.choices[0].message.content
    return content.strip() if content else None
