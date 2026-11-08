from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from .database import Base

# Portable JSON: JSONB on PostgreSQL, plain JSON on SQLite.
JSONType = JSON().with_variant(JSONB, "postgresql")


# Association table retained for backwards compatibility with the original
# schema. The application authorises access through Datasets.user_id.
user_dataset = Table(
    "user_dataset",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("dataset_id", Integer, ForeignKey("datasets.id", ondelete="CASCADE"), primary_key=True),
)


class Users(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(128), unique=True, nullable=False, index=True)
    email = Column(String(254), unique=True, nullable=False, index=True)
    password_hash = Column(String(512), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True, server_default="1")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Legacy denormalised fields kept for API compatibility.
    datasets = Column(JSONType, default=list, server_default="[]")
    experiments = Column(JSONType, default=list, server_default="[]")
    models = Column(JSONType, default=list, server_default="[]")


class Datasets(Base):
    __tablename__ = "datasets"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(256), nullable=False)
    original_filename = Column(String(256), nullable=False)
    file_path = Column(String(1024), nullable=False)
    file_format = Column(String(10), nullable=False)  # csv, xlsx, xls
    row_count = Column(Integer, nullable=False, default=0)
    column_count = Column(Integer, nullable=False, default=0)
    status = Column(String(50), nullable=False, default="uploaded")  # uploaded, cleaned
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Legacy denormalised fields kept for API compatibility.
    dataset_versions = Column(JSONType, default=list, server_default="[]")
    cleaning_jobs = Column(JSONType, default=list, server_default="[]")
    experiments = Column(JSONType, default=list, server_default="[]")


class DatasetVersions(Base):
    __tablename__ = "dataset_versions"

    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False)
    version_number = Column(Integer, nullable=False)
    file_path = Column(String(1024), nullable=False)
    version_type = Column(String(50), nullable=False)  # original, cleaned
    parent_version_id = Column(Integer, ForeignKey("dataset_versions.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("dataset_id", "version_number", name="uq_dataset_version_number"),
        Index("ix_dataset_versions_dataset_id_version", "dataset_id", "version_number"),
    )


class CleaningJobs(Base):
    __tablename__ = "cleaning_jobs"

    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False)
    dataset_version_id = Column(Integer, ForeignKey("dataset_versions.id", ondelete="SET NULL"), nullable=True)
    configuration = Column(JSONType, nullable=False)
    operation_summary = Column(JSONType, nullable=False)
    status = Column(String(50), nullable=False, default="completed")  # completed, failed
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_cleaning_jobs_dataset_id", "dataset_id"),
        Index("ix_cleaning_jobs_dataset_version_id", "dataset_version_id"),
    )


class Experiments(Base):
    __tablename__ = "experiments"

    id = Column(Integer, primary_key=True, index=True)
    dataset_version_id = Column(
        Integer, ForeignKey("dataset_versions.id", ondelete="CASCADE"), nullable=False
    )
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    target_column = Column(String(256), nullable=False)
    problem_type = Column(String(50), nullable=False)  # classification, regression
    selected_features = Column(JSONType, default=list, server_default="[]")
    split_configuration = Column(JSONType, nullable=False)
    random_seed = Column(Integer, nullable=True)
    status = Column(String(50), nullable=False, default="configured")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    model_results = Column(JSONType, default=list, server_default="[]")


class ModelResults(Base):
    __tablename__ = "model_results"

    id = Column(Integer, primary_key=True, index=True)
    experiment_id = Column(
        Integer, ForeignKey("experiments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    algorithm_name = Column(String(128), nullable=False)
    hyperparameters = Column(JSONType, nullable=False, default=dict)
    evaluation_metrics = Column(JSONType, nullable=False, default=dict)
    training_duration = Column(Float, nullable=True)
    model_artifact_path = Column(String(1024), nullable=True)
    status = Column(String(50), nullable=False, default="pending")  # completed, failed
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Predictions(Base):
    __tablename__ = "predictions"

    id = Column(Integer, primary_key=True, index=True)
    model_result_id = Column(
        Integer, ForeignKey("model_results.id", ondelete="CASCADE"), nullable=False
    )
    input_data = Column(JSONType, nullable=False)
    predicted_output = Column(JSONType, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (Index("ix_predictions_model_result_id", "model_result_id"),)
