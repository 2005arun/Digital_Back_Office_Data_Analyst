from pathlib import Path

from app.services.anomalies import detect_anomalies


def test_iqr_anomaly_detection(tmp_path: Path):
    dataset = tmp_path / "metrics.csv"
    dataset.write_text("value\n10\n11\n12\n13\n100\n", encoding="utf-8")
    result = detect_anomalies(dataset)
    assert result["count"] == 1
    assert result["findings"][0]["value"] == 100
