from __future__ import annotations

from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest
from fastapi import HTTPException

from app.config import MODELS_DIR
from app.models import ModelResults
from app.services.cleaning_service import DataCleaningService
from app.services.data_io import (
    dataframe_preview,
    json_safe,
    read_dataframe,
    safe_filename,
)
from app.services.ml_service import (
    MLTrainingError,
    _is_identifier,
    _recommended_result,
    _validate_split_config,
    build_preprocessor,
    detect_problem_type,
    evaluate_classification,
    evaluate_regression,
    load_artifact,
    model_input_schema,
    predict_rows,
    prepare_features_and_target,
    split_and_encode,
)
from app.services.profiling_service import DatasetProfiler


# ---------------------------------------------------------------------------
# data_io helpers
# ---------------------------------------------------------------------------
def test_json_safe_converts_numpy_and_nan():
    assert json_safe(np.int64(3)) == 3
    assert json_safe(np.float64(2.5)) == 2.5
    assert json_safe(float("nan")) is None
    assert json_safe(float("inf")) is None
    assert json_safe(np.bool_(True)) is True
    assert json_safe(pd.Timestamp("2024-01-02")) == "2024-01-02T00:00:00"
    assert json_safe(np.array([1, 2])) == [1, 2]
    assert json_safe(pd.Series([1, None])) == [1, None]
    assert json_safe({"a": np.int64(1)}) == {"a": 1}
    assert json_safe(pd.NA) is None


def test_dataframe_preview_clamps_window():
    frame = pd.DataFrame({"a": range(10), "b": ["x"] * 10})
    preview = dataframe_preview(frame, offset=2, limit=3)
    assert preview["row_count"] == 10
    assert preview["column_count"] == 2
    assert preview["offset"] == 2
    assert preview["limit"] == 3
    assert len(preview["first_rows"]) == 3
    assert preview["first_rows"][0] == [2, "x"]

    clamped = dataframe_preview(frame, offset=0, limit=9999)
    assert clamped["limit"] == 500
    assert len(clamped["first_rows"]) == 10


def test_safe_filename_strips_paths_and_unsafe_characters():
    assert safe_filename("../../etc/passwd.csv") == "passwd.csv"
    assert safe_filename("C:\\temp\\my file.csv") == "my file.csv"
    assert safe_filename("bad<>name.csv") == "badname.csv"
    assert safe_filename(None, "fallback.csv") == "fallback.csv"


def test_read_dataframe_missing_file_raises_404():
    with pytest.raises(HTTPException) as exc:
        read_dataframe("does-not-exist.csv", "csv")
    assert exc.value.status_code == 404


def test_read_dataframe_unsupported_format(tmp_path):
    path = tmp_path / "data.txt"
    path.write_text("a,b\n1,2\n", encoding="utf-8")
    with pytest.raises(HTTPException) as exc:
        read_dataframe(path, "txt")
    assert exc.value.status_code == 400


# ---------------------------------------------------------------------------
# Profiler
# ---------------------------------------------------------------------------
def test_profiler_detects_types_and_ignores_numeric_strings_as_dates():
    frame = pd.DataFrame(
        {
            "num": [1, 2, 3, 4],
            "numeric_string": ["1", "2", "3", "4"],
            "date": ["2024-01-01", "2024-02-01", "2024-03-01", "2024-04-01"],
            "flag": [True, False, True, False],
            "empty": [None, None, None, None],
        }
    )
    profiler = DatasetProfiler(frame)
    assert profiler.column_analysis["num"]["data_type"] == "numerical"
    assert profiler.column_analysis["numeric_string"]["data_type"] == "categorical"
    assert profiler.column_analysis["date"]["data_type"] == "datetime"
    assert profiler.column_analysis["flag"]["data_type"] == "boolean"
    assert profiler.column_analysis["empty"]["data_type"] == "empty"
    assert profiler.overview["total_missing_cells"] == 4


