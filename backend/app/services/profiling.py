import json
from pathlib import Path

import pandas as pd


def profile_csv(path: Path) -> dict:
    frame = pd.read_csv(path)
    columns = []
    for name in frame.columns:
        series = frame[name]
        columns.append({
            "name": str(name),
            "dtype": str(series.dtype),
            "nulls": int(series.isna().sum()),
            "null_rate": round(float(series.isna().mean()), 4),
            "unique": int(series.nunique(dropna=True)),
            "sample": [str(value) for value in series.dropna().head(3).tolist()],
        })
    return {
        "rows": int(len(frame)),
        "columns": int(len(frame.columns)),
        "duplicate_rows": int(frame.duplicated().sum()),
        "column_details": columns,
        "preview": json.loads(frame.head(8).to_json(orient="records", date_format="iso")),
    }
