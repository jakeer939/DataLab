"""Leakage-safe machine-learning training, evaluation and prediction.

Every model is trained inside a scikit-learn Pipeline so imputers, encoders
and scalers are fitted on the training split only. The fitted pipeline is
persisted together with the feature schema so predictions are reproducible.
"""
from __future__ import annotations

import math
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import (
    GradientBoostingClassifier,
    GradientBoostingRegressor,
    RandomForestClassifier,
    RandomForestRegressor,
)
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Lasso, LinearRegression, LogisticRegression, Ridge
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    r2_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import cross_val_score, train_test_split
from sklearn.naive_bayes import GaussianNB
from sklearn.neighbors import KNeighborsClassifier, KNeighborsRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import LabelEncoder, OneHotEncoder, StandardScaler
from sklearn.svm import SVC, SVR
from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor

from ..config import MODELS_DIR
from ..models import DatasetVersions, Datasets, ModelResults
from ..services.data_io import json_safe, load_dataset_frame

try:  # optional dependency
    import xgboost as xgb
except ImportError:  # pragma: no cover - exercised only when xgboost is absent
    xgb = None


CLASSIFICATION_ALGORITHMS = {
    "logistic_regression",
    "decision_tree",
    "random_forest",
    "knn",
    "svm",
    "naive_bayes",
    "gradient_boosting",
    "xgboost",
}

REGRESSION_ALGORITHMS = {
    "linear_regression",
    "ridge",
    "lasso",
    "decision_tree",
    "random_forest",
    "gradient_boosting",
    "svr",
    "xgboost",
}

ALL_ALGORITHMS = CLASSIFICATION_ALGORITHMS | REGRESSION_ALGORITHMS

ALGORITHM_LABELS = {
    "logistic_regression": "Logistic Regression",
    "decision_tree": "Decision Tree",
    "random_forest": "Random Forest",
    "knn": "K-Nearest Neighbours",
    "svm": "Support Vector Machine",
    "naive_bayes": "Gaussian Naive Bayes",
    "gradient_boosting": "Gradient Boosting",
    "xgboost": "XGBoost",
    "linear_regression": "Linear Regression",
    "ridge": "Ridge Regression",
    "lasso": "Lasso Regression",
    "svr": "Support Vector Regressor",
}


class MLTrainingError(ValueError):
    """Raised for user-correctable experiment configuration errors."""


def detect_problem_type(target: pd.Series) -> str:
    """Heuristically infer classification vs regression."""
    if pd.api.types.is_bool_dtype(target):
        return "classification"
    if not pd.api.types.is_numeric_dtype(target):
        return "classification"
    non_null = target.dropna()
    if non_null.empty:
        return "classification"
    unique = non_null.nunique()
    if unique <= 2:
        return "classification"
    if unique <= 20 and (unique / max(len(non_null), 1)) < 0.05:
        return "classification"
    return "regression"


def _validate_split_config(split_config: Dict[str, Any]) -> Tuple[float, int]:
    try:
        test_size = float(split_config.get("test_size", 0.2))
        random_seed = int(split_config.get("random_seed", 42))
    except (TypeError, ValueError):
        raise MLTrainingError("test_size must be numeric and random_seed must be an integer")
    if not 0.05 <= test_size <= 0.5:
        raise MLTrainingError("test_size must be between 0.05 and 0.5")
    return test_size, random_seed


def _is_identifier(column: str) -> bool:
    lowered = column.lower().strip()
    patterns = ("id", "uuid", "guid", "hash", "token")
    return any(lowered == pattern or lowered.endswith(f"_{pattern}") or lowered.startswith(f"{pattern}_")
               for pattern in patterns)