# ---------------------------------------------------------------------------
# ML helpers
# ---------------------------------------------------------------------------
def test_detect_problem_type():
    assert detect_problem_type(pd.Series([True, False])) == "classification"
    assert detect_problem_type(pd.Series(["a", "b"])) == "classification"
    assert detect_problem_type(pd.Series([0, 1, 0, 1])) == "classification"
    assert detect_problem_type(pd.Series([0.5, 1.2, 9.9, 3.3])) == "regression"
    assert detect_problem_type(pd.Series([0] * 95 + [1] * 5)) == "classification"


def test_validate_split_config():
    assert _validate_split_config({"test_size": 0.3, "random_seed": 7}) == (0.3, 7)
    with pytest.raises(MLTrainingError):
        _validate_split_config({"test_size": 0.01})
    with pytest.raises(MLTrainingError):
        _validate_split_config({"test_size": "abc"})


def test_identifier_detection():
    assert _is_identifier("id")
    assert _is_identifier("user_id")
    assert _is_identifier("uuid")
    assert _is_identifier("token_hash")
    assert not _is_identifier("valid")


def test_prepare_features_excludes_identifiers_and_free_text():
    frame = pd.DataFrame(
        {
            "id": range(20),
            "name": [f"person_{index}" for index in range(20)],
            "age": np.arange(20) + 20,
            "score": np.arange(20) * 2.0,
            "category": ["a", "b"] * 10,
            "target": [0, 1] * 10,
        }
    )
    X, y, numeric, categorical, class_names, used, dropped = prepare_features_and_target(
        frame, "target", "classification"
    )
    assert dropped == 0
    assert "id" not in used and "name" not in used
    assert set(numeric) == {"age", "score"}
    assert categorical == ["category"]
    assert class_names == ["0", "1"]
    assert len(X) == len(y) == 20


def test_prepare_features_drops_missing_targets_and_datetime_conversion():
    frame = pd.DataFrame(
        {
            "age": [20, 21, 22, 23],
            "when": pd.to_datetime(
                ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"]
            ),
            "target": [1.0, np.nan, 2.5, 3.5],
        }
    )
    X, y, numeric, categorical, _class_names, used, dropped = prepare_features_and_target(
        frame, "target", "regression"
    )
    assert dropped == 1
    assert len(X) == 3
    assert "when" in numeric
    assert pd.api.types.is_numeric_dtype(X["when"])


def test_prepare_features_validation_errors():
    frame = pd.DataFrame({"age": [1, 2], "target": [0, 1]})
    with pytest.raises(MLTrainingError):
        prepare_features_and_target(frame, "missing", "classification")
    with pytest.raises(MLTrainingError):
        prepare_features_and_target(
            frame, "target", "classification", selected_features=["age", "target"]
        )
    with pytest.raises(MLTrainingError):
        prepare_features_and_target(
            frame, "target", "classification", selected_features=["nope"]
        )
    with pytest.raises(MLTrainingError):
        prepare_features_and_target(
            pd.DataFrame({"age": [1, 2], "target": ["a", "b"]}),
            "target",
            "regression",
        )
    with pytest.raises(MLTrainingError):
        prepare_features_and_target(
            pd.DataFrame({"age": [1, 2], "target": [0, 0]}), "target", "classification"
        )


def test_split_and_encode_stratifies_and_requires_enough_rows():
    X = pd.DataFrame({"x": range(20)})
    y = pd.Series([0] * 10 + [1] * 10)

    X_train, X_test, y_train, y_test, class_names = split_and_encode(
        X, y, "classification", 0.2, 42
    )
    assert set(np.unique(y_train)) == {0, 1}
    assert set(np.unique(y_test)) == {0, 1}
    assert class_names == ["0", "1"]
    assert len(X_train) == 16 and len(X_test) == 4

    with pytest.raises(MLTrainingError):
        split_and_encode(pd.DataFrame({"x": range(5)}), pd.Series([0, 1, 0, 1, 0]), "classification", 0.2, 42)


