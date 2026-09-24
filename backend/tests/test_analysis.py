from pathlib import Path

import pandas as pd

from app.services.analysis import answer_question, execute_intent
from app.services.intent import AnalysisIntent
from app.services.profiling import profile_csv
from app.services.query import execute_read_only


def test_profile_and_grouped_answer(tmp_path: Path):
    dataset = tmp_path / "sales.csv"
    dataset.write_text("region,revenue\nNorth,100\nSouth,240\nNorth,50\n", encoding="utf-8")

    profile = profile_csv(dataset)
    result = answer_question(dataset, "Which region generated the highest revenue?")

    assert profile["rows"] == 3
    assert profile["duplicate_rows"] == 0
    assert result["answer"].startswith("South has the highest total revenue")
    assert result["chart"]["type"] == "bar"


def test_intent_uses_requested_product_and_metric(tmp_path: Path):
    dataset = tmp_path / "products.csv"
    dataset.write_text(
        "region,product,units,profit\nNorth,A,10,40\nSouth,B,80,15\nNorth,B,5,30\n",
        encoding="utf-8",
    )

    result = answer_question(dataset, "Which product has the lowest profit?")

    assert result["intent"]["operation"] == "grouped_rank"
    assert result["intent"]["group_by"] == "product"
    assert result["intent"]["metric"] == "profit"
    assert result["intent"]["direction"] == "asc"
    assert result["answer"].startswith("A has the lowest total profit")


def test_multi_file_workspace_unions_matching_schemas(tmp_path: Path):
    first = tmp_path / "north.csv"
    second = tmp_path / "south.csv"
    first.write_text("region,revenue\nNorth,100\n", encoding="utf-8")
    second.write_text("region,revenue\nSouth,240\n", encoding="utf-8")

    result = answer_question([first, second], "Which region generated the highest revenue?")

    assert result["answer"].startswith("South has the highest total revenue")
    assert result["intent"]["source_files"] == ["north.csv", "south.csv"]
    assert result["sql_result"][0]["total"] == 240.0


def test_null_question_returns_data_quality_result(tmp_path: Path):
    dataset = tmp_path / "quality.csv"
    dataset.write_text("year,region,revenue\n2022,North,100\n,South,240\n2024,,180\n", encoding="utf-8")

    result = answer_question(dataset, "NULL values are present in the dataset")

    assert result["intent"]["operation"] == "data_quality"
    assert result["intent"]["metric"] is None
    assert result["answer"].startswith("I found 2 missing cells")
    assert result["evidence"][0]["label"] in {"year", "region"}
    assert result["chart"]["type"] == "bar"


def test_trend_without_measure_returns_validation_answer(tmp_path: Path):
    dataset = tmp_path / "catalog.csv"
    dataset.write_text("year,industry\n2023,Technology\n2024,Finance\n", encoding="utf-8")

    result = answer_question(dataset, "Show me the main trends in this data.")

    assert result["intent"]["operation"] == "trend"
    assert result["intent"]["metric"] is None
    assert "separate numeric measure" in result["answer"]


def test_trend_schema_validation_does_not_fail_metric_reference_check():
    frame = pd.DataFrame({"year": [2023, 2024], "industry": ["Technology", "Finance"]})
    result = execute_intent(frame, AnalysisIntent("trend", metric=None, time_column="year"))

    result["intent"] = {"metric": None}
    from app.services.analysis import validate_result

    validate_result(result, AnalysisIntent("trend", metric=None, time_column="year"))


def test_unrelated_question_returns_dataset_relevance_message(tmp_path: Path):
    dataset = tmp_path / "survey.csv"
    dataset.write_text("region,revenue\nNorth,10\nSouth,20\n", encoding="utf-8")

    result = answer_question(dataset, "how are you doing today")

    assert result["intent"]["operation"] == "unrelated"
    assert result["answer"] == "The question is not related to the dataset. Please ask about the uploaded data."
    assert result["evidence"] == []


def test_summary_with_all_missing_numeric_values_is_json_safe():
    frame = pd.DataFrame({"revenue": [None, None]})
    result = execute_intent(frame, AnalysisIntent("summary", metric="revenue"))

    assert result["evidence"] == []
    assert "no valid numeric values" in result["answer"]


def test_summary_returns_full_report_and_processed_schema(tmp_path: Path):
    dataset = tmp_path / "sales.csv"
    dataset.write_text("region,revenue\nNorth,100\nSouth,240\nNorth,50\n", encoding="utf-8")

    result = answer_question(dataset, "Give me a complete summary of this dataset")

    assert result["intent"]["operation"] == "summary"
    assert result["report"]["overview"]["rows"] == 3
    assert len(result["report"]["schema"]) == 2
    assert result["report"]["numeric_statistics"][0]["column"] == "revenue"
    assert len(result["report"]["sample_rows"]) == 3
    assert result["sql_result"] == [{"rows": 3}]


def test_trend_with_invalid_dates_returns_validation_answer():
    frame = pd.DataFrame({"date": ["not-a-date", "also-invalid"], "sales": [10, 20]})
    result = execute_intent(frame, AnalysisIntent("trend", metric="sales", time_column="date"))

    assert result["evidence"] == []
    assert "no valid date" in result["answer"]


def test_query_validator_allows_select_and_rejects_writes():
    frame = pd.DataFrame({"region": ["North"], "revenue": [100]})

    assert execute_read_only(frame, "SELECT region, revenue FROM dataset") == [{"region": "North", "revenue": 100}]

    try:
        execute_read_only(frame, "DELETE FROM dataset")
    except ValueError as exc:
        assert "SELECT or WITH" in str(exc)
    else:
        raise AssertionError("write query should be rejected")


def test_trend_sql_casts_csv_date_strings_for_duckdb():
    frame = pd.DataFrame({"Date of birth": ["2010-01", "2010-02"], "Index": [62, 66]})
    result = execute_intent(frame, AnalysisIntent("trend", metric="Index", time_column="Date of birth"))

    assert result["generated_sql"] is not None
    assert "TRY_CAST" in result["generated_sql"]
    assert execute_read_only(frame, result["generated_sql"]) == [
        {"month": pd.Timestamp("2010-01-01"), "total": 62.0},
        {"month": pd.Timestamp("2010-02-01"), "total": 66.0},
    ]


def test_offline_pipeline_keeps_safe_sql_fallback_and_verified_result(tmp_path: Path):
    dataset = tmp_path / "sales.csv"
    dataset.write_text("region,revenue\nNorth,100\nSouth,240\n", encoding="utf-8")

    result = answer_question(dataset, "Which region generated the highest revenue?")

    assert result["generated_sql"].startswith("SELECT")
    assert result["sql_result"][0]["region"] == "South"
    assert result.get("sql_validation") is None
