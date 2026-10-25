"""Generate synthetic data, train + calibrate the model, print test metrics, save model.joblib.

SYNTHETIC DATA: the relationships below are ASSUMPTIONS made for building the demo,
not clinical findings. Metrics from this data say nothing about real-world accuracy.
To use real data: replace generate_synthetic() with a loader that returns a DataFrame
with the same columns (core.FEATURES + "pcos"), then rerun this script.
"""
import json
import os
import numpy as np
import pandas as pd
import joblib
from sklearn.model_selection import train_test_split
from sklearn.impute import SimpleImputer
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import make_pipeline
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import accuracy_score, roc_auc_score, brier_score_loss
import core

SEED = 42


def generate_synthetic(n=1500, seed=SEED):
    rng = np.random.default_rng(seed)
    # NOTE: 0.33 is a demo setting chosen so the borderline "not sure" zone is visible. Real PCOS prevalence
    # is roughly 8-13%, so these probabilities are NOT population-calibrated. Retrain on real data before any real use.
    y = (rng.random(n) < 0.33).astype(int)
    pick = lambda a, b: np.where(y == 1, a, b)
    irregular = (rng.random(n) < pick(0.75, 0.20)).astype(int)
    df = pd.DataFrame({
        "age": np.clip(rng.normal(pick(26, 27.5), 6, n), 15, 45).round(),
        "BMI": np.clip(rng.normal(pick(26.5, 23.5), pick(5.0, 4.2), n), 14, 45).round(1),
        "cycle_irregular": irregular,
        "cycle_length": np.clip(np.where(irregular == 1, rng.normal(40, 12, n), rng.normal(29, 3, n)), 21, 100).round(),
        "acne": (rng.random(n) < pick(0.60, 0.30)).astype(int),
        "excess_hair": (rng.random(n) < pick(0.55, 0.12)).astype(int),
        "weight_gain": (rng.random(n) < pick(0.55, 0.25)).astype(int),
        "LH_FSH_ratio": np.clip(np.exp(rng.normal(pick(np.log(1.8), 0.0), pick(0.35, 0.30), n)), 0.2, 6).round(2),
        "AMH": np.clip(rng.normal(pick(6.5, 3.8), pick(2.8, 1.8), n), 0.2, 15).round(1),
        "follicle_count": np.clip(rng.poisson(pick(15, 9), n), 0, 40).astype(float),
        "pcos": y,
    })
    return df


def mask_copy(df, rng, mode):
    """Hide inputs so the model learns to cope with missing values."""
    d = df.copy()
    if mode == "tests_hidden":
        d[core.TESTS] = np.nan
    elif mode == "tests_random":
        for f in core.TESTS:
            d.loc[rng.random(len(d)) < 0.5, f] = np.nan
    elif mode == "any_random":
        for f in core.TESTS:
            d.loc[rng.random(len(d)) < 0.5, f] = np.nan
        for f in core.SYMPTOMS:
            d.loc[rng.random(len(d)) < 0.10, f] = np.nan
    return d


def augment(df, seed):
    rng = np.random.default_rng(seed)
    parts = [mask_copy(df, rng, m) for m in ["none", "tests_hidden", "tests_random", "any_random"]]
    return pd.concat(parts, ignore_index=True)


def build_grid(full_train):
    grid = {}
    for f in core.FEATURES:
        if f in core.BINARY:
            prev = float(full_train[f].mean())
            grid[f] = ([0.0, 1.0], np.array([1 - prev, prev]))
        else:
            vals = [float(v) for v in full_train[f].quantile([0.1, 0.3, 0.5, 0.7, 0.9])]
            grid[f] = (vals, np.full(5, 0.2))
    return grid


def metrics(model, X, y):
    p = model.proba(X)
    return {"accuracy": round(float(accuracy_score(y, p >= 0.5)), 3),
            "roc_auc": round(float(roc_auc_score(y, p)), 3),
            "brier": round(float(brier_score_loss(y, p)), 3)}


def main(quiet=False):
    log = (lambda *a: None) if quiet else print
    df = generate_synthetic()
    log("DATA SOURCE: synthetic (assumptions, not clinical findings)")
    train, rest = train_test_split(df, test_size=0.4, stratify=df["pcos"], random_state=SEED)
    val, test = train_test_split(rest, test_size=0.5, stratify=rest["pcos"], random_state=SEED)

    tr = augment(train, 1)
    pipe = make_pipeline(SimpleImputer(strategy="median", add_indicator=True),
                         RandomForestClassifier(n_estimators=200, min_samples_leaf=5, random_state=SEED, n_jobs=-1))
    pipe.fit(tr[core.FEATURES], tr["pcos"])

    va = augment(val, 2)
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1)
    iso.fit(pipe.predict_proba(va[core.FEATURES])[:, 1], va["pcos"])
    model = core.CalibratedModel(pipe, iso)

    sym_only = test.copy()
    sym_only[core.TESTS] = np.nan
    res = {"data_source": "synthetic",
           "symptoms_only": metrics(model, sym_only[core.FEATURES], test["pcos"]),
           "symptoms_plus_tests": metrics(model, test[core.FEATURES], test["pcos"])}

    bundle = {"model": model, "grid": build_grid(train), "data_source": "synthetic"}

    # Adaptive check: for symptoms-only cases the model is unsure about, supply the suggested test's true value
    before, after = [], []
    for i in range(len(test)):
        row = sym_only.iloc[i]
        inputs = {f: (None if np.isnan(row[f]) else float(row[f])) for f in core.FEATURES}
        r = core.predict(inputs, bundle)
        if not r["is_uncertain"]:
            continue
        top = core.next_best_input(inputs, bundle)[0]["feature"]
        inputs[top] = float(test.iloc[i][top])
        before.append(r["confidence"])
        after.append(core.predict(inputs, bundle)["confidence"])
    res["adaptive"] = {"uncertain_cases": len(before),
                       "mean_confidence_before": round(float(np.mean(before)), 3) if before else None,
                       "mean_confidence_after": round(float(np.mean(after)), 3) if after else None,
                       "share_with_higher_confidence": round(float(np.mean(np.array(after) > np.array(before))), 3) if before else None}
    bundle["metrics"] = res
    joblib.dump(bundle, core.MODEL_PATH)
    with open(os.path.join(core.HERE, "metrics.json"), "w") as f:
        json.dump(res, f, indent=2)
    log(json.dumps(res, indent=2))
    return res


if __name__ == "__main__":
    main()
