from __future__ import annotations

from pathlib import Path

import pytest

from app.models import Experiments, ModelResults

from .conftest import classification_csv, upload_csv


def train_model(client, headers, dataset_id, algorithms=None):
    response = client.post(
        "/api/v1/experiments/",
        headers=headers,
        json={
            "dataset_id": dataset_id,
            "target_column": "target",
            "problem_type": "classification",
            "algorithms": algorithms or ["decision_tree"],
            "split_configuration": {"test_size": 0.2, "random_seed": 42},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def trained(client, auth, uploaded_dataset):
    experiment = train_model(client, auth, uploaded_dataset["id"])
    return {
        "dataset": uploaded_dataset,
        "experiment": experiment,
        "model_id": experiment["results"][0]["model_id"],
    }


SAMPLE_ROW = {
    "age": 30,
    "score": 80,
    "category": "alpha",
    "event_date": "2024-01-05",
}


def test_list_models_returns_owned_models(client, auth, trained):
    response = client.get("/api/v1/models/", headers=auth)
    assert response.status_code == 200, response.text
    models = response.json()
    assert len(models) == 1
    model = models[0]
    assert model["id"] == trained["model_id"]
    assert model["algorithm_name"] == "decision_tree"
    assert model["problem_type"] == "classification"
    assert model["dataset_id"] == trained["dataset"]["id"]
    assert model["dataset_name"] == trained["dataset"]["name"]
    assert model["status"] == "completed"


def test_model_detail_includes_feature_schema(client, auth, trained):
    response = client.get(f"/api/v1/models/{trained['model_id']}", headers=auth)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["artifact_available"] is True
    assert body["hyperparameters"]["label"] == "Decision Tree"
    schema = {entry["name"]: entry for entry in body["feature_schema"]}
    assert schema["age"]["type"] == "numeric"
    assert schema["score"]["type"] == "numeric"
    assert schema["category"]["type"] == "categorical"
    assert "alpha" in schema["category"]["categories"]


def test_model_download(client, auth, trained):
    response = client.get(
        f"/api/v1/models/{trained['model_id']}/download", headers=auth
    )
    assert response.status_code == 200
    assert len(response.content) > 0
    assert ".joblib" in response.headers["content-disposition"]


def test_single_prediction_returns_label_and_probabilities(client, auth, trained):
    response = client.post(
        f"/api/v1/models/{trained['model_id']}/predict",
        headers=auth,
        json={"data": SAMPLE_ROW},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["model_id"] == trained["model_id"]
    assert body["prediction"] in {"0", "1"}
    assert set(body["probability"]) == {"0", "1"}
    assert abs(sum(body["probability"].values()) - 1) < 1e-3


def test_prediction_is_persisted_in_history(client, auth, trained):
    row = {**SAMPLE_ROW, "age": 44, "score": 55}
    assert (
        client.post(
            f"/api/v1/models/{trained['model_id']}/predict",
            headers=auth,
            json={"data": row},
        ).status_code
        == 200
    )

    history = client.get(
        f"/api/v1/models/{trained['model_id']}/predictions", headers=auth
    )
    assert history.status_code == 200
    records = history.json()
    assert len(records) == 1
    assert records[0]["input_data"]["age"] == 44
    assert records[0]["predicted_output"]["prediction"] in {"0", "1"}


def test_prediction_requires_all_features(client, auth, trained):
    response = client.post(
        f"/api/v1/models/{trained['model_id']}/predict",
        headers=auth,
        json={"data": {"age": 30}},
    )
    assert response.status_code == 400
    assert "Missing required feature" in response.json()["detail"]


def test_batch_prediction(client, auth, trained):
    csv = (
        "age,score,category,event_date\n"
        "30,80,alpha,2024-01-05\n"
        "45,60,beta,2024-01-06\n"
        "22,91,gamma,2024-01-07\n"
    ).encode()
    response = client.post(
        f"/api/v1/models/{trained['model_id']}/predict/batch",
        headers=auth,
        files={"file": ("batch.csv", csv, "text/csv")},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["row_count"] == 3
    assert len(body["predictions"]) == 3
    assert all(prediction in {"0", "1"} for prediction in body["predictions"])

    history = client.get(
        f"/api/v1/models/{trained['model_id']}/predictions", headers=auth
    ).json()
    assert len(history) == 1
    assert history[0]["input_data"]["row_count"] == 3


def test_batch_prediction_rejects_missing_column(client, auth, trained):
    csv = b"age,score\n30,80\n"
    response = client.post(
        f"/api/v1/models/{trained['model_id']}/predict/batch",
        headers=auth,
        files={"file": ("batch.csv", csv, "text/csv")},
    )
    assert response.status_code == 400
    assert "Missing required feature" in response.json()["detail"]


def test_batch_prediction_rejects_empty_file(client, auth, trained):
    response = client.post(
        f"/api/v1/models/{trained['model_id']}/predict/batch",
        headers=auth,
        files={"file": ("batch.csv", b"", "text/csv")},
    )
    assert response.status_code == 400


def test_delete_model_removes_artifact(client, auth, trained, db_session):
    artifact_path = (
        db_session.query(ModelResults.model_artifact_path)
        .filter(ModelResults.id == trained["model_id"])
        .scalar()
    )
    assert artifact_path and Path(artifact_path).exists()

    response = client.delete(f"/api/v1/models/{trained['model_id']}", headers=auth)
    assert response.status_code == 200
    assert client.get(f"/api/v1/models/{trained['model_id']}", headers=auth).status_code == 404
    assert not Path(artifact_path).exists()


def test_failed_model_cannot_predict(client, auth, trained, db_session):
    experiment_id = trained["experiment"]["experiment_id"]
    failed = ModelResults(
        experiment_id=experiment_id,
        algorithm_name="broken_algorithm",
        hyperparameters={},
        evaluation_metrics={"error": "boom"},
        training_duration=0.1,
        model_artifact_path=None,
        status="failed",
    )
    db_session.add(failed)
    db_session.commit()
    db_session.refresh(failed)

    detail = client.get(f"/api/v1/models/{failed.id}", headers=auth)
    assert detail.status_code == 200
    assert detail.json()["artifact_available"] is False
    assert detail.json()["feature_schema"] == []

    response = client.post(
        f"/api/v1/models/{failed.id}/predict",
        headers=auth,
        json={"data": SAMPLE_ROW},
    )
    assert response.status_code == 400
    assert "did not train successfully" in response.json()["detail"]


def test_corrupt_artifact_is_reported_not_crashed(
    client, auth, trained, db_session
):
    artifact_path = (
        db_session.query(ModelResults.model_artifact_path)
        .filter(ModelResults.id == trained["model_id"])
        .scalar()
    )
    Path(artifact_path).write_bytes(b"this is not a joblib payload")

    detail = client.get(f"/api/v1/models/{trained['model_id']}", headers=auth)
    assert detail.status_code == 200
    assert detail.json()["artifact_available"] is True
    assert detail.json()["feature_schema"] == []

    prediction = client.post(
        f"/api/v1/models/{trained['model_id']}/predict",
        headers=auth,
        json={"data": SAMPLE_ROW},
    )
    assert prediction.status_code == 400
    assert "Unable to load model artifact" in prediction.json()["detail"]


def test_failed_model_artifact_cannot_be_downloaded(client, auth, trained, db_session):
    failed = ModelResults(
        experiment_id=trained["experiment"]["experiment_id"],
        algorithm_name="failed_download",
        hyperparameters={},
        evaluation_metrics={},
        training_duration=0.0,
        model_artifact_path=None,
        status="failed",
    )
    db_session.add(failed)
    db_session.commit()
    db_session.refresh(failed)

    response = client.get(f"/api/v1/models/{failed.id}/download", headers=auth)
    assert response.status_code == 404


def test_models_are_scoped_to_owner(client, other_auth, trained):
    assert client.get("/api/v1/models/", headers=other_auth).json() == []
    assert (
        client.get(f"/api/v1/models/{trained['model_id']}", headers=other_auth).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/v1/models/{trained['model_id']}/download", headers=other_auth
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/models/{trained['model_id']}/predict",
            headers=other_auth,
            json={"data": SAMPLE_ROW},
        ).status_code
        == 404
    )
    assert (
        client.delete(f"/api/v1/models/{trained['model_id']}", headers=other_auth).status_code
        == 404
    )


def test_missing_model_returns_404(client, auth):
    assert client.get("/api/v1/models/999999", headers=auth).status_code == 404


def test_model_requires_authentication(client):
    assert client.get("/api/v1/models/").status_code == 401