def prepare_features_and_target(
    df: pd.DataFrame,
    target_column: str,
    problem_type: str,
    selected_features: Optional[List[str]] = None,
) -> Tuple[pd.DataFrame, pd.Series, List[str], List[str], List[str], List[str], int]:
    """Return X, y, numeric columns, categorical columns, class names, features, dropped rows."""
    if target_column not in df.columns:
        raise MLTrainingError(f"Target column '{target_column}' does not exist")

    selected_features = list(selected_features or [])
    if selected_features:
        missing = [column for column in selected_features if column not in df.columns]
        if missing:
            raise MLTrainingError(f"Selected features do not exist: {', '.join(missing)}")
        if target_column in selected_features:
            raise MLTrainingError("The target column cannot also be a feature")

    working = df.copy()
    rows_before = len(working)
    working = working[working[target_column].notna()]
    dropped_rows = rows_before - len(working)
    if len(working) == 0:
        raise MLTrainingError("The target column contains no usable values")

    y = working[target_column]
    X = working.drop(columns=[target_column])

    if problem_type == "classification":
        y = y.astype(str)
        class_names = sorted(y.unique().tolist())
        if len(class_names) < 2:
            raise MLTrainingError("Classification requires at least two target classes")
    else:
        numeric_y = pd.to_numeric(y, errors="coerce")
        invalid = int(numeric_y.isna().sum())
        if invalid:
            raise MLTrainingError(
                f"Regression target contains {invalid} non-numeric value(s); clean or convert it first"
            )
        y = numeric_y.astype(float)
        class_names = []

    if selected_features:
        feature_columns = selected_features
    else:
        feature_columns = []
        for column in X.columns:
            if _is_identifier(column):
                continue
            series = X[column]
            if series.isna().all():
                continue
            if pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series):
                unique_ratio = series.nunique(dropna=True) / max(len(series), 1)
                if unique_ratio > 0.9:
                    # Free-text / identifier-like column, not a useful feature.
                    continue
            feature_columns.append(column)

    if not feature_columns:
        raise MLTrainingError("No usable feature columns remain after excluding identifiers")

    X = X[feature_columns].copy()

    numeric_columns: List[str] = []
    categorical_columns: List[str] = []
    for column in X.columns:
        series = X[column]
        if pd.api.types.is_datetime64_any_dtype(series):
            converted = pd.to_datetime(series, errors="coerce")
            numeric_values = converted.astype("int64") / 1e9
            numeric_values = numeric_values.mask(converted.isna(), np.nan)
            X[column] = numeric_values
            numeric_columns.append(column)
        elif pd.api.types.is_bool_dtype(series):
            X[column] = series.astype("object")
            categorical_columns.append(column)
        elif pd.api.types.is_numeric_dtype(series):
            numeric_columns.append(column)
        elif pd.api.types.is_object_dtype(series) or isinstance(series.dtype, pd.CategoricalDtype):
            X[column] = series.astype("object")
            categorical_columns.append(column)
        else:
            # Unsupported dtype (e.g. timedelta) is dropped from the feature set.
            continue

    used = numeric_columns + categorical_columns
    X = X[used]
    return X, y, numeric_columns, categorical_columns, class_names, used, dropped_rows


def build_preprocessor(
    numeric_columns: List[str], categorical_columns: List[str]
) -> ColumnTransformer:
    transformers = []
    if numeric_columns:
        transformers.append(
            (
                "num",
                Pipeline(
                    steps=[
                        ("imputer", SimpleImputer(strategy="median")),
                        ("scaler", StandardScaler()),
                    ]
                ),
                numeric_columns,
            )
        )
    if categorical_columns:
        transformers.append(
            (
                "cat",
                Pipeline(
                    steps=[
                        ("imputer", SimpleImputer(strategy="most_frequent")),
                        (
                            "encoder",
                            OneHotEncoder(
                                sparse_output=False,
                                handle_unknown="ignore",
                                drop=None,
                            ),
                        ),
                    ]
                ),
                categorical_columns,
            )
        )
    if not transformers:
        raise MLTrainingError("No numeric or categorical features are available")
    return ColumnTransformer(transformers=transformers, remainder="drop", sparse_threshold=0)


