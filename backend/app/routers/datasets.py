from __future__ import annotations

import shutil
import uuid
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..config import ALLOWED_EXTENSIONS, DATASETS_DIR, MAX_UPLOAD_BYTES
from ..database import get_db
from ..models import (
    CleaningJobs,
    Datasets,
    DatasetVersions,
    Experiments,
    ModelResults,
    Predictions,
    Users,
)
from ..schemas import DatasetInfo, DatasetPreview, DatasetVersionInfo
from ..security import get_current_user
from ..services.data_io import (
    dataframe_preview,
    get_latest_version,
    get_versions,
    load_dataset_frame,
    safe_filename,
)

router = APIRouter(prefix="/datasets", tags=["Dataset Management"])


def _get_owned_dataset(dataset_id: int, user: Users, db: Session) -> Datasets:
    dataset = (
        db.query(Datasets)
        .filter(Datasets.id == dataset_id, Datasets.user_id == user.id)
        .first()
    )
    if dataset is None:
        # Deliberately do not reveal whether another user's dataset exists.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")
    return dataset


def _dataset_payload(dataset: Datasets, version_count: int) -> dict:
    return {
        "id": dataset.id,
        "name": dataset.name,
        "original_filename": dataset.original_filename,
        "file_format": dataset.file_format,
        "row_count": dataset.row_count,
        "column_count": dataset.column_count,
        "status": dataset.status,
        "created_at": dataset.created_at,
        "version_count": version_count,
    }


def _raw_header(content: bytes, ext: str) -> list[str]:
    """Return the file's header row before pandas mangles duplicate names.

    ``pandas`` silently renames repeated headers (``a, a -> a, a.1``), which
    would hide a genuinely broken upload. Reading the header row separately
    lets us reject duplicate column names with an actionable error.
    """
    if ext == "csv":
        try:
            raw = pd.read_csv(
                BytesIO(content), header=None, nrows=1, encoding="utf-8-sig"
            )
        except UnicodeDecodeError:
            raw = pd.read_csv(
                BytesIO(content), header=None, nrows=1, encoding="latin-1"
            )
    else:
        raw = pd.read_excel(BytesIO(content), header=None, nrows=1)
    if raw.empty:
        return []
    return [str(value).strip() for value in raw.iloc[0].tolist()]


def _parse_upload(content: bytes, ext: str) -> pd.DataFrame:
    try:
        header = _raw_header(content, ext)
        if len(header) != len(set(header)):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Dataset contains duplicate column names",
            )
        if ext == "csv":
            try:
                return pd.read_csv(BytesIO(content), encoding="utf-8-sig")
            except UnicodeDecodeError:
                return pd.read_csv(BytesIO(content), encoding="latin-1")
        if ext in {"xlsx", "xls"}:
            return pd.read_excel(BytesIO(content))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to read file: {exc}",
        )
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Unsupported file extension '.{ext}'. Allowed: csv, xlsx, xls",
    )


