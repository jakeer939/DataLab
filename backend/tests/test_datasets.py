from __future__ import annotations

from io import BytesIO

import pandas as pd

from .conftest import classification_csv, upload_csv


def test_upload_csv_creates_dataset_and_original_version(client, auth):
    content = classification_csv(rows=12)
    response = upload_csv(client, auth, content, filename="people.csv", name="People")
    assert response.status_code == 201, response.text
    body = response.json()

    assert body["name"] == "People"
    assert body["original_filename"] == "people.csv"
    assert body["file_format"] == "csv"
    assert body["row_count"] == 12
    assert body["column_count"] == 7
    assert body["status"] == "uploaded"
    assert body["version_count"] == 1

    versions = client.get(
        f"/api/v1/datasets/{body['id']}/versions", headers=auth
    ).json()
    assert len(versions) == 1
    assert versions[0]["version_number"] == 0
    assert versions[0]["version_type"] == "original"


def test_upload_uses_filename_when_name_blank(client, auth):
    response = upload_csv(client, auth, classification_csv(rows=5), filename="my_data.csv")
    assert response.status_code == 201
    assert response.json()["name"] == "my_data"


def test_upload_xlsx(client, auth):
    frame = pd.DataFrame(
        {
            "age": [21, 34, 45, 29],
            "score": [88.0, 70.0, 65.0, 91.0],
            "group": ["a", "b", "a", "c"],
        }
    )
    buffer = BytesIO()
    frame.to_excel(buffer, index=False, engine="openpyxl")

    response = client.post(
        "/api/v1/datasets/upload",
        headers=auth,
        files={
            "file": (
                "people.xlsx",
                buffer.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
        data={"name": "Excel data"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["file_format"] == "xlsx"
    assert body["row_count"] == 4

    preview = client.get(
        f"/api/v1/datasets/{body['id']}/preview", headers=auth
    )
    assert preview.status_code == 200
    assert preview.json()["columns"] == ["age", "score", "group"]


def test_upload_rejects_file_without_extension(client, auth):
    response = upload_csv(client, auth, b"a,b\n1,2\n", filename="no_extension")
    assert response.status_code == 400


def test_upload_rejects_files_over_the_configured_limit(client, auth, monkeypatch):
    monkeypatch.setattr("app.routers.datasets.MAX_UPLOAD_BYTES", 10)
    response = upload_csv(client, auth, b"a,b\n1,2\n3,4\n")
    assert response.status_code == 413


def test_upload_accepts_latin1_encoded_csv(client, auth):
    content = "id,city\n1,München\n2,Köln\n".encode("latin-1")
    response = upload_csv(client, auth, content, filename="latin1.csv")
    assert response.status_code == 201, response.text
    preview = client.get(
        f"/api/v1/datasets/{response.json()['id']}/preview", headers=auth
    ).json()
    city_index = preview["columns"].index("city")
    assert preview["first_rows"][0][city_index] == "München"


def test_upload_rejects_unsupported_extension(client, auth):
    response = upload_csv(client, auth, b"a,b\n1,2\n", filename="data.txt")
    assert response.status_code == 400


def test_upload_rejects_empty_file(client, auth):
    response = upload_csv(client, auth, b"", filename="empty.csv")
    assert response.status_code == 400


def test_upload_rejects_empty_dataframe(client, auth):
    response = upload_csv(client, auth, b"a,b\n", filename="headers_only.csv")
    assert response.status_code == 400


def test_upload_rejects_duplicate_columns(client, auth):
    response = upload_csv(client, auth, b"a,a,b\n1,2,3\n", filename="dupes.csv")
    assert response.status_code == 400


def test_list_and_detail_are_scoped_to_owner(client, auth, other_auth, uploaded_dataset):
    mine = client.get("/api/v1/datasets/", headers=auth).json()
    assert any(item["id"] == uploaded_dataset["id"] for item in mine)

    theirs = client.get("/api/v1/datasets/", headers=other_auth).json()
    assert all(item["id"] != uploaded_dataset["id"] for item in theirs)

    assert (
        client.get(f"/api/v1/datasets/{uploaded_dataset['id']}", headers=auth).status_code
        == 200
    )
    assert (
        client.get(
            f"/api/v1/datasets/{uploaded_dataset['id']}", headers=other_auth
        ).status_code
        == 404
    )


def test_preview_supports_pagination(client, auth, uploaded_dataset):
    response = client.get(
        f"/api/v1/datasets/{uploaded_dataset['id']}/preview?offset=5&limit=3",
        headers=auth,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["offset"] == 5
    assert body["limit"] == 3
    assert len(body["first_rows"]) == 3
    assert body["row_count"] == uploaded_dataset["row_count"]
    assert body["columns"][0] == "id"


def test_preview_validates_limit(client, auth, uploaded_dataset):
    response = client.get(
        f"/api/v1/datasets/{uploaded_dataset['id']}/preview?limit=9999",
        headers=auth,
    )
    assert response.status_code == 422


def test_download_returns_original_bytes(client, auth):
    content = classification_csv(rows=8)
    dataset = upload_csv(client, auth, content, filename="download.csv").json()

    response = client.get(f"/api/v1/datasets/{dataset['id']}/download", headers=auth)
    assert response.status_code == 200
    assert response.content == content
    assert "download.csv" in response.headers["content-disposition"]


def test_download_rejects_foreign_version(client, auth):
    first = upload_csv(client, auth, classification_csv(rows=8)).json()
    second = upload_csv(client, auth, classification_csv(rows=9)).json()

    versions = client.get(
        f"/api/v1/datasets/{second['id']}/versions", headers=auth
    ).json()
    foreign_version_id = versions[0]["id"]

    response = client.get(
        f"/api/v1/datasets/{first['id']}/download?version_id={foreign_version_id}",
        headers=auth,
    )
    assert response.status_code == 404


def test_delete_removes_dataset_and_dependents(client, auth):
    dataset = upload_csv(client, auth, classification_csv(rows=15)).json()

    experiment = client.post(
        "/api/v1/experiments/",
        headers=auth,
        json={
            "dataset_id": dataset["id"],
            "target_column": "target",
            "problem_type": "classification",
            "algorithms": ["decision_tree"],
            "split_configuration": {"test_size": 0.2, "random_seed": 42},
        },
    )
    assert experiment.status_code == 201, experiment.text
    model_id = experiment.json()["recommended_model_id"]

    delete = client.delete(f"/api/v1/datasets/{dataset['id']}", headers=auth)
    assert delete.status_code == 200

    assert (
        client.get(f"/api/v1/datasets/{dataset['id']}", headers=auth).status_code == 404
    )
    assert client.get(f"/api/v1/models/{model_id}", headers=auth).status_code == 404
    assert client.get("/api/v1/models/", headers=auth).json() == []


def test_delete_foreign_dataset_is_404(client, auth, other_auth, uploaded_dataset):
    response = client.delete(
        f"/api/v1/datasets/{uploaded_dataset['id']}", headers=other_auth
    )
    assert response.status_code == 404


def test_missing_dataset_returns_404(client, auth):
    assert client.get("/api/v1/datasets/999999", headers=auth).status_code == 404
    assert (
        client.get("/api/v1/datasets/999999/preview", headers=auth).status_code == 404
    )


def test_upload_requires_authentication(client):
    response = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("data.csv", classification_csv(rows=3), "text/csv")},
    )
    assert response.status_code == 401