def create_estimator(algorithm: str, problem_type: str, random_seed: int):
    if problem_type == "classification":
        if algorithm == "logistic_regression":
            return LogisticRegression(max_iter=2000, random_state=random_seed, class_weight="balanced")
        if algorithm == "decision_tree":
            return DecisionTreeClassifier(random_state=random_seed, class_weight="balanced")
        if algorithm == "random_forest":
            return RandomForestClassifier(
                n_estimators=200, random_state=random_seed, class_weight="balanced", n_jobs=-1
            )
        if algorithm == "knn":
            return KNeighborsClassifier(n_neighbors=5)
        if algorithm == "svm":
            # SVC(probability=True) is deprecated in scikit-learn 1.9; an
            # explicitly calibrated SVC keeps predict_proba available.
            return CalibratedClassifierCV(
                SVC(random_state=random_seed, class_weight="balanced"),
                ensemble=False,
            )
        if algorithm == "naive_bayes":
            return GaussianNB()
        if algorithm == "gradient_boosting":
            return GradientBoostingClassifier(random_state=random_seed)
        if algorithm == "xgboost":
            if xgb is None:
                raise MLTrainingError("XGBoost is not installed on the server")
            return xgb.XGBClassifier(
                n_estimators=200,
                random_state=random_seed,
                eval_metric="logloss",
                n_jobs=-1,
            )
        raise MLTrainingError(f"Algorithm '{algorithm}' is not supported for classification")

    if algorithm == "linear_regression":
        return LinearRegression()
    if algorithm == "ridge":
        return Ridge(random_state=random_seed)
    if algorithm == "lasso":
        return Lasso(random_state=random_seed, max_iter=5000)
    if algorithm == "decision_tree":
        return DecisionTreeRegressor(random_state=random_seed)
    if algorithm == "random_forest":
        return RandomForestRegressor(n_estimators=200, random_state=random_seed, n_jobs=-1)
    if algorithm == "gradient_boosting":
        return GradientBoostingRegressor(random_state=random_seed)
    if algorithm == "svr":
        return SVR()
    if algorithm == "xgboost":
        if xgb is None:
            raise MLTrainingError("XGBoost is not installed on the server")
        return xgb.XGBRegressor(n_estimators=200, random_state=random_seed, n_jobs=-1)
    raise MLTrainingError(f"Algorithm '{algorithm}' is not supported for regression")


def split_and_encode(
    X: pd.DataFrame,
    y: pd.Series,
    problem_type: str,
    test_size: float,
    random_seed: int,
):
    if len(X) < 10:
        raise MLTrainingError("At least 10 usable rows are required to train a model")

    stratify = None
    if problem_type == "classification":
        counts = y.value_counts()
        if len(counts) < 2:
            raise MLTrainingError("Classification requires at least two target classes")
        if counts.min() >= 2:
            stratify = y
        else:
            raise MLTrainingError(
                "Each target class needs at least two rows for a stratified train/test split"
            )

    try:
        X_train, X_test, y_train, y_test = train_test_split(
            X,
            y,
            test_size=test_size,
            random_state=random_seed,
            stratify=stratify,
        )
    except ValueError as exc:
        raise MLTrainingError(f"Unable to create a train/test split: {exc}")

    if len(X_train) == 0 or len(X_test) == 0:
        raise MLTrainingError("Train/test split produced an empty partition")

    class_names: List[str] = []
    if problem_type == "classification":
        encoder = LabelEncoder()
        y_train_encoded = encoder.fit_transform(y_train.astype(str))
        class_names = [str(item) for item in encoder.classes_.tolist()]
        known = set(class_names)
        unseen = sorted(set(y_test.astype(str)) - known)
        if unseen:
            raise MLTrainingError(
                "The test split contains classes absent from the training split: "
                + ", ".join(unseen)
            )
        y_test_encoded = encoder.transform(y_test.astype(str))
        return X_train, X_test, y_train_encoded, y_test_encoded, class_names

    return X_train, X_test, y_train.astype(float), y_test.astype(float), class_names


def evaluate_classification(y_test, y_pred, y_proba, class_names: List[str]) -> Dict[str, Any]:
    metrics: Dict[str, Any] = {
        "accuracy": round(float(accuracy_score(y_test, y_pred)), 4),
        "precision": round(
            float(precision_score(y_test, y_pred, average="weighted", zero_division=0)), 4
        ),
        "recall": round(
            float(recall_score(y_test, y_pred, average="weighted", zero_division=0)), 4
        ),
        "f1_score": round(
            float(f1_score(y_test, y_pred, average="weighted", zero_division=0)), 4
        ),
    }
    labels = list(range(len(class_names)))
    metrics["confusion_matrix"] = [
        [int(value) for value in row]
        for row in confusion_matrix(y_test, y_pred, labels=labels).tolist()
    ]
    metrics["class_labels"] = class_names

    try:
        if y_proba is not None:
            if len(class_names) == 2 and y_proba.shape[1] == 2:
                metrics["roc_auc"] = round(float(roc_auc_score(y_test, y_proba[:, 1])), 4)
            elif len(class_names) > 2:
                present = set(np.unique(y_test).tolist())
                if present == set(labels):
                    metrics["roc_auc"] = round(
                        float(
                            roc_auc_score(
                                y_test,
                                y_proba,
                                multi_class="ovr",
                                average="weighted",
                            )
                        ),
                        4,
                    )
    except (ValueError, TypeError):
        pass
    return metrics


