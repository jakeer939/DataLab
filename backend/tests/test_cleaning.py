from __future__ import annotations

from .conftest import classification_csv, messy_csv, upload_csv


def clean(client, headers, dataset_id, operations):
    return client.post(
        f"/api/v1/cleaning/{dataset_id}/start",
        headers=headers,
        json={"operations": operations},
    )


def latest_preview(client, headers, dataset_id, version_id=None):
    url = f"/api/v1/datasets/{dataset_id}/preview?limit=100"
    if version_id is not None:
        url += f"&version_id={version_id}"
    response = client.get(url, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_mean_imputation(client, auth):
    dataset = upload_csv(client, auth, messy_csv()).json()
    response = clean(
        client,
        auth,
        dataset["id"],
        [
            {
                "operation": "missing_value_handling",
                "affected_columns": ["age", "score"],
                "configuration": {"method": "mean"},
            }
        ],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["success"] is True
    assert body["data"]["version_number"] == 1
    assert body["data"]["remaining_rows"] == 11

    preview = latest_preview(client, auth, dataset["id"])
    age_index = preview["columns"].index("age")
    score_index = preview["columns"].index("score")
    name_index = preview["columns"].index("name")
    bob = next(row for row in preview["first_rows"] if row[name_index] == "Bob")
    assert bob[age_index] == 33.1
    assert all(row[age_index] is not None for row in preview["first_rows"])
    assert all(row[score_index] is not None for row in preview["first_rows"])


def test_median_and_mode_imputation(client, auth):
    dataset = upload_csv(client, auth, messy_csv()).json()
    response = clean(
        client,
        auth,
        dataset["id"],
        [
            {
                "operation": "missing_value_handling",
                "affected_columns": ["age"],
                "configuration": {"method": "median"},
            },
            {
                "operation": "missing_value_handling",
                "affected_columns": ["score"],
                "configuration": {"method": "mode"},
            },
        ],
    )
    assert response.status_code == 200, response.text
    preview = latest_preview(client, auth, dataset["id"])
    age_index = preview["columns"].index("age")
    assert all(row[age_index] is not None for row in preview["first_rows"])


def test_drop_missing_rows(client, auth):
    dataset = upload_csv(client, auth, messy_csv()).json()
    response = clean(
        client,
        auth,
        dataset["id"],
        [
            {
                "operation": "missing_value_handling",
                "affected_columns": ["age", "score"],
                "configuration": {"method": "drop"},
            }
        ],
    )
    assert response.status_code == 200, response.text
    body = response.json()["data"]
    assert body["remaining_rows"] == 8
    assert body["operations"][0]["records_removed"] == 3


def test_remove_duplicates_strategies(client, auth):
    dataset = upload_csv(client, auth, messy_csv()).json()
    response = clean(
        client,
        auth,
        dataset["id"],
        [{"operation": "remove_duplicates", "configuration": {"strategy": "remove_all"}}],
    )
    assert response.status_code == 200, response.text
    # remove_all uses keep=False, so both copies of the duplicated row go.
    assert response.json()["data"]["remaining_rows"] == 9

    keep_dataset = upload_csv(client, auth, messy_csv()).json()
    response = clean(
        client,
        auth,
        keep_dataset["id"],
        [{"operation": "remove_duplicates", "configuration": {"strategy": "keep_first"}}],
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["remaining_rows"] == 10


def test_outlier_remove(client, auth):
    dataset = upload_csv(client, auth, messy_csv()).json()
    response = clean(
        client,
        auth,
        dataset["id"],
        [
            {
                "operation": "outlier_handling",
                "affected_columns": ["score"],
                "configuration": {"method": "iqr", "operation": "remove"},
            }
        ],
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["operations"][0]["detected_outliers"][0]["column"] == "score"
    assert data["remaining_rows"] == 10

    preview = latest_preview(client, auth, dataset["id"])
    score_index = preview["columns"].index("score")
    scores = [row[score_index] for row in preview["first_rows"] if row[score_index] is not None]
    assert max(scores) < 500


def test_outlier_cap(client, auth):
    dataset = upload_csv(client, auth, messy_csv()).json()
    response = clean(
        client,
        auth,
        dataset["id"],
        [
            {
                "operation": "outlier_handling",
                "affected_columns": ["score"],
                "configuration": {"method": "iqr", "operation": "cap"},
            }
        ],
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    upper = data["operations"][0]["detected_outliers"][0]["upper_bound"]

    preview = latest_preview(client, auth, dataset["id"])
    score_index = preview["columns"].index("score")
    scores = [row[score_index] for row in preview["first_rows"] if row[score_index] is not None]
    capped_max = max(scores)
    assert capped_max < 500
    assert abs(capped_max - upper) < 1e-3


def test_z_score_outlier_detection(client, auth):
    dataset = upload_csv(client, auth, messy_csv()).json()
    response = clean(
        client,
        auth,
        dataset["id"],
        [
            {
                "operation": "outlier_handling",
                "affected_columns": ["score"],
                "configuration": {
                    "method": "z_score",
                    "operation": "detect",
                    "z_threshold": 2.0,
                },
            }
        ],
    )
    assert response.status_code == 200, response.text
    detected = response.json()["data"]["operations"][0]["detected_outliers"]
    assert detected and detected[0]["method"] == "Z-score"


def test_one_hot_encoding(client, auth):
    dataset = upload_csv(client, auth, messy_csv()).json()
    response = clean(
        client,
        auth,
        dataset["id"],
        [
            {
                "operation": "encoding",
                "affected_columns": ["category"],
                "configuration": {"method": "one_hot"},
            }
        ],
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert "category" not in data["final_columns"]
    assert len(data["final_columns"]) == 6  # 5 original - 1 + 2 one-hot columns


def test_ordinal_encoding(client, auth):
    dataset = upload_csv(client, auth, messy_csv()).json()
    response = clean(
        client,
        auth,
        dataset["id"],
        [
            {
                "operation": "encoding",
                "affected_columns": ["category"],
                "configuration": {"method": "ordinal"},
            }
        ],
    )
    assert response.status_code == 200, response.text
    preview = latest_preview(client, auth, dataset["id"])
    category_index = preview["columns"].index("category")
    values = {row[category_index] for row in preview["first_rows"]}
    assert values <= {0, 1, 2}


def test_standard_scaling(client, auth):
    dataset = upload_csv(client, auth, classification_csv(rows=40)).json()
    response = clean(
        client,
        auth,
        dataset["id"],
        [
            {
                "operation": "feature_scaling",
                "affected_columns": ["age", "score"],
                "configuration": {"method": "standard"},
            }
        ],
    )
    assert response.status_code == 200, response.text
    preview = latest_preview(client, auth, dataset["id"])
    age_index = preview["columns"].index("age")
    values = [row[age_index] for row in preview["first_rows"]]
    assert abs(sum(values) / len(values)) < 1e-6
    assert abs(max(values) - min(values)) > 1


def test_data_type_conversion(client, auth):
    dataset = upload_csv(client, auth, classification_csv(rows=12)).json()
    response = clean(
        client,
        auth,
        dataset["id"],
        [
            {
                "operation": "data_type_conversion",
                "affected_columns": ["age"],
                "configuration": {"target_type": "float"},
            }
        ],
    )
    assert response.status_code == 200, response.text
    preview = latest_preview(client, auth, dataset["id"])
    assert "float" in preview["data_types"]["age"]


def test_multiple_operations_and_versioning(client, auth):
    dataset = upload_csv(client, auth, messy_csv()).json()

    first = clean(
        client,
        auth,
        dataset["id"],
        [
            {
                "operation": "missing_value_handling",
                "affected_columns": ["age", "score"],
                "configuration": {"method": "mean"},
            },
            {"operation": "remove_duplicates", "configuration": {}},
        ],
    )
    assert first.status_code == 200, first.text
    assert first.json()["data"]["version_number"] == 1

    second = clean(
        client,
        auth,
        dataset["id"],
        [{"operation": "remove_duplicates", "configuration": {}}],
    )
    assert second.status_code == 200, second.text
    assert second.json()["data"]["version_number"] == 2

    versions = client.get(
        f"/api/v1/datasets/{dataset['id']}/versions", headers=auth
    ).json()
    assert [version["version_number"] for version in versions] == [0, 1, 2]

    detail = client.get(f"/api/v1/datasets/{dataset['id']}", headers=auth).json()
    assert detail["version_count"] == 3
    assert detail["status"] == "cleaned"


def test_original_version_is_not_mutated(client, auth):
    dataset = upload_csv(client, auth, messy_csv()).json()
    versions = client.get(
        f"/api/v1/datasets/{dataset['id']}/versions", headers=auth
    ).json()
    original_id = versions[0]["id"]

    response = clean(
        client,
        auth,
        dataset["id"],
        [
            {
                "operation": "missing_value_handling",
                "affected_columns": ["age"],
                "configuration": {"method": "mean"},
            }
        ],
    )
    assert response.status_code == 200

    original = latest_preview(client, auth, dataset["id"], version_id=original_id)
    age_index = original["columns"].index("age")
    assert any(row[age_index] is None for row in original["first_rows"])

    cleaned = latest_preview(client, auth, dataset["id"])
    assert all(row[age_index] is not None for row in cleaned["first_rows"])


def test_cleaning_history_and_download(client, auth):
    dataset = upload_csv(client, auth, messy_csv()).json()
    clean(
        client,
        auth,
        dataset["id"],
        [{"operation": "remove_duplicates", "configuration": {}}],
    )

    history = client.get(
        f"/api/v1/cleaning/{dataset['id']}/cleaning-history", headers=auth
    )
    assert history.status_code == 200, history.text
    body = history.json()["data"]
    assert len(body["cleaning_history"]) == 1
    assert body["cleaning_history"][0]["status"] == "completed"
    assert body["version_count"] == 2

    download = client.get(f"/api/v1/cleaning/{dataset['id']}/download", headers=auth)
    assert download.status_code == 200
    assert download.headers["content-type"].startswith("text/csv")
    text = download.content.decode("utf-8")
    assert text.count("\n") == 10  # header + 9 deduplicated rows


def test_invalid_operation_is_rejected(client, auth, uploaded_dataset):
    response = clean(
        client,
        auth,
        uploaded_dataset["id"],
        [{"operation": "does_not_exist", "configuration": {}}],
    )
    assert response.status_code == 400


def test_invalid_method_is_rejected(client, auth, uploaded_dataset):
    response = clean(
        client,
        auth,
        uploaded_dataset["id"],
        [
            {
                "operation": "missing_value_handling",
                "affected_columns": ["age"],
                "configuration": {"method": "teleport"},
            }
        ],
    )
    assert response.status_code == 400


def test_cleaning_all_rows_removed_is_rejected(client, auth):
    dataset = upload_csv(client, auth, b"a,b\n,1\n2,\n").json()
    response = clean(
        client,
        auth,
        dataset["id"],
        [
            {
                "operation": "missing_value_handling",
                "affected_columns": ["a", "b"],
                "configuration": {"method": "drop"},
            }
        ],
    )
    assert response.status_code == 400


def test_cleaning_requires_at_least_one_operation(client, auth, uploaded_dataset):
    response = client.post(
        f"/api/v1/cleaning/{uploaded_dataset['id']}/start",
        headers=auth,
        json={"operations": []},
    )
    assert response.status_code == 422


def test_cleaning_is_scoped_to_owner(client, other_auth, uploaded_dataset):
    response = clean(
        client,
        other_auth,
        uploaded_dataset["id"],
        [{"operation": "remove_duplicates", "configuration": {}}],
    )
    assert response.status_code == 404
