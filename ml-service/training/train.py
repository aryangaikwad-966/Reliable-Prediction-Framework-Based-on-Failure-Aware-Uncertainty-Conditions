from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from xgboost import XGBRegressor

from training.features import FEATURES, add_features, normalize_columns


def read_dataset(path: str, commodity: str, market: str | None = None) -> pd.DataFrame:
    chunks = []
    for chunk in pd.read_csv(path, chunksize=100_000, low_memory=False):
        normalized = normalize_columns(chunk)
        filtered = normalized[normalized["commodity"].str.casefold() == commodity.casefold()]
        if market:
            filtered = filtered[filtered["market"].str.casefold() == market.casefold()]
        if not filtered.empty:
            chunks.append(filtered)
    if not chunks:
        raise ValueError("No rows matched the requested commodity/market.")
    return pd.concat(chunks, ignore_index=True)


def train_model(data_path: str, commodity: str, market: str | None, horizon: int, test_fraction: float, model_dir: Path) -> dict:
    frame = add_features(read_dataset(data_path, commodity, market), horizon)
    frame = frame.sort_values("report_date")
    split = max(1, int(len(frame) * (1 - test_fraction)))
    train, test = frame.iloc[:split], frame.iloc[split:]
    if len(train) < 20 or len(test) < 1:
        raise ValueError("Not enough chronological observations after feature engineering.")
    model = XGBRegressor(n_estimators=250, max_depth=5, learning_rate=0.05, subsample=0.85, colsample_bytree=0.85, objective="reg:squarederror", random_state=42)
    model.fit(train[FEATURES], train["target"])
    predictions = model.predict(test[FEATURES])
    metrics = {
        "mae": float(mean_absolute_error(test["target"], predictions)),
        "rmse": float(mean_squared_error(test["target"], predictions) ** 0.5),
        "r2": float(r2_score(test["target"], predictions)),
        "rows": int(len(frame)),
        "train_rows": int(len(train)),
        "test_rows": int(len(test)),
        "training_start": str(train["report_date"].min().date()),
        "training_end": str(train["report_date"].max().date()),
    }
    model_dir.mkdir(parents=True, exist_ok=True)
    artifact = {
        "model": model,
        "features": FEATURES,
        "feature_means": train[FEATURES].mean().astype(float).tolist(),
        "feature_scales": train[FEATURES].std().replace(0, 1).astype(float).tolist(),
        "model_uncertainty": float(np.std(test["target"].to_numpy() - predictions) / max(np.mean(test["target"]), 1)),
        "metrics": metrics,
        "metadata": {"commodity": commodity, "market": market, "horizon": horizon, "trained_at": datetime.now(timezone.utc).isoformat()},
    }
    version = f"{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{commodity.lower()}"
    joblib.dump(artifact, model_dir / f"{version}.joblib")
    joblib.dump(artifact, model_dir / "latest.joblib")
    (model_dir / f"{version}.json").write_text(json.dumps({**metrics, **artifact["metadata"], "version": version}, indent=2))
    return {"status": "TRAINED", "version": version, "artifact": str(model_dir / f"{version}.joblib"), "metrics": metrics}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    parser.add_argument("--commodity", default="Tomato")
    parser.add_argument("--market")
    parser.add_argument("--horizon", type=int, default=7)
    parser.add_argument("--test-fraction", type=float, default=0.2)
    parser.add_argument("--model-dir", default="./models")
    args = parser.parse_args()
    print(json.dumps(train_model(args.data, args.commodity, args.market, args.horizon, args.test_fraction, Path(args.model_dir)), indent=2))