def evaluate_regression(y_test, y_pred) -> Dict[str, Any]:
    mse = float(mean_squared_error(y_test, y_pred))
    return {
        "mae": round(float(mean_absolute_error(y_test, y_pred)), 4),
        "mse": round(mse, 4),
        "rmse": round(math.sqrt(mse), 4),
        "r2_score": round(float(r2_score(y_test, y_pred)), 4),
    }


def _safe_params(estimator) -> Dict[str, Any]:
    params = {}
    for key, value in estimator.get_params(deep=False).items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            params[key] = value
        else:
            params[key] = str(value)
    return params


def _json_safe_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    return {str(key): json_safe(value) for key, value in data.items()}


def _category_values(X_train: pd.DataFrame, columns: List[str]) -> Dict[str, List[str]]:
    values = {}
    for column in columns:
        counts = X_train[column].astype(str).value_counts().head(100)
        values[column] = [str(item) for item in counts.index.tolist()]
    return values


def _recommended_result(results: List[Dict[str, Any]], problem_type: str) -> Optional[int]:
    successful = [result for result in results if result.get("model_id") and result.get("status") == "completed"]
    if not successful:
        return None
    if problem_type == "classification":
        successful.sort(
            key=lambda result: (
                result["metrics"].get("f1_score") or 0,
                result["metrics"].get("accuracy") or 0,
                -(result.get("training_duration") or 0),
            ),
            reverse=True,
        )
    else:
        successful.sort(
            key=lambda result: (
                result["metrics"].get("r2_score") if result["metrics"].get("r2_score") is not None else -1e9,
                -(result["metrics"].get("rmse") if result["metrics"].get("rmse") is not None else 1e9),
                -(result.get("training_duration") or 0),
            ),
            reverse=True,
        )
    return successful[0]["model_id"]


