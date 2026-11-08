from __future__ import annotations

from pathlib import Path

import pytest

from app.models import ModelResults

from .conftest import classification_csv, regression_csv, upload_csv


def train(client, headers, dataset_id, **overrides):
    payload = {
        "dataset_id": dataset_id,
        "target_column": "target",
        "problem_type": "classification",
        "selected_features": [],
        "split_configuration": {"test_size": 0.2, "random_seed": 42},
        "algorithms": ["decision_tree"],
    }
    payload.update(overrides)
    return client.post("/api/v1/experiments/", headers=headers, json=payload)


def test_algorithms_endpoint(client, auth):
    response = client.get("/api/v1/experiments/algorithms", headers=auth)
    assert response.status_code == 200
    body = response.json()
    assert "logistic_regression" in body["classification"]
    assert "random_forest" in body["classification"]
    assert "linear_regression" in body["regression"]
    assert "ridge" in body["regression"]
    assert body["labels"]["decision_tree"] == "Decision Tree"


def test_classification_training(client, auth, uploaded_dataset):
    response = train(
        client,
        auth,
        uploaded_dataset["id"],
        algorithms=["logistic_regression", "decision_tree", "random_forest"],
    )
    assert response.status_code == 201, response.text
    body = response.json()

    assert body["problem_type"] == "classification"
    assert body["target_column"] == "target"
    assert len(body["results"]) == 3
    assert all(result["status"] == "completed" for result in body["results"])
    assert all(result["model_id"] for result in body["results"])

    metrics = body["results"][0]["metrics"]
    assert 0 <= metrics["accuracy"] <= 1
    assert 0 <= metrics["precision"] <= 1
    assert 0 <= metrics["recall"] <= 1
    assert 0 <= metrics["f1_score"] <= 1
    assert len(metrics["confusion_matrix"]) == 2
    assert metrics["class_labels"] == ["0", "1"]

    assert body["recommended_model_id"] in [
        result["model_id"] for result in body["results"]
    ]
    preprocessing = body["preprocessing_config"]
    assert "id" not in preprocessing["numeric_columns"]
    assert "name" not in preprocessing["numeric_columns"] + preprocessing["categorical_columns"]
    assert preprocessing["training_rows"] + preprocessing["test_rows"] <= 60


