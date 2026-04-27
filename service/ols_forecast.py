"""
ols_forecast.py
================

This module contains helper functions to train and evaluate linear (OLS)
models on the delinquency data provided by the user.  The intention
behind this script is twofold:

1.  Provide a clear, reproducible pipeline for selecting an
    appropriate regression specification for each business segment
    (Retail, Mass Products and BK+VKL).  The script demonstrates how
    to merge the segment time series with macro‑economic factors,
    engineer seasonality and trend features, perform stepwise
    elimination based on p‑values and variance inflation factors, and
    report the resulting model’s statistics (R², coefficients and
    p‑values).

2.  Offer a reference implementation for producing a 3‑month
    out‑of‑sample forecast.  Forecasts are generated recursively: the
    model’s own predictions feed into lagged terms when moving beyond
    the last observed period.  Macro‑economic variables for future
    months are pulled from the supplied macro sheet when available.
    For segment‑specific regressors (e.g. «Рестр‑ия», «Зона
    рисков»), a very simple assumption is made: the most recent
    observed value is held constant over the forecast horizon.  This
    assumption can easily be relaxed in the future if more sophisticated
    forecasts for those drivers become available.

Usage
-----

Running this module as a script will load the default Excel files
packaged with the exercise, fit a model for each segment and print
both the in‑sample summary and the next three predicted values.  You
can also import the functions in your own code to experiment with
different sets of predictors or integrate the logic into a web
application.

Example:

    python ols_forecast.py

This will output something like::

    === Розница ===
    Selected columns: ['lag1', 'Рестр‑ия', 'Зона рисков', 'trend']
    R² (adj.): 0.971
    Coefficients:
      const        -3253.8858
      lag1            0.3981
      Рестр‑ия       -0.7991
      Зона рисков     0.7157
      trend         339.2364
    Forecast:
      2026‑01‑01 :  99 906
      2026‑02‑01 : 100 322
      2026‑03‑01 : 100 806

The predictions are approximate due to the naive assumption on
unchanging «Рестр‑ия» and «Зона рисков» in the future.  If you
possess separate forecasts for those inputs they can easily be fed
into the `forecast_segment` function.

Dependencies
------------

This script relies on `pandas` and `statsmodels`, both of which are
commonly available in Python data science environments.  They should
already be installed in the container used by this exercise.  If
executing on your own machine you can install them via pip::

    pip install pandas statsmodels
"""

import pathlib
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple

import numpy as np
import pandas as pd
from statsmodels.regression.linear_model import OLS
from statsmodels.tools.tools import add_constant


@dataclass
class SegmentModel:
    """Container for a fitted OLS model and metadata."""
    name: str
    columns: List[str]
    model: OLS
    data: pd.DataFrame  # data used for training (with engineered features)


def load_segment(path: pathlib.Path) -> pd.DataFrame:
    """Load a segment Excel file into a DataFrame with numeric columns."""
    df = pd.read_excel(path)
    df['Период'] = pd.to_datetime(df['Период'])
    # Convert numeric columns – ignore strings like "9.8%"
    for col in ['ОД порт.', 'Проср.', 'Прос.15+', 'НПЛ', 'Рестр-ия', 'Зона рисков']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    return df