@router.post("/upload", response_model=DatasetInfo, status_code=status.HTTP_201_CREATED)
async def upload_dataset(
    file: UploadFile = File(...),
    name: str = Form(""),
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upload a CSV or Excel dataset and create its original version."""
    original_filename = safe_filename(file.filename)
    if "." not in original_filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must have a .csv, .xlsx or .xls extension",
        )
    ext = original_filename.rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File extension '.{ext}' not supported. Allowed: csv, xlsx, xls",
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File size exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)}MB limit",
        )

    df = _parse_upload(content, ext)
    if df.shape[0] == 0 or df.shape[1] == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Dataset must contain at least one row and one column",
        )
    if len(df.columns) != len(set(map(str, df.columns))):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Dataset contains duplicate column names",
        )

    dataset_dir = DATASETS_DIR / f"dataset_{uuid.uuid4().hex}"
    dataset_dir.mkdir(parents=True, exist_ok=False)
    original_path = dataset_dir / f"original.{ext}"
    original_path.write_bytes(content)

    try:
        dataset = Datasets(
            user_id=current_user.id,
            name=(name.strip() or original_filename.rsplit(".", 1)[0])[:256],
            original_filename=original_filename,
            file_path=str(original_path),
            file_format=ext,
            row_count=int(df.shape[0]),
            column_count=int(df.shape[1]),
            status="uploaded",
            created_at=datetime.now(timezone.utc),
        )
        db.add(dataset)
        db.flush()

        version = DatasetVersions(
            dataset_id=dataset.id,
            version_number=0,
            file_path=str(original_path),
            version_type="original",
            parent_version_id=None,
            created_at=datetime.now(timezone.utc),
        )
        db.add(version)
        db.commit()
        db.refresh(dataset)
    except Exception:
        db.rollback()
        shutil.rmtree(dataset_dir, ignore_errors=True)
        raise

    return _dataset_payload(dataset, version_count=1)


@router.get("/", response_model=list[DatasetInfo])
def list_datasets(
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List datasets owned by the authenticated user."""
    datasets = (
        db.query(Datasets)
        .filter(Datasets.user_id == current_user.id)
        .order_by(Datasets.created_at.desc(), Datasets.id.desc())
        .all()
    )
    result = []
    for dataset in datasets:
        version_count = (
            db.query(DatasetVersions)
            .filter(DatasetVersions.dataset_id == dataset.id)
            .count()
        )
        result.append(_dataset_payload(dataset, version_count))
    return result


@router.get("/{dataset_id}", response_model=DatasetInfo)
def get_dataset(
    dataset_id: int,
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    dataset = _get_owned_dataset(dataset_id, current_user, db)
    version_count = (
        db.query(DatasetVersions).filter(DatasetVersions.dataset_id == dataset.id).count()
    )
    return _dataset_payload(dataset, version_count)


@router.get("/{dataset_id}/preview", response_model=DatasetPreview)
def preview_dataset(
    dataset_id: int,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    version_id: Optional[int] = Query(None),
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    dataset = _get_owned_dataset(dataset_id, current_user, db)
    df, _version = load_dataset_frame(db, dataset, version_id)
    return dataframe_preview(df, offset=offset, limit=limit)


@router.get("/{dataset_id}/versions", response_model=list[DatasetVersionInfo])
def list_dataset_versions(
    dataset_id: int,
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    dataset = _get_owned_dataset(dataset_id, current_user, db)
    return [
        {
            "id": version.id,
            "dataset_id": version.dataset_id,
            "version_number": version.version_number,
            "version_type": version.version_type,
            "parent_version_id": version.parent_version_id,
            "created_at": version.created_at,
        }
        for version in get_versions(db, dataset.id)
    ]


@router.get("/{dataset_id}/download")
def download_dataset(
    dataset_id: int,
    version_id: Optional[int] = Query(None),
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Download the latest (or requested) dataset version."""
    dataset = _get_owned_dataset(dataset_id, current_user, db)
    if version_id is not None:
        version = (
            db.query(DatasetVersions)
            .filter(
                DatasetVersions.id == version_id,
                DatasetVersions.dataset_id == dataset.id,
            )
            .first()
        )
        if version is None:
            raise HTTPException(status_code=404, detail="Dataset version not found")
    else:
        version = get_latest_version(db, dataset)

    path = Path(version.file_path) if version else Path(dataset.file_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Dataset file not found")

    suffix = path.suffix or f".{dataset.file_format}"
    return FileResponse(
        path=str(path),
        filename=f"{safe_filename(dataset.name, 'dataset').rsplit('.', 1)[0]}{suffix}",
        media_type="application/octet-stream",
    )


@router.delete("/{dataset_id}")
def delete_dataset(
    dataset_id: int,
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a dataset and all dependent versions, jobs, experiments and models."""
    dataset = _get_owned_dataset(dataset_id, current_user, db)
    # Capture attributes before the bulk delete expires the ORM instance.
    dataset_file_path = dataset.file_path

    version_ids = [
        row[0]
        for row in db.query(DatasetVersions.id)
        .filter(DatasetVersions.dataset_id == dataset.id)
        .all()
    ]

    experiment_ids = []
    if version_ids:
        experiment_ids = [
            row[0]
            for row in db.query(Experiments.id)
            .filter(Experiments.dataset_version_id.in_(version_ids))
            .all()
        ]

    model_ids = []
    if experiment_ids:
        model_ids = [
            row[0]
            for row in db.query(ModelResults.id)
            .filter(ModelResults.experiment_id.in_(experiment_ids))
            .all()
        ]

    model_paths = []
    if model_ids:
        model_paths = [
            row[0]
            for row in db.query(ModelResults.model_artifact_path)
            .filter(ModelResults.id.in_(model_ids))
            .all()
            if row[0]
        ]
        db.query(Predictions).filter(Predictions.model_result_id.in_(model_ids)).delete(
            synchronize_session=False
        )
        db.query(ModelResults).filter(ModelResults.id.in_(model_ids)).delete(
            synchronize_session=False
        )
    if experiment_ids:
        db.query(Experiments).filter(Experiments.id.in_(experiment_ids)).delete(
            synchronize_session=False
        )

    db.query(CleaningJobs).filter(CleaningJobs.dataset_id == dataset.id).delete(
        synchronize_session=False
    )
    db.query(DatasetVersions).filter(DatasetVersions.dataset_id == dataset.id).delete(
        synchronize_session=False
    )
    db.query(Datasets).filter(Datasets.id == dataset.id).delete(synchronize_session=False)
    db.commit()

    for model_path in model_paths:
        try:
            Path(model_path).unlink(missing_ok=True)
        except OSError:
            pass

    dataset_path = Path(dataset_file_path)
    try:
        if dataset_path.resolve().is_relative_to(DATASETS_DIR):
            shutil.rmtree(dataset_path.parent, ignore_errors=True)
    except (OSError, ValueError):
        pass

    return {"success": True, "message": "Dataset deleted successfully"}