def test_preprocessor_is_fitted_on_training_data_only():
    X_train = pd.DataFrame(
        {
            "age": [10.0, 20.0, 30.0, 40.0],
            "category": ["a", "b", "a", "b"],
        }
    )
    X_test = pd.DataFrame({"age": [1000.0], "category": ["unseen"]})

    preprocessor = build_preprocessor(["age"], ["category"])
    transformed_train = preprocessor.fit_transform(X_train)
    transformed_test = preprocessor.transform(X_test)

    scaler = preprocessor.named_transformers_["num"].named_steps["scaler"]
    assert scaler.mean_[0] == pytest.approx(25.0)

    encoder = preprocessor.named_transformers_["cat"].named_steps["encoder"]
    assert set(encoder.categories_[0]) == {"a", "b"}
    assert transformed_train.shape[1] == 3  # age + two one-hot columns
    assert transformed_test.shape[1] == 3


def test_evaluation_metrics():
    y_test = np.array([0, 1, 1, 0])
    y_pred = np.array([0, 1, 0, 0])
    y_proba = np.array([[0.8, 0.2], [0.1, 0.9], [0.6, 0.4], [0.7, 0.3]])
    metrics = evaluate_classification(y_test, y_pred, y_proba, ["0", "1"])
    assert metrics["accuracy"] == 0.75
    assert "roc_auc" in metrics
    assert metrics["confusion_matrix"] == [[2, 0], [1, 1]]

    regression = evaluate_regression(np.array([1.0, 2.0]), np.array([1.0, 3.0]))
    assert regression["mae"] == 0.5
    assert regression["rmse"] == pytest.approx(0.7071, abs=1e-4)


def test_recommended_model_prefers_best_score():
    results = [
        {"model_id": 1, "status": "completed", "metrics": {"f1_score": 0.5}, "training_duration": 1},
        {"model_id": 2, "status": "completed", "metrics": {"f1_score": 0.9}, "training_duration": 2},
        {"model_id": 3, "status": "failed", "metrics": {}, "training_duration": 0.1},
    ]
    assert _recommended_result(results, "classification") == 2
    assert _recommended_result([], "classification") is None

    regression = [
        {"model_id": 1, "status": "completed", "metrics": {"r2_score": 0.4, "rmse": 2.0}, "training_duration": 1},
        {"model_id": 2, "status": "completed", "metrics": {"r2_score": 0.8, "rmse": 1.0}, "training_duration": 1},
    ]
    assert _recommended_result(regression, "regression") == 2


def test_load_artifact_rejects_paths_outside_storage(tmp_path):
    outside = tmp_path / "evil.joblib"
    joblib.dump({"pipeline": object()}, outside)

    model = ModelResults(model_artifact_path=str(outside))
    with pytest.raises(MLTrainingError):
        load_artifact(model)

    model.model_artifact_path = str(MODELS_DIR / "missing.joblib")
    with pytest.raises(MLTrainingError):
        load_artifact(model)

    model.model_artifact_path = None
    with pytest.raises(MLTrainingError):
        load_artifact(model)


def test_load_artifact_rejects_wrong_structure():
    path = MODELS_DIR / "test_invalid_artifact.joblib"
    joblib.dump([1, 2, 3], path)
    try:
        model = ModelResults(model_artifact_path=str(path))
        with pytest.raises(MLTrainingError):
            load_artifact(model)
    finally:
        path.unlink(missing_ok=True)


def test_model_input_schema_and_prediction_validation():
    artifact = {
        "pipeline": None,
        "feature_columns": ["age", "category"],
        "numeric_columns": ["age"],
        "categorical_columns": ["category"],
        "categories": {"category": ["a", "b"]},
        "class_names": ["0", "1"],
        "problem_type": "classification",
    }
    schema = model_input_schema(artifact)
    assert schema[0] == {"name": "age", "type": "numeric"}
    assert schema[1]["categories"] == ["a", "b"]

    with pytest.raises(MLTrainingError):
        predict_rows(artifact, [{"age": 1}])
    with pytest.raises(MLTrainingError):
        predict_rows(artifact, [])


# ---------------------------------------------------------------------------
# Cleaning service
# ---------------------------------------------------------------------------
@pytest.fixture
def cleaning_frame():
    return pd.DataFrame(
        {
            "a": [1.0, 2.0, np.nan, 4.0, 100.0],
            "b": ["x", "y", "x", "y", "x"],
            "c": [1, 1, 1, 1, 1],
        }
    )


