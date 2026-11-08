"""Dataset profiling, EDA statistics, chart data and quality assessment."""
from __future__ import annotations

import math
import re
from typing import Any, Dict, List

import numpy as np
import pandas as pd

from .data_io import json_safe


_NUMERIC_TEXT = re.compile(r"^-?\d+(\.\d+)?$")


def _to_datetime(series: pd.Series) -> pd.Series:
    """Parse a series to datetimes without pandas' per-element format warning.

    ``format="mixed"`` makes the per-element fallback explicit, which keeps the
    behaviour deterministic and avoids the noisy ``UserWarning`` pandas emits
    when it silently falls back to dateutil.
    """
    try:
        return pd.to_datetime(series, errors="coerce", format="mixed")
    except (ValueError, TypeError, OverflowError):
        return pd.to_datetime(series, errors="coerce")


def _safe_round(value: Any, digits: int = 4) -> Any:
    value = json_safe(value)
    if isinstance(value, float):
        return round(value, digits)
    return value


class DatasetProfiler:
    """Compute a JSON-friendly profile for a pandas DataFrame."""

    def __init__(self, df: pd.DataFrame):
        self.df = df
        self.overview = self._compute_overview()
        self.column_analysis = self._compute_column_analysis()
        self.numerical_stats = self._compute_numerical_stats()
        self.categorical_stats = self._compute_categorical_stats()
        self.correlation = self._compute_correlation()
        self.charts = self._compute_charts()

    # ------------------------------------------------------------------
    # Type detection
    # ------------------------------------------------------------------
    def _detect_column_type(self, column: str) -> str:
        col = self.df[column]
        if pd.api.types.is_bool_dtype(col):
            return "boolean"
        if pd.api.types.is_datetime64_any_dtype(col):
            return "datetime"
        if pd.api.types.is_numeric_dtype(col):
            return "numerical"

        non_null = col.dropna()
        if non_null.empty:
            return "empty"
        if self._looks_datetime(non_null):
            return "datetime"
        return "categorical"

    @staticmethod
    def _looks_datetime(non_null: pd.Series) -> bool:
        sample = non_null.astype(str).head(100).str.strip()
        if sample.empty:
            return False
        # Pure numbers should remain numerical, not epoch timestamps.
        if sample.map(lambda item: bool(_NUMERIC_TEXT.match(item))).all():
            return False
        parsed = _to_datetime(non_null)
        return bool(parsed.notna().mean() >= 0.9)

    # ------------------------------------------------------------------
    # Overview and per-column analysis
    # ------------------------------------------------------------------
    def _compute_overview(self) -> Dict[str, Any]:
        type_counts = {"numerical": 0, "categorical": 0, "datetime": 0, "boolean": 0, "empty": 0}
        for column in self.df.columns:
            col_type = self._detect_column_type(column)
            type_counts[col_type] = type_counts.get(col_type, 0) + 1

        memory_usage = int(self.df.memory_usage(deep=True).sum()) if len(self.df.columns) else 0
        return {
            "number_of_rows": int(len(self.df)),
            "number_of_columns": int(len(self.df.columns)),
            "memory_usage_bytes": memory_usage,
            "memory_usage_mb": round(memory_usage / (1024 * 1024), 4),
            "total_numerical_columns": type_counts["numerical"],
            "total_categorical_columns": type_counts["categorical"],
            "total_datetime_columns": type_counts["datetime"],
            "total_boolean_columns": type_counts["boolean"],
            "total_empty_columns": type_counts["empty"],
            "total_missing_cells": int(self.df.isna().sum().sum()),
            "total_duplicate_rows": int(self.df.duplicated().sum()),
        }

    def _compute_column_analysis(self) -> Dict[str, Dict[str, Any]]:
        analysis: Dict[str, Dict[str, Any]] = {}
        for column in self.df.columns:
            col = self.df[column]
            col_type = self._detect_column_type(column)
            missing_count = int(col.isna().sum())
            denominator = len(col) if len(col) else 1
            unique_count = int(col.nunique(dropna=True))

            base = {
                "column_name": str(column),
                "data_type": col_type,
                "dtype": str(col.dtype),
                "missing_value_count": missing_count,
                "missing_value_percentage": round(missing_count / denominator * 100, 2),
                "unique_value_count": unique_count,
                "duplicate_value_count": int(len(col) - unique_count),
                "is_constant": bool(unique_count <= 1 and len(col) > 0),
                "is_empty": bool(missing_count == len(col)),
            }

            if col_type == "numerical":
                base.update(self._numerical_column_stats(col))
            elif col_type == "categorical":
                base.update(self._categorical_column_stats(col))
            elif col_type == "datetime":
                base.update(self._datetime_column_stats(col))
            elif col_type == "boolean":
                base.update(self._categorical_column_stats(col))
            analysis[str(column)] = base
        return analysis

    @staticmethod
    def _numerical_column_stats(col: pd.Series) -> Dict[str, Any]:
        non_null = col.dropna()
        if non_null.empty:
            return {}
        stats = {
            "mean": _safe_round(non_null.mean()),
            "median": _safe_round(non_null.median()),
            "mode": _safe_round(non_null.mode().iloc[0]) if not non_null.mode().empty else None,
            "standard_deviation": _safe_round(non_null.std()) if len(non_null) > 1 else None,
            "variance": _safe_round(non_null.var()) if len(non_null) > 1 else None,
            "minimum": _safe_round(non_null.min()),
            "maximum": _safe_round(non_null.max()),
            "p25": _safe_round(non_null.quantile(0.25)),
            "p50": _safe_round(non_null.quantile(0.50)),
            "p75": _safe_round(non_null.quantile(0.75)),
            "skewness": _safe_round(non_null.skew()) if len(non_null) > 2 else None,
            "kurtosis": _safe_round(non_null.kurtosis()) if len(non_null) > 3 else None,
        }
        return stats

    @staticmethod
    def _categorical_column_stats(col: pd.Series) -> Dict[str, Any]:
        non_null = col.dropna()
        if non_null.empty:
            return {}
        value_counts = non_null.astype(str).value_counts()
        return {
            "number_of_unique_categories": int(non_null.nunique()),
            "most_frequent_category": str(value_counts.index[0]),
            "category_frequencies": {
                str(key): int(value) for key, value in value_counts.head(50).items()
            },
            "category_distribution": {
                str(key): round(float(value / len(non_null)) * 100, 2)
                for key, value in value_counts.head(50).items()
            },
        }

    @staticmethod
    def _datetime_column_stats(col: pd.Series) -> Dict[str, Any]:
        parsed = _to_datetime(col)
        if parsed.isna().all():
            return {}
        return {
            "earliest": parsed.min().isoformat() if not parsed.empty else None,
            "latest": parsed.max().isoformat() if not parsed.empty else None,
            "unique_dates": int(parsed.nunique()),
        }

    def _compute_numerical_stats(self) -> Dict[str, Dict[str, Any]]:
        return {
            str(column): self._numerical_column_stats(self.df[column])
            for column in self.df.columns
            if self._detect_column_type(column) == "numerical"
        }

    def _compute_categorical_stats(self) -> Dict[str, Dict[str, Any]]:
        return {
            str(column): self._categorical_column_stats(self.df[column])
            for column in self.df.columns
            if self._detect_column_type(column) in {"categorical", "boolean"}
        }

    # ------------------------------------------------------------------
    # Correlations and chart-ready data
    # ------------------------------------------------------------------
    def _numeric_frame(self) -> pd.DataFrame:
        numeric_cols = [
            column
            for column in self.df.columns
            if pd.api.types.is_numeric_dtype(self.df[column])
            and not pd.api.types.is_bool_dtype(self.df[column])
        ]
        return self.df[numeric_cols]

    def _compute_correlation(self) -> Dict[str, Any]:
        numeric = self._numeric_frame()
        if numeric.shape[1] < 2:
            return {"columns": [], "matrix": []}
        corr = numeric.corr(numeric_only=True)
        columns = [str(column) for column in corr.columns]
        matrix = [
            [_safe_round(corr.iloc[row, col], 4) for col in range(len(columns))]
            for row in range(len(columns))
        ]
        return {"columns": columns, "matrix": matrix}

    def _compute_charts(self) -> Dict[str, Any]:
        histograms: Dict[str, Any] = {}
        boxplots: Dict[str, Any] = {}
        bar_charts: Dict[str, Any] = {}

        for column in self.df.columns:
            col_type = self._detect_column_type(column)
            series = self.df[column]

            if col_type == "numerical":
                non_null = series.dropna()
                if non_null.empty:
                    continue
                bin_count = min(20, max(5, int(math.sqrt(max(len(non_null), 1)))))
                counts, edges = np.histogram(non_null.astype(float), bins=bin_count)
                histograms[str(column)] = {
                    "bins": [_safe_round(edge) for edge in edges.tolist()],
                    "counts": [int(count) for count in counts.tolist()],
                }
                q1 = float(non_null.quantile(0.25))
                median = float(non_null.median())
                q3 = float(non_null.quantile(0.75))
                iqr = q3 - q1
                lower = q1 - 1.5 * iqr
                upper = q3 + 1.5 * iqr
                outliers = non_null[(non_null < lower) | (non_null > upper)]
                boxplots[str(column)] = {
                    "min": _safe_round(non_null.min()),
                    "q1": _safe_round(q1),
                    "median": _safe_round(median),
                    "q3": _safe_round(q3),
                    "max": _safe_round(non_null.max()),
                    "lower_fence": _safe_round(lower),
                    "upper_fence": _safe_round(upper),
                    "outliers": [_safe_round(value) for value in outliers.head(100).tolist()],
                }
            elif col_type in {"categorical", "boolean"}:
                non_null = series.dropna()
                if non_null.empty:
                    continue
                counts = non_null.astype(str).value_counts().head(10)
                bar_charts[str(column)] = {
                    "categories": [str(key) for key in counts.index.tolist()],
                    "counts": [int(value) for value in counts.tolist()],
                }

        return {
            "histograms": histograms,
            "boxplots": boxplots,
            "bar_charts": bar_charts,
        }

    # ------------------------------------------------------------------
    # Public payloads
    # ------------------------------------------------------------------
    def generate_profile(self) -> Dict[str, Any]:
        return {
            "overview": self.overview,
            "column_analysis": self.column_analysis,
            "numerical_statistics": self.numerical_stats,
            "categorical_statistics": self.categorical_stats,
            "correlation": self.correlation,
            "charts": self.charts,
        }

    def generate_quality(self) -> Dict[str, Any]:
        total_rows = len(self.df)
        denominator = total_rows if total_rows else 1

        missing_values = {
            str(column): {
                "count": int(self.df[column].isna().sum()),
                "percentage": round(float(self.df[column].isna().sum()) / denominator * 100, 2),
                "is_excessive": bool(
                    float(self.df[column].isna().sum()) / denominator * 100 > 50
                ),
            }
            for column in self.df.columns
        }

        duplicates = int(self.df.duplicated().sum())
        duplicate_columns = [
            str(column)
            for column in self.df.columns
            if int(self.df[column].duplicated().sum()) > 0
        ]

        outliers: Dict[str, Any] = {}
        for column in self.df.columns:
            if not pd.api.types.is_numeric_dtype(self.df[column]):
                continue
            if pd.api.types.is_bool_dtype(self.df[column]):
                continue
            non_null = self.df[column].dropna()
            if len(non_null) < 4:
                continue
            q1 = non_null.quantile(0.25)
            q3 = non_null.quantile(0.75)
            iqr = q3 - q1
            if iqr == 0:
                continue
            lower = q1 - 1.5 * iqr
            upper = q3 + 1.5 * iqr
            mask = (non_null < lower) | (non_null > upper)
            count = int(mask.sum())
            if count:
                outliers[str(column)] = {
                    "count": count,
                    "percentage": round(count / denominator * 100, 2),
                    "method": "IQR",
                    "lower_bound": _safe_round(lower),
                    "upper_bound": _safe_round(upper),
                }

        whitespace_issues = []
        mixed_types = []
        invalid_numerical = []
        invalid_dates = []
        empty_columns = []
        constant_columns = []

        for column in self.df.columns:
            series = self.df[column]
            non_null = series.dropna()
            if non_null.empty:
                empty_columns.append(str(column))
                continue
            if non_null.nunique() <= 1:
                constant_columns.append(str(column))

            if pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series):
                as_text = non_null.astype(str)
                if as_text.str.strip().ne(as_text).any():
                    whitespace_issues.append(str(column))
                if non_null.map(type).nunique() > 1:
                    mixed_types.append(str(column))

                numeric_ratio = pd.to_numeric(non_null, errors="coerce").notna().mean()
                if 0 < numeric_ratio < 1:
                    invalid_numerical.append(str(column))

                if not as_text.map(lambda item: bool(_NUMERIC_TEXT.match(item.strip()))).all():
                    date_ratio = _to_datetime(non_null).notna().mean()
                    if 0 < date_ratio < 1:
                        invalid_dates.append(str(column))

        return {
            "missing_values": missing_values,
            "duplicate_records": {
                "total_duplicates": duplicates,
                "percentage": round(duplicates / denominator * 100, 2),
                "contributing_columns": duplicate_columns,
            },
            "outliers": outliers,
            "inconsistent_data": {
                "whitespace_issues": bool(whitespace_issues),
                "whitespace_columns": whitespace_issues,
                "mixed_types": bool(mixed_types),
                "mixed_type_columns": mixed_types,
                "invalid_numerical": bool(invalid_numerical),
                "invalid_numerical_columns": invalid_numerical,
                "invalid_dates": bool(invalid_dates),
                "invalid_date_columns": invalid_dates,
                "empty_columns": empty_columns,
                "constant_columns": constant_columns,
            },
        }
