from __future__ import annotations

import math

from .conftest import classification_csv, messy_csv, upload_csv


def test_profile_has_expected_structure_and_statistics(client, auth):
    dataset = upload_csv(client, auth, classification_csv(rows=60)).json()
    response = client.get(f"/api/v1/profiling/{dataset['id']}", headers=auth)
    assert response.status_code == 200, response.text
    body = response.json()

    overview = body["overview"]
    assert overview["number_of_rows"] == 60
    assert overview["number_of_columns"] == 7
    assert overview["total_numerical_columns"] == 4  # id, age, score, target
    assert overview["total_categorical_columns"] == 2  # name, category
    assert overview["total_datetime_columns"] == 1  # event_date
    assert overview["total_missing_cells"] == 0
    assert overview["total_duplicate_rows"] == 0

    age_stats = body["numerical_statistics"]["age"]
    assert age_stats["mean"] == 36.1667
    assert age_stats["minimum"] == 20
    assert age_stats["maximum"] == 59
    assert age_stats["p50"] == age_stats["median"]

    assert body["column_analysis"]["event_date"]["data_type"] == "datetime"
    assert body["column_analysis"]["name"]["data_type"] == "categorical"
    assert body["column_analysis"]["category"]["number_of_unique_categories"] == 3

    correlation = body["correlation"]
    assert len(correlation["columns"]) == 4
    assert len(correlation["matrix"]) == 4
    assert all(len(row) == 4 for row in correlation["matrix"])

    charts = body["charts"]
    assert "age" in charts["histograms"]
    assert "category" in charts["bar_charts"]
    assert "age" in charts["boxplots"]


def test_profile_is_json_safe_with_missing_values(client, auth):
    dataset = upload_csv(client, auth, messy_csv()).json()
    response = client.get(f"/api/v1/profiling/{dataset['id']}", headers=auth)
    assert response.status_code == 200, response.text
    body = response.json()

    # NaN/inf must be converted to null, never emitted as invalid JSON tokens.
    raw = response.text
    assert "NaN" not in raw
    assert "Infinity" not in raw

    age = body["column_analysis"]["age"]
    assert age["missing_value_count"] == 1
    assert age["missing_value_percentage"] == round(1 / 11 * 100, 2)


def test_quality_detects_missing_duplicates_and_outliers(client, auth):
    dataset = upload_csv(client, auth, messy_csv()).json()
    response = client.get(f"/api/v1/profiling/{dataset['id']}/quality", headers=auth)
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["missing_values"]["age"]["count"] == 1
    assert body["missing_values"]["score"]["count"] == 2
    assert body["duplicate_records"]["total_duplicates"] == 1
    assert "score" in body["outliers"]
    assert body["outliers"]["score"]["method"] == "IQR"
    assert body["outliers"]["score"]["count"] >= 1


def test_quality_flags_inconsistent_data(client, auth):
    content = (
        b"id,amount,label,when\n"
        b"1,10.5, alpha ,2024-01-01\n"
        b"2,not-a-number,beta,2024-01-02\n"
        b"3,30.0,gamma,not-a-date\n"
    )
    dataset = upload_csv(client, auth, content).json()
    body = client.get(
        f"/api/v1/profiling/{dataset['id']}/quality", headers=auth
    ).json()

    inconsistent = body["inconsistent_data"]
    assert "label" in inconsistent["whitespace_columns"]
    assert "amount" in inconsistent["invalid_numerical_columns"]
    assert "when" in inconsistent["invalid_date_columns"]


def test_correlation_endpoint(client, auth, uploaded_dataset):
    response = client.get(
        f"/api/v1/profiling/{uploaded_dataset['id']}/correlation", headers=auth
    )
    assert response.status_code == 200
    body = response.json()
    assert "age" in body["columns"]
    assert "score" in body["columns"]


def test_scatter_returns_aligned_points(client, auth):
    dataset = upload_csv(client, auth, messy_csv()).json()
    response = client.get(
        f"/api/v1/profiling/{dataset['id']}/scatter?x_column=age&y_column=score",
        headers=auth,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["x_column"] == "age"
    assert body["y_column"] == "score"
    assert len(body["points"]) == 8
    assert all("x" in point and "y" in point for point in body["points"])
    assert all(not math.isnan(point["x"]) for point in body["points"])


def test_scatter_rejects_unknown_columns(client, auth, uploaded_dataset):
    response = client.get(
        f"/api/v1/profiling/{uploaded_dataset['id']}/scatter?x_column=age&y_column=nope",
        headers=auth,
    )
    assert response.status_code == 400


def test_profiling_is_scoped_to_owner(client, other_auth, uploaded_dataset):
    assert (
        client.get(f"/api/v1/profiling/{uploaded_dataset['id']}", headers=other_auth).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/v1/profiling/{uploaded_dataset['id']}/quality", headers=other_auth
        ).status_code
        == 404
    )


def test_profile_rejects_foreign_version(client, auth, uploaded_dataset):
    response = client.get(
        f"/api/v1/profiling/{uploaded_dataset['id']}?version_id=999999", headers=auth
    )
    assert response.status_code == 404
