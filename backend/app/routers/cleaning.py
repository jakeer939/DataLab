from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..config import DATASETS_DIR
from ..database import get_db
from ..models import CleaningJobs, Datasets, DatasetVersions, Users
from ..schemas import APIResponse, CleaningRequest
from ..security import get_current_user
from ..services.cleaning_service import DataCleaningService
from ..services.data_io import get_versions, load_dataset_frame, safe_filename

router = APIRouter(prefix="/cleaning", tags=["Data Cleaning"])


def _owned_dataset(dataset_id: int, user: Users, db: Session) -> Datasets:
    dataset = (
        db.query(Datasets)
        .filter(Datasets.id == dataset_id, Datasets.user_id == user.id)
        .first()
    )
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return dataset


def _apply_operation(service: DataCleaningService, operation: str, columns, config: dict):
    if operation in {"missing_value_handling", "missing_values", "missing_value"}:
        return service.handle_missing_values(
            method=config.get("method", "mean"),
            columns=columns,
            fill_value=config.get("fill_value", config.get("value")),
        )
    if operation in {"remove_duplicates", "duplicates"}:
        return service.remove_duplicates(strategy=config.get("strategy", "remove_all"))
    if operation in {"outlier_handling", "outliers"}:
        return service.handle_outliers(
            method=config.get("method", "iqr"),
            columns=columns,
            operation=config.get("operation", "detect"),
            iqr_factor=float(config.get("iqr_factor", 1.5)),
            z_threshold=float(config.get("z_threshold", 3.0)),
        )
    if operation in {"encoding", "encode"}:
        return service.encode_features(
            method=config.get("method", "one_hot"), columns=columns
        )
    if operation in {"feature_scaling", "scaling"}:
        return service.scale_features(
            method=config.get("method", "standard"), columns=columns
        )
    if operation in {"data_type_conversion", "convert_type"}:
        return service.convert_data_type(
            columns=columns, target_type=config.get("target_type", "float")
        )
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Unsupported cleaning operation: {operation}",
    )


@router.post("/{dataset_id}/start", response_model=APIResponse)
def start_data_cleaning(
    dataset_id: int,
    payload: CleaningRequest,
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Apply one or more cleaning operations and store a new dataset version."""
    dataset = _owned_dataset(dataset_id, current_user, db)

    try:
        df, source_version = load_dataset_frame(db, dataset)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unable to load dataset: {exc}",
        )

    service = DataCleaningService(df)
    results = []
    try:
        for operation in payload.operations:
            results.append(
                _apply_operation(
                    service,
                    operation.operation,
                    operation.affected_columns,
                    operation.configuration or {},
                )
            )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    cleaned = service.get_cleaned_data()
    if cleaned.shape[1] == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cleaning removed every column; no output was produced",
        )
    if cleaned.shape[0] == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cleaning removed every row; no output was produced",
        )

    versions = get_versions(db, dataset.id)
    next_version = max([version.version_number for version in versions], default=-1) + 1

    version_dir = DATASETS_DIR / f"dataset_{dataset.id}" / f"v{next_version}_cleaned"
    version_dir.mkdir(parents=True, exist_ok=True)
    cleaned_path = version_dir / f"cleaned_{uuid.uuid4().hex}.csv"

    try:
        cleaned.to_csv(cleaned_path, index=False)
        version = DatasetVersions(
            dataset_id=dataset.id,
            version_number=next_version,
            file_path=str(cleaned_path),
            version_type="cleaned",
            parent_version_id=source_version.id if source_version else None,
        )
        db.add(version)
        db.flush()

        job = CleaningJobs(
            dataset_id=dataset.id,
            dataset_version_id=version.id,
            configuration=payload.model_dump(),
            operation_summary={
                "rows_before": int(len(df)),
                "rows_after": int(len(cleaned)),
                "columns_before": int(df.shape[1]),
                "columns_after": int(cleaned.shape[1]),
                "results": results,
                "history": service.get_cleaning_history(),
            },
            status="completed",
        )
        db.add(job)
        dataset.row_count = int(len(cleaned))
        dataset.column_count = int(cleaned.shape[1])
        dataset.status = "cleaned"
        db.commit()
        db.refresh(version)
    except Exception as exc:
        db.rollback()
        shutil.rmtree(version_dir, ignore_errors=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save cleaned dataset: {exc}",
        )

    return APIResponse(
        success=True,
        message="Data cleaning completed successfully",
        data={
            "version_id": version.id,
            "version_number": version.version_number,
            "cleaning_history": service.get_cleaning_history(),
            "operations": results,
            "remaining_rows": int(len(cleaned)),
            "remaining_columns": int(cleaned.shape[1]),
            "final_columns": [str(column) for column in cleaned.columns],
        },
    )


@router.get("/{dataset_id}/cleaning-history", response_model=APIResponse)
def get_cleaning_history(
    dataset_id: int,
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    dataset = _owned_dataset(dataset_id, current_user, db)
    jobs = (
        db.query(CleaningJobs)
        .filter(CleaningJobs.dataset_id == dataset.id)
        .order_by(CleaningJobs.created_at.desc(), CleaningJobs.id.desc())
        .all()
    )
    versions = get_versions(db, dataset.id)
    return APIResponse(
        success=True,
        message="Cleaning history retrieved",
        data={
            "cleaning_history": [
                {
                    "job_id": job.id,
                    "version_id": job.dataset_version_id,
                    "status": job.status,
                    "configuration": job.configuration,
                    "summary": job.operation_summary,
                    "created_at": job.created_at,
                }
                for job in jobs
            ],
            "versions": [
                {
                    "id": version.id,
                    "version_number": version.version_number,
                    "version_type": version.version_type,
                    "parent_version_id": version.parent_version_id,
                    "created_at": version.created_at,
                }
                for version in versions
            ],
            "version_count": len(versions),
        },
    )


@router.get("/{dataset_id}/download")
def download_cleaned_dataset(
    dataset_id: int,
    version_id: int | None = Query(None),
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Download a cleaned version (latest by default) as CSV."""
    dataset = _owned_dataset(dataset_id, current_user, db)

    query = db.query(DatasetVersions).filter(DatasetVersions.dataset_id == dataset.id)
    if version_id is not None:
        query = query.filter(DatasetVersions.id == version_id)
    else:
        query = query.filter(DatasetVersions.version_type == "cleaned")
    version = query.order_by(DatasetVersions.version_number.desc()).first()

    if version is None:
        # Fall back to the latest version (which may be the original upload).
        version = (
            db.query(DatasetVersions)
            .filter(DatasetVersions.dataset_id == dataset.id)
            .order_by(DatasetVersions.version_number.desc())
            .first()
        )
    if version is None:
        raise HTTPException(status_code=404, detail="No dataset version found")

    path = Path(version.file_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Dataset file not found")

    base = safe_filename(dataset.name, "dataset").rsplit(".", 1)[0]
    return FileResponse(
        path=str(path),
        filename=f"{base}_v{version.version_number}.csv",
        media_type="text/csv",
    )
