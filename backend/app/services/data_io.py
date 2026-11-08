"""Shared dataset I/O helpers used by profiling, cleaning and ML routers."""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from ..models import Datasets, DatasetVersions


def read_dataframe(file_path: str | Path, file_format: str) -> pd.DataFrame:
    """Read a CSV/Excel dataset with helpful, non-leaking error messages."""
    path = Path(file_path)
    if not path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset file is missing from storage",
        )

    fmt = (file_format or "").lower().lstrip(".")
    try:
        if fmt == "csv":
            try:
                return pd.read_csv(path, encoding="utf-8-sig")
            except UnicodeDecodeError:
                return pd.read_csv(path, encoding="latin-1")
        if fmt in {"xlsx", "xls"}:
            return pd.read_excel(path)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unable to read dataset: {exc}",
        )
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Unsupported file format: {file_format}",
    )


def get_versions(db: Session, dataset_id: int) -> list[DatasetVersions]:
    return (
        db.query(DatasetVersions)
        .filter(DatasetVersions.dataset_id == dataset_id)
        .order_by(DatasetVersions.version_number.asc())
        .all()
    )


def get_latest_version(db: Session, dataset: Datasets) -> Optional[DatasetVersions]:
    return (
        db.query(DatasetVersions)
        .filter(DatasetVersions.dataset_id == dataset.id)
        .order_by(DatasetVersions.version_number.desc())
        .first()
    )


def load_dataset_frame(
    db: Session,
    dataset: Datasets,
    version_id: Optional[int] = None,
) -> tuple[pd.DataFrame, DatasetVersions | None]:
    """Load the requested version, the latest version, or the raw upload."""
    version = None
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
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Dataset version not found",
            )
    else:
        version = get_latest_version(db, dataset)

    path = version.file_path if version else dataset.file_path
    fmt = dataset.file_format
    if path and str(path).lower().endswith((".xlsx", ".xls")):
        fmt = Path(path).suffix.lstrip(".")
    elif path:
        fmt = Path(path).suffix.lstrip(".") or fmt
    return read_dataframe(path, fmt), version


def json_safe(value: Any) -> Any:
    """Convert numpy/pandas scalars into JSON-serialisable Python objects."""
    if value is None:
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        value = float(value)
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if isinstance(value, (np.ndarray,)):
        return [json_safe(item) for item in value.tolist()]
    if isinstance(value, (pd.Series,)):
        return [json_safe(item) for item in value.tolist()]
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    if pd.isna(value):
        return None
    return value


def dataframe_preview(
    df: pd.DataFrame, offset: int = 0, limit: int = 50
) -> dict[str, Any]:
    offset = max(0, int(offset))
    limit = min(max(1, int(limit)), 500)
    window = df.iloc[offset : offset + limit]
    return {
        "columns": [str(col) for col in df.columns],
        "data_types": {str(col): str(dtype) for col, dtype in df.dtypes.items()},
        "first_rows": [
            [json_safe(cell) for cell in row]
            for row in window.itertuples(index=False, name=None)
        ],
        "row_count": int(len(df)),
        "column_count": int(len(df.columns)),
        "offset": offset,
        "limit": limit,
    }


def safe_filename(filename: Optional[str], fallback: str = "dataset.csv") -> str:
    """Strip directories and unsafe characters from a client-supplied name."""
    name = Path(filename or fallback).name
    name = name.replace("\\", "_").replace("/", "_")
    cleaned = "".join(ch for ch in name if ch.isalnum() or ch in "._- ").strip()
    cleaned = cleaned or fallback
    return cleaned[:200]