def train_experiment(
    db,
    dataset: Datasets,
    target_column: str,
    problem_type: str,
    selected_features: List[str],
    split_configuration: Dict[str, Any],
    algorithms: List[str],
) -> Dict[str, Any]:
    """Train all requested algorithms on one shared, leakage-free split."""
    df, version = load_dataset_frame(db, dataset)
    if version is None:
        raise MLTrainingError("Dataset has no stored version; re-upload the dataset")

    if problem_type == "auto":
        problem_type = detect_problem_type(df[target_column])
    if problem_type not in {"classification", "regression"}:
        raise MLTrainingError("problem_type must be classification or regression")

    if not algorithms:
        algorithms = (
            sorted(CLASSIFICATION_ALGORITHMS)
            if problem_type == "classification"
            else sorted(REGRESSION_ALGORITHMS)
        )

    supported = CLASSIFICATION_ALGORITHMS if problem_type == "classification" else REGRESSION_ALGORITHMS
    invalid_algorithms = [name for name in algorithms if name not in supported]
    if invalid_algorithms:
        raise MLTrainingError(
            f"Algorithms not supported for {problem_type}: {', '.join(invalid_algorithms)}"
        )

    test_size, random_seed = _validate_split_config(split_configuration)

    X, y, numeric_columns, categorical_columns, class_names, feature_columns, dropped_rows = (
        prepare_features_and_target(df, target_column, problem_type, selected_features)
    )
    X_train, X_test, y_train, y_test, class_names = split_and_encode(
        X, y, problem_type, test_size, random_seed
    )

    from ..models import Experiments  # local import avoids a circular import at module load

    experiment = Experiments(
        dataset_version_id=version.id,
        user_id=dataset.user_id,
        target_column=target_column,
        problem_type=problem_type,
        selected_features=feature_columns,
        split_configuration={
            **split_configuration,
            "test_size": test_size,
            "random_seed": random_seed,
        },
        random_seed=random_seed,
        status="training",
    )
    db.add(experiment)
    db.commit()
    db.refresh(experiment)

    categories = _category_values(X_train, categorical_columns)
    results: List[Dict[str, Any]] = []

    try:
        for algorithm in algorithms:
            started = time.perf_counter()
            try:
                estimator = create_estimator(algorithm, problem_type, random_seed)
                pipeline = Pipeline(
                    steps=[
                        ("preprocessor", build_preprocessor(numeric_columns, categorical_columns)),
                        ("model", estimator),
                    ]
                )
                pipeline.fit(X_train, y_train)
                y_pred = pipeline.predict(X_test)

                if problem_type == "classification":
                    y_proba = None
                    if hasattr(pipeline, "predict_proba"):
                        try:
                            y_proba = pipeline.predict_proba(X_test)
                        except (AttributeError, ValueError):
                            y_proba = None
                    metrics = evaluate_classification(y_test, y_pred, y_proba, class_names)
                else:
                    metrics = evaluate_regression(y_test, y_pred)

                if split_configuration.get("cross_validation"):
                    try:
                        scoring = "f1_weighted" if problem_type == "classification" else "r2"
                        cv_folds = (
                            min(5, int(pd.Series(y_train).value_counts().min()))
                            if problem_type == "classification"
                            else 5
                        )
                        if cv_folds >= 2:
                            scores = cross_val_score(
                                pipeline, X_train, y_train, cv=cv_folds, scoring=scoring, n_jobs=1
                            )
                            metrics["cv_mean"] = round(float(np.mean(scores)), 4)
                            metrics["cv_std"] = round(float(np.std(scores)), 4)
                            metrics["cv_folds"] = int(cv_folds)
                    except (ValueError, TypeError):
                        pass

                duration = round(time.perf_counter() - started, 4)
                artifact_path = MODELS_DIR / f"model_{uuid.uuid4().hex}.joblib"
                artifact = {
                    "pipeline": pipeline,
                    "algorithm": algorithm,
                    "algorithm_label": ALGORITHM_LABELS.get(algorithm, algorithm),
                    "problem_type": problem_type,
                    "target_column": target_column,
                    "class_names": class_names,
                    "feature_columns": feature_columns,
                    "numeric_columns": numeric_columns,
                    "categorical_columns": categorical_columns,
                    "categories": categories,
                    "metrics": metrics,
                    "training_rows": int(len(X_train)),
                    "test_rows": int(len(X_test)),
                    "random_seed": random_seed,
                }
                joblib.dump(artifact, artifact_path)

                model_result = ModelResults(
                    experiment_id=experiment.id,
                    algorithm_name=algorithm,
                    hyperparameters={
                        "label": ALGORITHM_LABELS.get(algorithm, algorithm),
                        "params": _safe_params(estimator),
                        "feature_columns": feature_columns,
                        "numeric_columns": numeric_columns,
                        "categorical_columns": categorical_columns,
                        "class_names": class_names,
                    },
                    evaluation_metrics=metrics,
                    training_duration=duration,
                    model_artifact_path=str(artifact_path),
                    status="completed",
                )
                db.add(model_result)
                db.commit()
                db.refresh(model_result)
                results.append(
                    {
                        "model_id": model_result.id,
                        "algorithm": algorithm,
                        "status": "completed",
                        "metrics": metrics,
                        "training_duration": duration,
                    }
                )
            except Exception as exc:
                db.rollback()
                failed = ModelResults(
                    experiment_id=experiment.id,
                    algorithm_name=algorithm,
                    hyperparameters={"label": ALGORITHM_LABELS.get(algorithm, algorithm)},
                    evaluation_metrics={"error": str(exc)},
                    training_duration=round(time.perf_counter() - started, 4),
                    model_artifact_path=None,
                    status="failed",
                )
                db.add(failed)
                db.commit()
                db.refresh(failed)
                results.append(
                    {
                        "model_id": failed.id,
                        "algorithm": algorithm,
                        "status": "failed",
                        "metrics": {},
                        "training_duration": failed.training_duration,
                        "error": str(exc),
                    }
                )

        experiment.status = "completed" if any(r["status"] == "completed" for r in results) else "failed"
        experiment.model_results = [r["model_id"] for r in results]
        db.commit()
    except Exception:
        experiment.status = "failed"
        db.commit()
        raise

    return {
        "experiment_id": experiment.id,
        "problem_type": problem_type,
        "target_column": target_column,
        "selected_features": feature_columns,
        "split_configuration": experiment.split_configuration,
        "dataset_version_id": version.id,
        "results": results,
        "recommended_model_id": _recommended_result(results, problem_type),
        "preprocessing_config": {
            "numeric_columns": numeric_columns,
            "categorical_columns": categorical_columns,
            "dropped_rows": dropped_rows,
            "training_rows": int(len(X_train)),
            "test_rows": int(len(X_test)),
            "class_names": class_names,
        },
    }


