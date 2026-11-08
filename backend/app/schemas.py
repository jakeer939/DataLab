from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


# ============================================================
# Authentication
# ============================================================

class UserRegister(BaseModel):
    username: str = Field(..., min_length=3, max_length=128)
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=256)

    @field_validator("username")
    @classmethod
    def username_is_clean(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Username cannot be blank")
        if any(ch.isspace() for ch in value):
            raise ValueError("Username cannot contain whitespace")
        return value


class UserLogin(BaseModel):
    username: str = Field(..., min_length=1, max_length=256)
    password: str = Field(..., min_length=1, max_length=256)


class UserMe(BaseModel):
    id: int
    username: str
    email: str
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: Optional[UserMe] = None


class UserProfile(BaseModel):
    id: int
    username: str
    email: str
    created_at: datetime
    total_datasets: int = 0
    total_cleaning_operations: int = 0
    total_ml_experiments: int = 0
    total_trained_models: int = 0


# ============================================================
# Datasets
# ============================================================

class DatasetInfo(BaseModel):
    id: int
    name: str
    original_filename: str
    file_format: str
    row_count: int
    column_count: int
    status: str
    created_at: datetime
    version_count: int = 0


class DatasetVersionInfo(BaseModel):
    id: int
    dataset_id: int
    version_number: int
    version_type: str
    parent_version_id: Optional[int] = None
    created_at: datetime


class DatasetPreview(BaseModel):
    columns: List[str]
    data_types: Dict[str, str]
    first_rows: List[List[Any]]
    row_count: int
    column_count: int
    offset: int = 0
    limit: int = 50


class DatasetProfile(BaseModel):
    overview: Dict[str, Any]
    column_analysis: Dict[str, Dict[str, Any]]
    numerical_statistics: Dict[str, Dict[str, Any]]
    categorical_statistics: Dict[str, Dict[str, Any]]
    correlation: Dict[str, Any] = {}
    charts: Dict[str, Any] = {}


class DatasetQuality(BaseModel):
    missing_values: Dict[str, Dict[str, Any]]
    duplicate_records: Dict[str, Any]
    outliers: Dict[str, Dict[str, Any]]
    inconsistent_data: Dict[str, Any]


# ============================================================
# Data cleaning
# ============================================================

class CleaningOperation(BaseModel):
    operation: str
    affected_columns: List[str] = []
    configuration: Dict[str, Any] = {}


class CleaningRequest(BaseModel):
    operations: List[CleaningOperation] = Field(..., min_length=1)


class CleaningResult(BaseModel):
    version_id: int
    version_number: int
    operations: List[Dict[str, Any]]
    remaining_rows: int
    remaining_columns: int
    final_columns: List[str]


# ============================================================
# Machine learning
# ============================================================

class ExperimentConfig(BaseModel):
    dataset_id: int
    target_column: str
    problem_type: str = "auto"
    selected_features: List[str] = []
    split_configuration: Dict[str, Any] = Field(
        default_factory=lambda: {"test_size": 0.2, "random_seed": 42}
    )
    algorithms: List[str] = Field(default_factory=list)

    @field_validator("problem_type")
    @classmethod
    def valid_problem_type(cls, value: str) -> str:
        if value not in {"auto", "classification", "regression"}:
            raise ValueError("problem_type must be auto, classification or regression")
        return value


class ExperimentResultItem(BaseModel):
    model_id: Optional[int] = None
    algorithm: str
    status: str
    metrics: Dict[str, Any] = {}
    training_duration: Optional[float] = None
    error: Optional[str] = None


class ExperimentResponse(BaseModel):
    experiment_id: int
    problem_type: str
    target_column: str
    selected_features: List[str]
    split_configuration: Dict[str, Any]
    dataset_version_id: int
    results: List[ExperimentResultItem]
    recommended_model_id: Optional[int] = None
    preprocessing_config: Dict[str, Any] = {}


class ModelSummary(BaseModel):
    id: int
    algorithm_name: str
    algorithm_label: Optional[str] = None
    experiment_id: int
    target_column: str
    problem_type: str
    dataset_id: int
    dataset_name: str
    metrics: Dict[str, Any]
    training_duration: Optional[float] = None
    status: str
    created_at: datetime


class ModelDetail(ModelSummary):
    feature_schema: List[Dict[str, Any]] = []
    hyperparameters: Dict[str, Any] = {}
    artifact_available: bool = False


class PredictionRequest(BaseModel):
    data: Dict[str, Any]


class PredictionResponse(BaseModel):
    model_id: int
    prediction: Any
    probability: Optional[Dict[str, Any]] = None


class BatchPredictionResponse(BaseModel):
    model_id: int
    row_count: int
    predictions: List[Any]


# ============================================================
# Generic responses
# ============================================================

class APIResponse(BaseModel):
    success: bool
    message: str
    data: Optional[Any] = None


class ErrorResponse(BaseModel):
    success: bool = False
    error: str
    detail: Optional[str] = None
    status_code: int
