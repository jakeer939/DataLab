from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    Datasets,
    DatasetVersions,
    Experiments,
    ModelResults,
    Predictions,
    Users,
)
from ..schemas import ExperimentConfig, ExperimentResponse
from ..security import get_current_user
from ..services.ml_service import (
    ALGORITHM_LABELS,
    CLASSIFICATION_ALGORITHMS,
    MLTrainingError,
    REGRESSION_ALGORITHMS,
    _recommended_result,
    train_experiment,
)

router = APIRouter(prefix="/experiments", tags=["Machine Learning"])


def _owned_dataset(dataset_id: int, user: Users, db: Session) -> Datasets:
    dataset = (
        db.query(Datasets)
        .filter(Datasets.id == dataset_id, Datasets.user_id == user.id)
        .first()
    )
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return dataset


def _owned_experiment(experiment_id: int, user: Users, db: Session) -> Experiments:
    experiment = (
        db.query(Experiments)
        .filter(Experiments.id == experiment_id, Experiments.user_id == user.id)
        .first()
    )
    if experiment is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return experiment


def _result_payload(model: ModelResults) -> dict:
    return {
        "model_id": model.id,
        "algorithm": model.algorithm_name,
        "algorithm_label": ALGORITHM_LABELS.get(model.algorithm_name, model.algorithm_name),
        "status": model.status,
        "metrics": model.evaluation_metrics or {},
        "training_duration": model.training_duration,
        "created_at": model.created_at,
    }


def _experiment_payload(experiment: Experiments, db: Session) -> dict:
    results = (
        db.query(ModelResults)
        .filter(ModelResults.experiment_id == experiment.id)
        .order_by(ModelResults.id.asc())
        .all()
    )
    result_payloads = [_result_payload(result) for result in results]
    recommended = _recommended_result(
        [
            {
                "model_id": result["model_id"],
                "status": result["status"],
                "metrics": result["metrics"],
                "training_duration": result["training_duration"],
            }
            for result in result_payloads
        ],
        experiment.problem_type,
    )
    return {
        "id": experiment.id,
        "dataset_version_id": experiment.dataset_version_id,
        "target_column": experiment.target_column,
        "problem_type": experiment.problem_type,
        "selected_features": experiment.selected_features or [],
        "split_configuration": experiment.split_configuration,
        "random_seed": experiment.random_seed,
        "status": experiment.status,
        "created_at": experiment.created_at,
        "results": result_payloads,
        "recommended_model_id": recommended,
    }


@router.get("/algorithms")
def list_algorithms(current_user: Users = Depends(get_current_user)):
    """Return supported algorithm identifiers for each problem type."""
    return {
        "classification": sorted(CLASSIFICATION_ALGORITHMS),
        "regression": sorted(REGRESSION_ALGORITHMS),
        "labels": ALGORITHM_LABELS,
    }


@router.post("/", response_model=ExperimentResponse, status_code=status.HTTP_201_CREATED)
def create_and_train_experiment(
    payload: ExperimentConfig,
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create an experiment and train every requested algorithm on one split."""
    dataset = _owned_dataset(payload.dataset_id, current_user, db)
    try:
        return train_experiment(
            db=db,
            dataset=dataset,
            target_column=payload.target_column,
            problem_type=payload.problem_type,
            selected_features=payload.selected_features,
            split_configuration=payload.split_configuration,
            algorithms=payload.algorithms,
        )
    except MLTrainingError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/")
def list_experiments(
    dataset_id: int | None = None,
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Experiments).filter(Experiments.user_id == current_user.id)
    if dataset_id is not None:
        dataset = _owned_dataset(dataset_id, current_user, db)
        version_ids = [
            row[0]
            for row in db.query(DatasetVersions.id)
            .filter(DatasetVersions.dataset_id == dataset.id)
            .all()
        ]
        query = query.filter(Experiments.dataset_version_id.in_(version_ids or [-1]))
    experiments = query.order_by(Experiments.created_at.desc(), Experiments.id.desc()).all()
    return [_experiment_payload(experiment, db) for experiment in experiments]


@router.get("/results")
def list_all_model_results(
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Leaderboard of every model owned by the authenticated user."""
    rows = (
        db.query(ModelResults, Experiments, DatasetVersions, Datasets)
        .join(Experiments, Experiments.id == ModelResults.experiment_id)
        .join(DatasetVersions, DatasetVersions.id == Experiments.dataset_version_id)
        .join(Datasets, Datasets.id == DatasetVersions.dataset_id)
        .filter(Experiments.user_id == current_user.id)
        .order_by(ModelResults.created_at.desc(), ModelResults.id.desc())
        .all()
    )
    payload = []
    for model, experiment, _version, dataset in rows:
        payload.append(
            {
                "id": model.id,
                "algorithm_name": model.algorithm_name,
                "algorithm_label": ALGORITHM_LABELS.get(
                    model.algorithm_name, model.algorithm_name
                ),
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
        )
    return payload


@router.get("/{experiment_id}")
def get_experiment(
    experiment_id: int,
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    experiment = _owned_experiment(experiment_id, current_user, db)
    return _experiment_payload(experiment, db)


@router.get("/{experiment_id}/results")
def get_experiment_results(
    experiment_id: int,
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    experiment = _owned_experiment(experiment_id, current_user, db)
    results = (
        db.query(ModelResults)
        .filter(ModelResults.experiment_id == experiment.id)
        .order_by(ModelResults.id.asc())
        .all()
    )
    return {
        "experiment_id": experiment.id,
        "problem_type": experiment.problem_type,
        "results": [_result_payload(result) for result in results],
        "recommended_model_id": _recommended_result(
            [
                {
                    "model_id": result.id,
                    "status": result.status,
                    "metrics": result.evaluation_metrics or {},
                    "training_duration": result.training_duration,
                }
                for result in results
            ],
            experiment.problem_type,
        ),
    }


@router.delete("/{experiment_id}")
def delete_experiment(
    experiment_id: int,
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    experiment = _owned_experiment(experiment_id, current_user, db)
    models = (
        db.query(ModelResults).filter(ModelResults.experiment_id == experiment.id).all()
    )
    model_ids = [model.id for model in models]
    paths = [model.model_artifact_path for model in models if model.model_artifact_path]

    if model_ids:
        db.query(Predictions).filter(Predictions.model_result_id.in_(model_ids)).delete(
            synchronize_session=False
        )
        db.query(ModelResults).filter(ModelResults.id.in_(model_ids)).delete(
            synchronize_session=False
        )
    db.query(Experiments).filter(Experiments.id == experiment.id).delete(
        synchronize_session=False
    )
    db.commit()

    for path in paths:
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            pass
    return {"success": True, "message": "Experiment deleted"}