# ----------------------------------------------------------------------
# Persistence and prediction
# ----------------------------------------------------------------------
def load_artifact(model_result: ModelResults) -> Dict[str, Any]:
    """Load a server-created model artifact, refusing paths outside storage."""
    if not model_result.model_artifact_path:
        raise MLTrainingError("This model has no saved artifact")
    path = Path(model_result.model_artifact_path).resolve()
    try:
        if not path.is_relative_to(MODELS_DIR):
            raise MLTrainingError("Model artifact path is outside the model storage directory")
    except ValueError:
        raise MLTrainingError("Model artifact path is invalid")
    if path.suffix != ".joblib" or not path.exists():
        raise MLTrainingError("Model artifact is missing or has an unsupported format")

    try:
        artifact = joblib.load(path)
    except Exception as exc:
        raise MLTrainingError(f"Unable to load model artifact: {exc}")
    if not isinstance(artifact, dict) or "pipeline" not in artifact:
        raise MLTrainingError("Model artifact has an unsupported structure")
    return artifact


def model_input_schema(artifact: Dict[str, Any]) -> List[Dict[str, Any]]:
    numeric = set(artifact.get("numeric_columns", []))
    categorical = set(artifact.get("categorical_columns", []))
    categories = artifact.get("categories", {})
    schema = []
    for column in artifact.get("feature_columns", []):
        entry = {
            "name": column,
            "type": "numeric" if column in numeric else "categorical" if column in categorical else "unknown",
        }
        if column in categorical:
            entry["categories"] = categories.get(column, [])
        schema.append(entry)
    return schema


def _prepare_prediction_frame(artifact: Dict[str, Any], rows: List[Dict[str, Any]]) -> pd.DataFrame:
    feature_columns = artifact.get("feature_columns", [])
    numeric_columns = set(artifact.get("numeric_columns", []))
    categorical_columns = set(artifact.get("categorical_columns", []))

    missing_by_row = []
    for index, row in enumerate(rows):
        missing = [column for column in feature_columns if column not in row]
        if missing:
            missing_by_row.append(f"row {index + 1}: {', '.join(missing)}")
    if missing_by_row:
        raise MLTrainingError("Missing required feature(s): " + "; ".join(missing_by_row[:10]))

    prepared = []
    for row in rows:
        output = {}
        for column in feature_columns:
            value = row.get(column)
            if column in numeric_columns:
                output[column] = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
            elif column in categorical_columns:
                output[column] = None if value is None or (isinstance(value, float) and math.isnan(value)) else str(value)
            else:
                output[column] = value
        prepared.append(output)
    return pd.DataFrame(prepared, columns=feature_columns)


def predict_rows(artifact: Dict[str, Any], rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not rows:
        raise MLTrainingError("At least one prediction row is required")
    frame = _prepare_prediction_frame(artifact, rows)
    pipeline: Pipeline = artifact["pipeline"]
    try:
        predictions = pipeline.predict(frame)
    except Exception as exc:
        raise MLTrainingError(f"Prediction failed: {exc}")

    class_names = artifact.get("class_names") or []
    probabilities = None
    if hasattr(pipeline, "predict_proba"):
        try:
            probabilities = pipeline.predict_proba(frame)
        except (AttributeError, ValueError):
            probabilities = None

    output = []
    for index, raw_prediction in enumerate(predictions):
        if artifact.get("problem_type") == "classification":
            try:
                prediction = class_names[int(raw_prediction)]
            except (IndexError, TypeError, ValueError):
                prediction = json_safe(raw_prediction)
        else:
            prediction = round(float(raw_prediction), 6)

        probability = None
        if probabilities is not None and len(class_names) == probabilities.shape[1]:
            probability = {
                str(label): round(float(value), 6)
                for label, value in zip(class_names, probabilities[index].tolist())
            }
        output.append({"prediction": prediction, "probability": probability})
    return output
