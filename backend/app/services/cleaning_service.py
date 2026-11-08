"""Configurable, deterministic data-cleaning operations."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler, OneHotEncoder, OrdinalEncoder, RobustScaler, StandardScaler


class DataCleaningService:
    """Apply cleaning operations to a DataFrame while keeping an audit trail.

    The service always copies the input frame; the caller's original data is
    never mutated.
    """

    def __init__(self, df: pd.DataFrame):
        self.original_df = df.copy(deep=True)
        self.cleaned_df = df.copy(deep=True)
        self.cleaning_history: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _record(
        self,
        operation: str,
        columns: List[str],
        configuration: Dict[str, Any],
        affected_records: int,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        entry = {
            "operation": operation,
            "affected_columns": [str(column) for column in columns],
            "configuration": configuration,
            "affected_records": int(affected_records),
            "timestamp": pd.Timestamp.now().isoformat(),
            "resulting_version": len(self.cleaning_history) + 1,
        }
        if details:
            entry.update(details)
        self.cleaning_history.append(entry)

    def _numeric_columns(self) -> List[str]:
        return [
            str(column)
            for column in self.cleaned_df.columns
            if pd.api.types.is_numeric_dtype(self.cleaned_df[column])
            and not pd.api.types.is_bool_dtype(self.cleaned_df[column])
        ]

    def _categorical_columns(self) -> List[str]:
        return [
            str(column)
            for column in self.cleaned_df.columns
            if pd.api.types.is_object_dtype(self.cleaned_df[column])
            or isinstance(self.cleaned_df[column].dtype, pd.CategoricalDtype)
            or pd.api.types.is_bool_dtype(self.cleaned_df[column])
        ]

    def _validate_columns(self, columns: List[str]) -> tuple[List[str], List[str]]:
        valid = [column for column in columns if column in self.cleaned_df.columns]
        missing = [column for column in columns if column not in self.cleaned_df.columns]
        return valid, missing

    # ------------------------------------------------------------------
    # Missing values
    # ------------------------------------------------------------------
    def handle_missing_values(
        self,
        method: str,
        columns: Optional[List[str]] = None,
        fill_value: Optional[Any] = None,
    ) -> Dict[str, Any]:
        method = (method or "").lower()
        columns = list(columns or [])
        if method not in {"mean", "median", "mode", "constant", "drop"}:
            raise ValueError(f"Unsupported missing-value method: {method}")

        rows_before = len(self.cleaned_df)

        if method == "drop":
            target = columns or [
                str(column) for column in self.cleaned_df.columns
                if self.cleaned_df[column].isna().any()
            ]
            valid, missing = self._validate_columns(target)
            self.cleaned_df = self.cleaned_df.dropna(subset=valid) if valid else self.cleaned_df
            removed = rows_before - len(self.cleaned_df)
            self._record(
                "drop_missing_rows",
                valid,
                {"method": "drop", "requested_columns": columns},
                removed,
                {"missing_columns": missing},
            )
            return {
                "operation": "drop_missing_rows",
                "affected_columns": valid,
                "missing_columns": missing,
                "records_removed": removed,
                "remaining_rows": len(self.cleaned_df),
            }

        if method in {"mean", "median"}:
            target = columns or self._numeric_columns()
            valid, missing = self._validate_columns(target)
            applicable = [
                column for column in valid
                if pd.api.types.is_numeric_dtype(self.cleaned_df[column])
            ]
            skipped = [column for column in valid if column not in applicable]
        else:
            target = columns or [
                str(column) for column in self.cleaned_df.columns
                if self.cleaned_df[column].isna().any()
            ]
            valid, missing = self._validate_columns(target)
            applicable = valid
            skipped = []

        affected: List[str] = []
        affected_cells = 0
        for column in applicable:
            series = self.cleaned_df[column]
            null_count = int(series.isna().sum())
            if null_count == 0:
                continue

            if method == "mean":
                fill = series.mean()
            elif method == "median":
                fill = series.median()
            elif method == "mode":
                modes = series.mode(dropna=True)
                fill = modes.iloc[0] if not modes.empty else (
                    fill_value if fill_value is not None else "Missing"
                )
            else:  # constant
                if fill_value is not None:
                    fill = fill_value
                else:
                    fill = 0 if pd.api.types.is_numeric_dtype(series) else "Missing"

            if pd.isna(fill):
                # An all-null column has no mean/median; fall back safely.
                fill = fill_value if fill_value is not None else (
                    0 if pd.api.types.is_numeric_dtype(series) else "Missing"
                )

            self.cleaned_df[column] = series.fillna(fill)
            affected.append(column)
            affected_cells += null_count

        self._record(
            f"{method}_imputation",
            affected,
            {"method": method, "fill_value": fill_value, "requested_columns": columns},
            affected_cells,
            {"skipped_columns": skipped, "missing_columns": missing},
        )
        return {
            "operation": f"{method}_imputation",
            "affected_columns": affected,
            "skipped_columns": skipped,
            "missing_columns": missing,
            "records_affected": affected_cells,
            "remaining_rows": len(self.cleaned_df),
        }

    # ------------------------------------------------------------------
    # Duplicates
    # ------------------------------------------------------------------
    def remove_duplicates(self, strategy: str = "remove_all") -> Dict[str, Any]:
        strategy = (strategy or "remove_all").lower()
        keep_map = {"remove_all": False, "keep_first": "first", "keep_last": "last"}
        if strategy not in keep_map:
            raise ValueError(f"Unsupported duplicate strategy: {strategy}")

        rows_before = len(self.cleaned_df)
        self.cleaned_df = self.cleaned_df.drop_duplicates(keep=keep_map[strategy])
        removed = rows_before - len(self.cleaned_df)

        self._record(
            "remove_duplicates",
            [str(column) for column in self.cleaned_df.columns],
            {"strategy": strategy},
            removed,
        )
        return {
            "operation": "remove_duplicates",
            "strategy": strategy,
            "records_removed": removed,
            "remaining_rows": len(self.cleaned_df),
        }

    # ------------------------------------------------------------------
    # Outliers
    # ------------------------------------------------------------------
    def handle_outliers(
        self,
        method: str,
        columns: Optional[List[str]] = None,
        operation: str = "detect",
        iqr_factor: float = 1.5,
        z_threshold: float = 3.0,
    ) -> Dict[str, Any]:
        method = (method or "iqr").lower()
        operation = (operation or "detect").lower()
        if method not in {"iqr", "z_score"}:
            raise ValueError(f"Unsupported outlier method: {method}")
        if operation not in {"detect", "remove", "cap"}:
            raise ValueError(f"Unsupported outlier operation: {operation}")

        columns = list(columns or []) or self._numeric_columns()
        valid, missing = self._validate_columns(columns)
        numeric = [
            column for column in valid
            if pd.api.types.is_numeric_dtype(self.cleaned_df[column])
        ]

        detected: List[Dict[str, Any]] = []
        remove_mask = pd.Series(False, index=self.cleaned_df.index)
        rows_before = len(self.cleaned_df)
        capped_cells = 0

        for column in numeric:
            series = self.cleaned_df[column]
            non_null = series.dropna()
            if len(non_null) < (4 if method == "iqr" else 3):
                continue

            if method == "iqr":
                q1 = non_null.quantile(0.25)
                q3 = non_null.quantile(0.75)
                iqr = q3 - q1
                if iqr == 0:
                    continue
                lower = q1 - float(iqr_factor) * iqr
                upper = q3 + float(iqr_factor) * iqr
                mask = (series < lower) | (series > upper)
            else:
                mean = non_null.mean()
                std = non_null.std()
                if not std or std == 0 or pd.isna(std):
                    continue
                z_scores = ((series - mean) / std).abs()
                lower = mean - float(z_threshold) * std
                upper = mean + float(z_threshold) * std
                mask = z_scores > float(z_threshold)

            count = int(mask.fillna(False).sum())
            if count == 0:
                continue

            detected.append(
                {
                    "column": column,
                    "method": "IQR" if method == "iqr" else "Z-score",
                    "lower_bound": round(float(lower), 6),
                    "upper_bound": round(float(upper), 6),
                    "count": count,
                    "percentage": round(count / len(self.cleaned_df) * 100, 2),
                }
            )

            if operation == "remove":
                remove_mask = remove_mask | mask.fillna(False)
            elif operation == "cap":
                clipped = series.clip(lower=lower, upper=upper)
                capped_cells += int((clipped != series).fillna(False).sum())
                self.cleaned_df[column] = clipped

        records_affected = 0
        if operation == "remove" and remove_mask.any():
            self.cleaned_df = self.cleaned_df.loc[~remove_mask]
            records_affected = rows_before - len(self.cleaned_df)
        elif operation == "cap":
            records_affected = capped_cells

        self._record(
            f"outlier_{method}_{operation}",
            numeric,
            {
                "method": method,
                "operation": operation,
                "iqr_factor": iqr_factor,
                "z_threshold": z_threshold,
            },
            records_affected,
            {"detected_outliers": detected, "missing_columns": missing},
        )
        return {
            "operation": f"outlier_{method}_{operation}",
            "detected_outliers": detected,
            "affected_columns": numeric,
            "missing_columns": missing,
            "records_affected": records_affected,
            "remaining_rows": len(self.cleaned_df),
        }

    # ------------------------------------------------------------------
    # Encoding
    # ------------------------------------------------------------------
    def encode_features(
        self, method: str, columns: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        method = (method or "one_hot").lower()
        if method not in {"one_hot", "ordinal"}:
            raise ValueError(f"Unsupported encoding method: {method}")

        columns = list(columns or []) or self._categorical_columns()
        valid, missing = self._validate_columns(columns)
        if not valid:
            return {
                "operation": f"encoding_{method}",
                "affected_columns": [],
                "new_columns": [],
                "missing_columns": missing,
                "remaining_rows": len(self.cleaned_df),
            }

        if method == "one_hot":
            encoder = OneHotEncoder(
                sparse_output=False, drop="first", handle_unknown="ignore"
            )
            encoded = encoder.fit_transform(self.cleaned_df[valid].astype(object).fillna("Missing"))
            names = [str(name) for name in encoder.get_feature_names_out(valid)]
            encoded_df = pd.DataFrame(encoded, columns=names, index=self.cleaned_df.index)
            self.cleaned_df = self.cleaned_df.drop(columns=valid)
            self.cleaned_df = pd.concat([self.cleaned_df, encoded_df], axis=1)
            new_columns = names
        else:
            encoder = OrdinalEncoder(
                handle_unknown="use_encoded_value", unknown_value=-1
            )
            self.cleaned_df[valid] = encoder.fit_transform(
                self.cleaned_df[valid].astype(object).fillna("Missing")
            )
            new_columns = []

        self._record(
            f"encoding_{method}",
            valid,
            {"method": method},
            len(self.cleaned_df),
            {"new_columns": new_columns, "missing_columns": missing},
        )
        return {
            "operation": f"encoding_{method}",
            "affected_columns": valid,
            "new_columns": new_columns,
            "missing_columns": missing,
            "remaining_rows": len(self.cleaned_df),
        }

    # ------------------------------------------------------------------
    # Scaling
    # ------------------------------------------------------------------
    def scale_features(
        self, method: str, columns: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        method = (method or "standard").lower()
        scaler_map = {
            "standard": StandardScaler,
            "minmax": MinMaxScaler,
            "robust": RobustScaler,
        }
        if method not in scaler_map:
            raise ValueError(f"Unsupported scaling method: {method}")

        columns = list(columns or []) or self._numeric_columns()
        valid, missing = self._validate_columns(columns)
        numeric = [
            column for column in valid
            if pd.api.types.is_numeric_dtype(self.cleaned_df[column])
        ]

        for column in numeric:
            series = self.cleaned_df[column]
            mask = series.notna()
            if not mask.any():
                continue
            scaler = scaler_map[method]()
            values = series.loc[mask].astype(float).to_numpy().reshape(-1, 1)
            # Cast the whole column to float first; assigning floats into an
            # int64 column through .loc is deprecated in pandas 2.x.
            scaled_series = series.astype(float)
            scaled_series.loc[mask] = scaler.fit_transform(values).ravel()
            self.cleaned_df[column] = scaled_series

        self._record(
            f"scaling_{method}",
            numeric,
            {"method": method},
            len(self.cleaned_df),
            {"missing_columns": missing},
        )
        return {
            "operation": f"scaling_{method}",
            "affected_columns": numeric,
            "missing_columns": missing,
            "remaining_rows": len(self.cleaned_df),
        }

    # ------------------------------------------------------------------
    # Type conversion
    # ------------------------------------------------------------------
    def convert_data_type(
        self, columns: Optional[List[str]], target_type: str
    ) -> Dict[str, Any]:
        target_type = (target_type or "").lower()
        if target_type not in {"integer", "float", "string", "categorical", "datetime"}:
            raise ValueError(f"Unsupported target type: {target_type}")

        valid, missing = self._validate_columns(list(columns or []))
        converted: List[str] = []
        failed: List[str] = []

        for column in valid:
            try:
                if target_type == "integer":
                    numeric = pd.to_numeric(self.cleaned_df[column], errors="coerce")
                    if numeric.isna().any():
                        self.cleaned_df[column] = numeric.astype("Int64")
                    else:
                        self.cleaned_df[column] = numeric.astype(int)
                elif target_type == "float":
                    self.cleaned_df[column] = pd.to_numeric(
                        self.cleaned_df[column], errors="coerce"
                    ).astype(float)
                elif target_type == "string":
                    self.cleaned_df[column] = self.cleaned_df[column].astype(str)
                elif target_type == "categorical":
                    self.cleaned_df[column] = self.cleaned_df[column].astype("category")
                else:
                    self.cleaned_df[column] = pd.to_datetime(
                        self.cleaned_df[column], errors="coerce"
                    )
                converted.append(column)
            except (ValueError, TypeError, OverflowError):
                failed.append(column)

        self._record(
            "data_type_conversion",
            converted,
            {"target_type": target_type},
            len(self.cleaned_df),
            {"failed_columns": failed, "missing_columns": missing},
        )
        return {
            "operation": "data_type_conversion",
            "affected_columns": converted,
            "failed_columns": failed,
            "missing_columns": missing,
            "target_type": target_type,
            "remaining_rows": len(self.cleaned_df),
        }

    # ------------------------------------------------------------------
    # Public accessors
    # ------------------------------------------------------------------
    def get_cleaned_data(self) -> pd.DataFrame:
        return self.cleaned_df

    def get_cleaning_history(self) -> List[Dict[str, Any]]:
        return self.cleaning_history