def test_cleaning_does_not_mutate_input(cleaning_frame):
    original = cleaning_frame.copy(deep=True)
    service = DataCleaningService(cleaning_frame)
    service.handle_missing_values("mean", columns=["a"])
    service.remove_duplicates()
    pd.testing.assert_frame_equal(cleaning_frame, original)


def test_cleaning_missing_value_methods(cleaning_frame):
    service = DataCleaningService(cleaning_frame)
    result = service.handle_missing_values("mean", columns=["a"])
    assert result["records_affected"] == 1
    assert service.get_cleaned_data()["a"].isna().sum() == 0

    service = DataCleaningService(cleaning_frame)
    service.handle_missing_values("constant", columns=["a"], fill_value=-1)
    assert service.get_cleaned_data().loc[2, "a"] == -1

    service = DataCleaningService(cleaning_frame)
    service.handle_missing_values("mode", columns=["b"])
    assert service.get_cleaned_data()["b"].isna().sum() == 0


def test_cleaning_duplicate_strategies():
    frame = pd.DataFrame({"a": [1, 1, 1, 2], "b": [1, 1, 1, 2]})
    first = DataCleaningService(frame)
    first.remove_duplicates("keep_first")
    assert len(first.get_cleaned_data()) == 2

    last = DataCleaningService(frame)
    last.remove_duplicates("keep_last")
    assert len(last.get_cleaned_data()) == 2

    with pytest.raises(ValueError):
        DataCleaningService(frame).remove_duplicates("nope")


def test_cleaning_outlier_operations():
    frame = pd.DataFrame({"a": [1.0, 2.0, 3.0, 4.0, 5.0, 1000.0]})

    detect = DataCleaningService(frame)
    result = detect.handle_outliers("iqr", columns=["a"], operation="detect")
    assert result["detected_outliers"][0]["count"] == 1
    assert len(detect.get_cleaned_data()) == 6

    remove = DataCleaningService(frame)
    remove.handle_outliers("iqr", columns=["a"], operation="remove")
    assert len(remove.get_cleaned_data()) == 5

    cap = DataCleaningService(frame)
    cap.handle_outliers("iqr", columns=["a"], operation="cap")
    assert cap.get_cleaned_data()["a"].max() < 1000

    with pytest.raises(ValueError):
        DataCleaningService(frame).handle_outliers("nope")
    with pytest.raises(ValueError):
        DataCleaningService(frame).handle_outliers("iqr", operation="nope")


def test_cleaning_encoding_and_scaling():
    frame = pd.DataFrame({"cat": ["a", "b", "c"], "num": [1.0, 2.0, 3.0]})

    one_hot = DataCleaningService(frame)
    result = one_hot.encode_features("one_hot", columns=["cat"])
    assert len(result["new_columns"]) == 2
    assert "cat" not in one_hot.get_cleaned_data().columns

    ordinal = DataCleaningService(frame)
    ordinal.encode_features("ordinal", columns=["cat"])
    assert ordinal.get_cleaned_data()["cat"].tolist() == [0.0, 1.0, 2.0]

    scaled = DataCleaningService(frame)
    scaled.scale_features("minmax", columns=["num"])
    assert scaled.get_cleaned_data()["num"].tolist() == [0.0, 0.5, 1.0]

    with pytest.raises(ValueError):
        DataCleaningService(frame).encode_features("nope")
    with pytest.raises(ValueError):
        DataCleaningService(frame).scale_features("nope")


def test_cleaning_type_conversion_and_history():
    frame = pd.DataFrame({"a": ["1", "2", "x"], "b": ["2024-01-01", "2024-01-02", "bad"]})
    service = DataCleaningService(frame)
    result = service.convert_data_type(["a"], "integer")
    assert "a" in result["affected_columns"]
    assert service.get_cleaned_data()["a"].isna().sum() == 1

    service.convert_data_type(["b"], "datetime")
    history = service.get_cleaning_history()
    assert len(history) == 2
    assert history[0]["operation"] == "data_type_conversion"
    assert "timestamp" in history[0]

    with pytest.raises(ValueError):
        service.convert_data_type(["a"], "nope")
