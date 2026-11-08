from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..config import MODELS_DIR
from ..database import get_db
from ..models import (
    Datasets,
    DatasetVersions,
    Experiments,
    ModelResults,
    Predictions,
    Users,
)
from ..schemas import (
    BatchPredictionResponse,
    ModelDetail,
    ModelSummary,
    PredictionRequest,
    PredictionResponse,
)
from ..security import get_current_user
from ..services.data_io import json_safe, safe_filename
from ..services.ml_service import (
    ALGORITHM_LABELS,
    MLTrainingError,
    load_artifact,
    model_input_schema,
    predict_rows,
)

router = APIRouter(prefix="/models", tags=["Saved Models"])


def _owned_model(model_id: int, user: Users, db: Session):
    row = (
        db.query(ModelResults, Experiments, DatasetVersions, Datasets)
        .join(Experiments, Experiments.id == ModelResults.experiment_id)
        .join(DatasetVersions, DatasetVersions.id == Experiments.dataset_version_id)
        .join(Datasets, Datasets.id == DatasetVersions.dataset_id)
        .filter(ModelResults.id == model_id, Experiments.user_id == user.id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Model not found")
    return row


def _summary(model: ModelResults, experiment: Experiments, dataset: Datasets) -> dict:
    return {
        "id": model.id,
        "algorithm_name": model.algorithm_name,
        "algorithm_label": ALGORITHM_LABELS.get(model.algorithm_name, model.algorithm_name),
        "experiment_id": experiment.id,
        "target_column": experiment.target_column,
        "problem_type": experiment.problem_type,
        "dataset_id": dataset.id,
        "dataset_name": dataset.name,
        "metrics": model.evaluation_metrics or {},
        "training_duration": model.training_duration,
        "status": model.status,
        "created_at": model.created_at,
    }


@router.get("/", response_model=list[ModelSummary])
def list_models(
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(ModelResults, Experiments, DatasetVersions, Datasets)
        .join(Experiments, Experiments.id == ModelResults.experiment_id)
        .join(DatasetVersions, DatasetVersions.id == Experiments.dataset_version_id)
        .join(Datasets, Datasets.id == DatasetVersions.dataset_id)
        .filter(Experiments.user_id == current_user.id)
        .order_by(ModelResults.created_at.desc(), ModelResults.id.desc())
        .all()
    )
    return [_summary(model, experiment, dataset) for model, experiment, _version, dataset in rows]


@router.get("/{model_id}", response_model=ModelDetail)
def get_model(
    model_id: int,
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    model, experiment, _version, dataset = _owned_model(model_id, current_user, db)
    detail = _summary(model, experiment, dataset)
    detail["hyperparameters"] = model.hyperparameters or {}
    detail["artifact_available"] = bool(
        model.model_artifact_path and Path(model.model_artifact_path).exists()
    )
    detail["feature_schema"] = []
    if detail["artifact_available"]:
        try:
            artifact = load_artifact(model)
            detail["feature_schema"] = model_input_schema(artifact)
        except MLTrainingError:
            detail["feature_schema"] = []
    return detail


@router.get("/{model_id}/download")
def download_model(
    model_id: int,
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    model, experiment, _version, _dataset = _owned_model(model_id, current_user, db)
    if not model.model_artifact_path:
        raise HTTPException(status_code=404, detail="Model artifact is not available")
    path = Path(model.model_artifact_path).resolve()
    try:
        if not path.is_relative_to(MODELS_DIR) or path.suffix != ".joblib":
            raise HTTPException(status_code=400, detail="Invalid model artifact path")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid model artifact path")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Model artifact is not available")
    return FileResponse(
        path=str(path),
        filename=f"{experiment.target_column}_{model.algorithm_name}_{model.id}.joblib",
        media_type="application/octet-stream",
    )


@router.delete("/{model_id}")
def delete_model(
    model_id: int,
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    model, _experiment, _version, _dataset = _owned_model(model_id, current_user, db)
    path = model.model_artifact_path
    db.query(Predictions).filter(Predictions.model_result_id == model.id).delete(
        synchronize_session=False
    )
    db.query(ModelResults).filter(ModelResults.id == model.id).delete(synchronize_session=False)
    db.commit()
    if path:
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            pass
    return {"success": True, "message": "Model deleted"}


@router.post("/{model_id}/predict", response_model=PredictionResponse)
def predict_single(
    model_id: int,
    payload: PredictionRequest,
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    model, _experiment, _version, _dataset = _owned_model(model_id, current_user, db)
    if model.status != "completed":
        raise HTTPException(status_code=400, detail="This model did not train successfully")
    try:
        artifact = load_artifact(model)
        result = predict_rows(artifact, [payload.data])[0]
    except MLTrainingError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    prediction = Predictions(
        model_result_id=model.id,
        input_data=json_safe(payload.data),
        predicted_output=json_safe(result),
    )
    db.add(prediction)
    db.commit()
    return {
        "model_id": model.id,
        "prediction": result["prediction"],
        "probability": result.get("probability"),
    }


@router.post("/{model_id}/predict/batch", response_model=BatchPredictionResponse)
async def predict_batch(
    model_id: int,
    file: UploadFile = File(...),
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    model, _experiment, _version, _dataset = _owned_model(model_id, current_user, db)
    if model.status != "completed":
        raise HTTPException(status_code=400, detail="This model did not train successfully")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded CSV is empty")
    try:
        frame = pd.read_csv(io.BytesIO(content))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Unable to read CSV: {exc}")
    if frame.empty:
        raise HTTPException(status_code=400, detail="CSV contains no rows")
    if len(frame) > 5000:
        raise HTTPException(status_code=400, detail="Batch prediction is limited to 5000 rows")

    try:
        artifact = load_artifact(model)
        results = predict_rows(artifact, frame.to_dict(orient="records"))
    except MLTrainingError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    predictions = [result["prediction"] for result in results]
    prediction = Predictions(
        model_result_id=model.id,
        input_data={
            "filename": safe_filename(file.filename, "batch.csv"),
            "row_count": int(len(frame)),
            "columns": [str(column) for column in frame.columns],
        },
        predicted_output={
            "predictions": json_safe(predictions[:1000]),
            "truncated": len(predictions) > 1000,
        },
    )
    db.add(prediction)
    db.commit()
    return {"model_id": model.id, "row_count": len(predictions), "predictions": predictions}


@router.get("/{model_id}/predictions")
def prediction_history(
    model_id: int,
    limit: int = Query(50, ge=1, le=500),
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    model, _experiment, _version, _dataset = _owned_model(model_id, current_user, db)
    rows = (
        db.query(Predictions)
        .filter(Predictions.model_result_id == model.id)
        .order_by(Predictions.created_at.desc(), Predictions.id.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": row.id,
            "model_id": row.model_result_id,
            "input_data": row.input_data,
            "predicted_output": row.predicted_output,
            "created_at": row.created_at,
        }
        for row in rows
    ]
