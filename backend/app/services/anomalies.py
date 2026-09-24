from pathlib import Path

import pandas as pd


def detect_anomalies(path: Path) -> dict:
    return detect_anomalies_frame(pd.read_csv(path))


def detect_anomalies_frame(frame: pd.DataFrame) -> dict:
    findings = []
    for column in frame.select_dtypes(include="number").columns:
        values = frame[column].dropna()
        if len(values) < 4:
            continue
        first_quartile, third_quartile = values.quantile([0.25, 0.75])
        spread = third_quartile - first_quartile
        if spread == 0:
            continue
        lower, upper = first_quartile - 1.5 * spread, third_quartile + 1.5 * spread
        mask = (frame[column] < lower) | (frame[column] > upper)
        for index, value in frame.loc[mask, column].items():
            findings.append({"row": int(index), "column": str(column), "value": float(value), "reason": f"Outside IQR bounds ({lower:.2f}, {upper:.2f})"})
    return {"count": len(findings), "method": "1.5x IQR rule per numeric column", "findings": findings[:100]}
