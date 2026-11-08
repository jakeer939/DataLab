from __future__ import annotations

from typing import Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Datasets, Users
from ..schemas import DatasetProfile, DatasetQuality
from ..security import get_current_user
from ..services.data_io import json_safe, load_dataset_frame
from ..services.profiling_service import DatasetProfiler

router = APIRouter(prefix="/profiling", tags=["Dataset Profiling"])


def _owned_dataset(dataset_id: int, user: Users, db: Session) -> Datasets:
    dataset = (
        db.query(Datasets)
        .filter(Datasets.id == dataset_id, Datasets.user_id == user.id)
        .first()
    )
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return dataset


@router.get("/{dataset_id}", response_model=DatasetProfile)
def get_dataset_profile(
    dataset_id: int,
    version_id: Optional[int] = Query(None),
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return a full statistical profile and chart-ready aggregates."""
    dataset = _owned_dataset(dataset_id, current_user, db)
    df, _version = load_dataset_frame(db, dataset, version_id)
    return DatasetProfiler(df).generate_profile()


@router.get("/{dataset_id}/quality", response_model=DatasetQuality)
def get_dataset_quality(
    dataset_id: int,
    version_id: Optional[int] = Query(None),
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Assess missing values, duplicates, outliers and inconsistent data."""
    dataset = _owned_dataset(dataset_id, current_user, db)
    df, _version = load_dataset_frame(db, dataset, version_id)
    return DatasetProfiler(df).generate_quality()


@router.get("/{dataset_id}/correlation")
def get_correlation_matrix(
    dataset_id: int,
    version_id: Optional[int] = Query(None),
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    dataset = _owned_dataset(dataset_id, current_user, db)
    df, _version = load_dataset_frame(db, dataset, version_id)
    return DatasetProfiler(df).correlation


@router.get("/{dataset_id}/scatter")
def get_scatter_data(
    dataset_id: int,
    x_column: str = Query(...),
    y_column: str = Query(...),
    color_column: Optional[str] = Query(None),
    limit: int = Query(1000, ge=1, le=5000),
    version_id: Optional[int] = Query(None),
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return sampled points for a scatter plot."""
    dataset = _owned_dataset(dataset_id, current_user, db)
    df, _version = load_dataset_frame(db, dataset, version_id)
    for column in (x_column, y_column):
        if column not in df.columns:
            raise HTTPException(status_code=400, detail=f"Column '{column}' does not exist")
    if color_column and color_column not in df.columns:
        raise HTTPException(status_code=400, detail=f"Column '{color_column}' does not exist")

    numeric_x = pd.to_numeric(df[x_column], errors="coerce")
    numeric_y = pd.to_numeric(df[y_column], errors="coerce")
    mask = numeric_x.notna() & numeric_y.notna()
    frame = df.loc[mask]
    if len(frame) > limit:
        frame = frame.sample(n=limit, random_state=42)

    points = []
    for index, row in frame.iterrows():
        point = {
            "x": json_safe(numeric_x.loc[index]),
            "y": json_safe(numeric_y.loc[index]),
        }
        if color_column:
            point["color"] = json_safe(row[color_column])
        points.append(point)
    return {"x_column": x_column, "y_column": y_column, "points": points}