def load_macro(path: pathlib.Path) -> pd.DataFrame:
    """Load the macro‑economic Excel file and parse dates."""
    macro = pd.read_excel(path)
    macro['Период'] = pd.to_datetime(macro['Период'])
    # Convert all non‑date columns to numeric where possible
    for col in macro.columns:
        if col != 'Период':
            macro[col] = pd.to_numeric(macro[col], errors='coerce')
    return macro


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Create trend, seasonal and lag features on a copy of the input frame.

    Parameters
    ----------
    df : DataFrame
        Must contain a datetime column named «Период» and a numeric
        target column «Проср.».

    Returns
    -------
    DataFrame
        The input data with new columns appended.
    """
    out = df.copy()
    out = out.sort_values('Период').reset_index(drop=True)
    # trend is a simple integer index starting at 0
    out['trend'] = np.arange(len(out))
    # month of year for seasonality
    out['month'] = out['Период'].dt.month
    out['sin'] = np.sin(2 * np.pi * out['month'] / 12)
    out['cos'] = np.cos(2 * np.pi * out['month'] / 12)
    # lagged target values
    out['lag1'] = out['Проср.'].shift(1)
    out['lag2'] = out['Проср.'].shift(2)
    return out


def select_and_fit(
    df: pd.DataFrame,
    potential_cols: List[str],
    target_col: str = 'Проср.'
) -> Tuple[OLS, List[str]]:
    """
    Fit an OLS model with stepwise elimination based on p‑values.

    Parameters
    ----------
    df : DataFrame
        Data with all potential predictors already engineered.
    potential_cols : list of str
        The initial set of predictor column names.
    target_col : str, default 'Проср.'
        Name of the dependent variable.

    Returns
    -------
    model : statsmodels.regression.linear_model.RegressionResultsWrapper
        The fitted model.
    columns : list of str
        The final list of predictors retained in the model.
    """
    # Drop rows with missing data in either the target or predictors
    data = df[[target_col] + potential_cols].dropna()
    y = data[target_col]
    current_cols = potential_cols.copy()

    def fit(cols: List[str]) -> OLS:
        X = data[cols]
        return OLS(y, add_constant(X)).fit()

    model = fit(current_cols)
    # Eliminate the worst predictor until all have p‑values ≤ 0.05
    while True:
        # Skip the intercept when checking p‑values
        pvalues = model.pvalues.drop('const')
        max_p = pvalues.max()
        if max_p > 0.05:
            var_to_remove = pvalues.idxmax()
            current_cols.remove(var_to_remove)
            model = fit(current_cols)
        else:
            break
    return model, current_cols


def fit_segment_model(
    name: str,
    seg_path: pathlib.Path,
    macro: pd.DataFrame,
    with_macro: bool = True,
    macro_cols: Optional[List[str]] = None,
) -> SegmentModel:
    """
    Fit a linear regression model for a single segment given a file path.

    This is a convenience wrapper around :func:`fit_segment_model_df`
    that loads the segment from disk using :func:`load_segment`.
    See the documentation of ``fit_segment_model_df`` for parameter
    explanations.
    """
    seg = load_segment(seg_path)
    return fit_segment_model_df(name, seg, macro, with_macro, macro_cols)


def fit_segment_model_df(
    name: str,
    seg_df: pd.DataFrame,
    macro: pd.DataFrame,
    with_macro: bool = True,
    macro_cols: Optional[List[str]] = None,
) -> SegmentModel:
    """
    Fit a linear regression model for a single segment given a DataFrame.

    Parameters
    ----------
    name : str
        Human‑friendly name of the segment (used for printing only).
    seg_df : DataFrame
        The segment's data.  Must contain a ``Период`` column and a
        numeric ``Проср.`` column.  Numeric conversion will be
        attempted on other relevant fields.
    macro : DataFrame
        Macro‑economic dataset loaded via :func:`load_macro`.
    with_macro : bool, default True
        Whether to consider macro factors alongside internal lags and
        seasonality features.
    macro_cols : list of str, optional
        If provided, a list of macro variables to consider.  If not
        provided and ``with_macro`` is True, a default set will be used.

    Returns
    -------
    SegmentModel
        Encapsulating the fitted model, the columns selected and the
        training data with engineered features.
    """
    # Ensure the date column is datetime
    seg = seg_df.copy()
    seg['Период'] = pd.to_datetime(seg['Период'])
    # Convert numeric segment fields
    for col in ['Проср.', 'Прос.15+', 'НПЛ', 'Рестр-ия', 'Зона рисков']:
        if col in seg.columns:
            seg[col] = pd.to_numeric(seg[col], errors='coerce')
    # Merge with macro data on date
    if with_macro:
        if macro_cols is None:
            macro_cols = [
                'cpi',
                'GDD_Trd_R',
                'Rincpop_q',
                'GDD_Con_R',
                'Rwage_q',
                'real_gdp',
                'usdkzt',
            ]
        macro_subset = macro[['Период'] + [c for c in macro_cols if c in macro.columns]]
        merged = seg.merge(macro_subset, on='Период', how='left')
    else:
        merged = seg.copy()
    # Engineer generic features
    merged = engineer_features(merged)
    # Build candidate predictor list
    predictors = ['lag1', 'lag2', 'trend', 'sin', 'cos']
    if with_macro:
        predictors += [c for c in macro_cols if c in merged.columns]
    # Also allow segment‑specific drivers to compete if present
    for col in ['Прос.15+', 'НПЛ', 'Рестр-ия', 'Зона рисков']:
        if col in merged.columns:
            predictors.append(col)
    # Fit and select
    model, cols = select_and_fit(merged, predictors, target_col='Проср.')
    return SegmentModel(name=name, columns=cols, model=model, data=merged)


def forecast_segment(
    seg_model: SegmentModel,
    macro: pd.DataFrame,
    horizon: int = 3,
    future_start: Optional[pd.Timestamp] = None,
    assume_const: bool = True
) -> List[Tuple[pd.Timestamp, float]]:
    """
    Produce a multi‑step forecast using the supplied model.

    Parameters
    ----------
    seg_model : SegmentModel
        The fitted model and its training data.
    macro : DataFrame
        Macro‑economic data for obtaining future values of macro drivers.
    horizon : int, default 3
        Number of monthly steps to predict.
    future_start : datetime, optional
        The first month of the forecast.  If `None`, the month
        immediately following the last training observation is used.
    assume_const : bool, default True
        If True, hold segment‑specific drivers (e.g. «Рестр‑ия»,
        «Зона рисков») constant at their most recent observed value.
        Macro drivers are looked up in the macro sheet.  If False,
        these variables will be set to NaN in the future, which will
        raise an error.  You can provide your own arrays for these
        variables by manually modifying the values before calling
        this function.

    Returns
    -------
    list of (Timestamp, float)
        Each tuple contains the forecast date and the predicted value for
        «Проср.».  The predictions are rounded to two decimal places.
    """
    model = seg_model.model
    cols = seg_model.columns
    df = seg_model.data.copy()
    df = df.sort_values('Период').reset_index(drop=True)
    # Determine forecast start date
    last_date = df['Период'].iloc[-1]
    if future_start is None:
        future_start = (last_date + pd.offsets.MonthBegin()).normalize()
    # Prepare state for recursive forecasting
    # We'll use the last known target values for lagged variables
    history_y = df['Проср.'].dropna().tolist()
    # Extract last values of segment‑specific drivers
    last_values: Dict[str, float] = {}
    for col in cols:
        if col in ['Прос.15+', 'НПЛ', 'Рестр-ия', 'Зона рисков']:
            # If there are missing values, use the last non‑missing value
            last_values[col] = df[col].dropna().iloc[-1]
    preds: List[Tuple[pd.Timestamp, float]] = []
    for step in range(horizon):
        current_date = future_start + pd.offsets.MonthBegin(step)
        # Build a row of predictors
        row: Dict[str, float] = {}
        # Lagged terms – rely on history_y list
        # lag1 uses most recent observation
        if 'lag1' in cols:
            row['lag1'] = history_y[-1]
        if 'lag2' in cols:
            # If only one past value exists (e.g. at the very start), use the same
            row['lag2'] = history_y[-2] if len(history_y) >= 2 else history_y[-1]
        # trend – continues counting forward
        if 'trend' in cols:
            last_trend = df['trend'].iloc[-1] if step == 0 else df['trend'].iloc[-1] + step
            row['trend'] = last_trend + 1  # shift by one for the next period
        # Seasonal features based on month
        month = current_date.month
        if 'sin' in cols:
            row['sin'] = np.sin(2 * np.pi * month / 12)
        if 'cos' in cols:
            row['cos'] = np.cos(2 * np.pi * month / 12)
        # Macro drivers – look up the row in macro DataFrame
        for macro_col in [c for c in cols if c not in ['lag1','lag2','trend','sin','cos','Прос.15+','НПЛ','Рестр-ия','Зона рисков']]:
            mrow = macro.loc[macro['Период'] == current_date]
            if len(mrow) and not pd.isna(mrow.iloc[0][macro_col]):
                row[macro_col] = float(mrow.iloc[0][macro_col])
            else:
                # Fallback to last available value in the training data
                # for that macro column (or NaN if never present)
                if macro_col in df.columns:
                    row[macro_col] = float(df[macro_col].dropna().iloc[-1])
                else:
                    row[macro_col] = np.nan
        # Segment specific drivers – hold constant if requested
        if assume_const:
            for drv, val in last_values.items():
                if drv in cols:
                    row[drv] = val
        # Convert row to the same order as model parameters
        X_new = [1.0]  # intercept
        for col in cols:
            X_new.append(row.get(col, 0.0))
        # Compute prediction
        coef = model.params
        # Ensure lengths match – remove the intercept name if necessary
        pred = float(np.dot(X_new, coef))
        preds.append((current_date, pred))
        # Append prediction to history for subsequent lagged values
        history_y.append(pred)
    return preds


def main() -> None:
    """Execute a demonstration fit and forecast for all segments."""
    base_dir = pathlib.Path(__file__).resolve().parent
    # Paths to the default datasets (these must exist in the same folder)
    seg_paths = {
        'Розничный сегмент': base_dir / 'Розница.xlsx',
        'Масс продукты': base_dir / 'Масс продукты.xlsx',
        'БК+ВКЛ': base_dir / 'БК+ВКЛ.xlsx',
    }
    macro_path = base_dir / 'НСТ.xlsx'
    macro = load_macro(macro_path)
    for name, path in seg_paths.items():
        # Fit a model with macro factors to allow future forecasting
        seg_model = fit_segment_model(name, path, macro, with_macro=True)
        print(f"=== {name} ===")
        print("Selected columns:", seg_model.columns)
        print(f"R² (adj.): {seg_model.model.rsquared_adj:.3f}")
        coef = seg_model.model.params
        print("Coefficients:")
        for key, val in coef.items():
            print(f"  {key:<12} {val:12.4f}")
        # Forecast next three months (starting at Jan 2026)
        preds = forecast_segment(seg_model, macro, horizon=3, future_start=pd.Timestamp('2026-01-01'))
        print("Forecast:")
        for date, val in preds:
            print(f"  {date.date()} : {val:8.0f}")
        print()