def test_classification_with_selected_features(client, auth, uploaded_dataset):
    response = train(
        client,
        auth,
        uploaded_dataset["id"],
        selected_features=["age", "score", "category"],
        algorithms=["decision_tree"],
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["selected_features"] == ["age", "score", "category"]
    assert body["results"][0]["status"] == "completed"


def test_regression_training(client, auth, uploaded_regression):
    response = train(
        client,
        auth,
        uploaded_regression["id"],
        target_column="price",
        problem_type="regression",
        algorithms=["linear_regression", "ridge", "decision_tree"],
    )
    assert response.status_code == 201, response.text
    body = response.json()

    assert body["problem_type"] == "regression"
    assert len(body["results"]) == 3
    assert all(result["status"] == "completed" for result in body["results"])

    metrics = body["results"][0]["metrics"]
    assert "mae" in metrics and "mse" in metrics
    assert "rmse" in metrics and "r2_score" in metrics
    assert metrics["rmse"] >= 0
    assert body["recommended_model_id"] is not None


def test_auto_problem_type_detection(client, auth, uploaded_dataset, uploaded_regression):
    classification = train(
        client, auth, uploaded_dataset["id"], problem_type="auto", algorithms=["decision_tree"]
    )
    assert classification.status_code == 201, classification.text
    assert classification.json()["problem_type"] == "classification"

    regression = train(
        client,
        auth,
        uploaded_regression["id"],
        target_column="price",
        problem_type="auto",
        algorithms=["linear_regression"],
    )
    assert regression.status_code == 201, regression.text
    assert regression.json()["problem_type"] == "regression"


def test_cross_validation_metrics(client, auth, uploaded_dataset):
    response = train(
        client,
        auth,
        uploaded_dataset["id"],
        algorithms=["decision_tree"],
        split_configuration={
            "test_size": 0.2,
            "random_seed": 42,
            "cross_validation": True,
        },
    )
    assert response.status_code == 201, response.text
    metrics = response.json()["results"][0]["metrics"]
    assert "cv_mean" in metrics
    assert "cv_std" in metrics
    assert metrics["cv_folds"] >= 2


def test_training_is_reproducible_with_same_seed(client, auth, uploaded_dataset):
    first = train(client, auth, uploaded_dataset["id"], algorithms=["decision_tree"])
    second = train(client, auth, uploaded_dataset["id"], algorithms=["decision_tree"])
    assert first.status_code == 201 and second.status_code == 201

    first_metrics = first.json()["results"][0]["metrics"]
    second_metrics = second.json()["results"][0]["metrics"]
    assert first_metrics["accuracy"] == second_metrics["accuracy"]
    assert first_metrics["f1_score"] == second_metrics["f1_score"]
    assert first_metrics["confusion_matrix"] == second_metrics["confusion_matrix"]


def test_training_rejects_missing_target(client, auth, uploaded_dataset):
    response = train(client, auth, uploaded_dataset["id"], target_column="nope")
    assert response.status_code == 400
    assert "does not exist" in response.json()["detail"]


def test_training_rejects_target_as_feature(client, auth, uploaded_dataset):
    response = train(
        client,
        auth,
        uploaded_dataset["id"],
        selected_features=["age", "target"],
    )
    assert response.status_code == 400


def test_training_rejects_unknown_selected_feature(client, auth, uploaded_dataset):
    response = train(
        client,
        auth,
        uploaded_dataset["id"],
        selected_features=["age", "missing_column"],
    )
    assert response.status_code == 400


def test_regression_rejects_non_numeric_target(client, auth):
    content = b"id,x,target\n" + b"".join(
        f"{index},{index},{'cheap' if index % 2 else 'expensive'}\n".encode()
        for index in range(20)
    )
    dataset = upload_csv(client, auth, content).json()

    response = train(
        client,
        auth,
        dataset["id"],
        problem_type="regression",
        algorithms=["linear_regression"],
    )
    assert response.status_code == 400
    assert "non-numeric" in response.json()["detail"]


def test_training_rejects_insufficient_rows(client, auth):
    dataset = upload_csv(client, auth, classification_csv(rows=6)).json()
    response = train(client, auth, dataset["id"])
    assert response.status_code == 400
    assert "10 usable rows" in response.json()["detail"]


def test_training_rejects_single_row_class(client, auth):
    lines = ["x,target"] + [f"{index},0" for index in range(11)] + ["99,1"]
    dataset = upload_csv(client, auth, ("\n".join(lines) + "\n").encode()).json()
    response = train(client, auth, dataset["id"])
    assert response.status_code == 400
    assert "at least two rows" in response.json()["detail"]


def test_training_rejects_unknown_algorithm(client, auth, uploaded_dataset):
    response = train(client, auth, uploaded_dataset["id"], algorithms=["magic_forest"])
    assert response.status_code == 400
    assert "not supported" in response.json()["detail"]


def test_training_rejects_invalid_split(client, auth, uploaded_dataset):
    response = train(
        client,
        auth,
        uploaded_dataset["id"],
        split_configuration={"test_size": 0.9, "random_seed": 42},
    )
    assert response.status_code == 400
    assert "test_size" in response.json()["detail"]


def test_experiment_listing_and_results(client, auth, uploaded_dataset):
    created = train(
        client,
        auth,
        uploaded_dataset["id"],
        algorithms=["decision_tree", "logistic_regression"],
    ).json()
    experiment_id = created["experiment_id"]

    listing = client.get("/api/v1/experiments/", headers=auth)
    assert listing.status_code == 200
    assert any(item["id"] == experiment_id for item in listing.json())

    filtered = client.get(
        f"/api/v1/experiments/?dataset_id={uploaded_dataset['id']}", headers=auth
    )
    assert filtered.status_code == 200
    assert any(item["id"] == experiment_id for item in filtered.json())

    detail = client.get(f"/api/v1/experiments/{experiment_id}", headers=auth)
    assert detail.status_code == 200
    assert detail.json()["status"] == "completed"

    results = client.get(
        f"/api/v1/experiments/{experiment_id}/results", headers=auth
    )
    assert results.status_code == 200
    assert len(results.json()["results"]) == 2

    leaderboard = client.get("/api/v1/experiments/results", headers=auth)
    assert leaderboard.status_code == 200
    assert len(leaderboard.json()) >= 2


def test_delete_experiment_removes_models_and_artifacts(
    client, auth, uploaded_dataset, db_session
):
    created = train(client, auth, uploaded_dataset["id"]).json()
    experiment_id = created["experiment_id"]
    model_id = created["recommended_model_id"]

    artifact_path = (
        db_session.query(ModelResults.model_artifact_path)
        .filter(ModelResults.id == model_id)
        .scalar()
    )
    assert artifact_path and Path(artifact_path).exists()

    response = client.delete(f"/api/v1/experiments/{experiment_id}", headers=auth)
    assert response.status_code == 200
    assert client.get(f"/api/v1/experiments/{experiment_id}", headers=auth).status_code == 404
    assert client.get(f"/api/v1/models/{model_id}", headers=auth).status_code == 404
    assert not Path(artifact_path).exists()


def test_experiments_are_scoped_to_owner(
    client, auth, other_auth, uploaded_dataset, uploaded_regression
):
    created = train(client, auth, uploaded_dataset["id"]).json()
    experiment_id = created["experiment_id"]

    assert (
        client.get(f"/api/v1/experiments/{experiment_id}", headers=other_auth).status_code
        == 404
    )
    assert (
        client.delete(f"/api/v1/experiments/{experiment_id}", headers=other_auth).status_code
        == 404
    )
    foreign_training = train(client, other_auth, uploaded_dataset["id"])
    assert foreign_training.status_code == 404


def test_every_classification_algorithm_trains(client, auth, uploaded_dataset):
    from app.services.ml_service import CLASSIFICATION_ALGORITHMS

    algorithms = sorted(CLASSIFICATION_ALGORITHMS)
    try:
        import xgboost  # noqa: F401
    except ImportError:  # pragma: no cover - only when optional dep is absent
        algorithms.remove("xgboost")

    response = train(client, auth, uploaded_dataset["id"], algorithms=algorithms)
    assert response.status_code == 201, response.text
    results = {result["algorithm"]: result for result in response.json()["results"]}
    assert set(results) == set(algorithms)
    for algorithm, result in results.items():
        assert result["status"] == "completed", (algorithm, result.get("error"))
        assert 0 <= result["metrics"]["accuracy"] <= 1


def test_every_regression_algorithm_trains(client, auth, uploaded_regression):
    from app.services.ml_service import REGRESSION_ALGORITHMS

    algorithms = sorted(REGRESSION_ALGORITHMS)
    try:
        import xgboost  # noqa: F401
    except ImportError:  # pragma: no cover - only when optional dep is absent
        algorithms.remove("xgboost")

    response = train(
        client,
        auth,
        uploaded_regression["id"],
        target_column="price",
        problem_type="regression",
        algorithms=algorithms,
    )
    assert response.status_code == 201, response.text
    results = {result["algorithm"]: result for result in response.json()["results"]}
    assert set(results) == set(algorithms)
    for algorithm, result in results.items():
        assert result["status"] == "completed", (algorithm, result.get("error"))
        assert result["metrics"]["rmse"] >= 0


def test_regression_cross_validation(client, auth, uploaded_regression):
    response = train(
        client,
        auth,
        uploaded_regression["id"],
        target_column="price",
        problem_type="regression",
        algorithms=["linear_regression"],
        split_configuration={
            "test_size": 0.2,
            "random_seed": 42,
            "cross_validation": True,
        },
    )
    assert response.status_code == 201, response.text
    metrics = response.json()["results"][0]["metrics"]
    assert metrics["cv_folds"] >= 2
    assert "cv_mean" in metrics and "cv_std" in metrics


def test_algorithm_failure_is_recorded_without_aborting(
    client, auth, uploaded_dataset, monkeypatch
):
    from app.services import ml_service

    original = ml_service.create_estimator

    def failing_estimator(algorithm, problem_type, random_seed):
        if algorithm == "decision_tree":
            raise RuntimeError("synthetic training failure")
        return original(algorithm, problem_type, random_seed)

    monkeypatch.setattr(ml_service, "create_estimator", failing_estimator)

    response = train(
        client,
        auth,
        uploaded_dataset["id"],
        algorithms=["decision_tree", "logistic_regression"],
    )
    assert response.status_code == 201, response.text
    body = response.json()
    results = {result["algorithm"]: result for result in body["results"]}

    assert results["decision_tree"]["status"] == "failed"
    assert "synthetic training failure" in results["decision_tree"]["error"]
    assert results["logistic_regression"]["status"] == "completed"
    assert body["recommended_model_id"] == results["logistic_regression"]["model_id"]


def test_unsupported_problem_type_is_validated(client, auth, uploaded_dataset):
    response = train(
        client, auth, uploaded_dataset["id"], problem_type="clustering"
    )
    assert response.status_code == 422
