"""Descriptive risk-factor aggregation & association module (Nahesson — DA/DS).

Computes daily-grain (ID x date) descriptive associations between lifestyle
risk factors and valid blood pressure measurements without duplicating daily
behaviors across morning/evening sessions.

Methodological safeguards:
- Grain is strictly 1 row per (respondent_id, date) for lifestyle factors.
- Blood pressure uses `bp_policy.assessed_frame` so unpaired, out-of-bounds,
  or pending-review sessions are excluded before computing daily mean SBP/DBP.
- Missing values (especially `sleep_hours` and `smoke_count`) remain NA and
  are never coerced to zero or a synthetic category.
- Small groups (`n < min_group_n` or `respondents < min_respondents`) are
  explicitly flagged so downstream UI/reports do not over-interpret noise.
- Outputs are descriptive associations only (`is_causal=False`,
  `is_diagnosis=False`); repeated observations per respondent are not
  statistically independent.
"""

from __future__ import annotations

import math
from typing import Iterable

import numpy as np
import pandas as pd

from .analytics_v2 import AGE_GROUPS, age_band
from .bp_policy import POLICY_VERSION, assessed_frame

GRAIN_DAILY = 'ID x tanggal'
GRAIN_SESSION = 'ID x tanggal x sesi'

CATEGORY_RISK_FIELDS = (
    'salty_food',
    'fruit',
    'vegetable',
    'caffeine',
    'smoked',
    'medication',
    'sitting',
    'activity_type',
    'occupation',
)

NUMERIC_RISK_FIELDS = (
    'sleep_hours',
    'stress',
    'activity_minutes',
    'smoke_count',
)

ALL_RISK_FIELDS = (
    'sleep_hours',
    'stress',
    'activity_minutes',
    'salty_food',
    'fruit',
    'vegetable',
    'caffeine',
    'smoked',
    'smoke_count',
    'medication',
    'sitting',
    'activity_type',
)

DISCLAIMER_ID = (
    'Ringkasan ini bersifat deskriptif pada grain ID x tanggal. '
    'Hubungan faktor gaya hidup dengan tekanan darah merupakan asosiasi, '
    'bukan bukti sebab-akibat maupun diagnosis medis. Pengamatan berulang '
    'dari responden yang sama saling berkorelasi (tidak independen).'
)


def _clean_float(value, digits: int | None = None) -> float | None:
    """Convert finite scalar to Python float (rounded if requested), else None."""
    if value is None or pd.isna(value):
        return None
    num = float(value)
    if not math.isfinite(num):
        return None
    return round(num, digits) if digits is not None else num


def _normalize_date_col(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize `date` column to YYYY-MM-DD strings when non-empty."""
    out = frame.copy()
    if 'date' in out.columns and len(out):
        out['date'] = pd.to_datetime(out['date']).dt.strftime('%Y-%m-%d')
    return out


def build_daily_bp_panel(
    sessions: pd.DataFrame,
    daily: pd.DataFrame,
    profiles: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Aggregate valid BP sessions to daily grain and left-join onto daily records.

    Parameters
    ----------
    sessions:
        BP session rows (morning/evening readings). Assessed through `bp_policy`.
    daily:
        Daily behavior rows at (respondent_id, date) grain.
    profiles:
        Optional participant profiles used to attach `age` if not already on `daily`.

    Returns
    -------
    (day_panel, assessed_sessions)
        `day_panel` preserves every daily row (including rows with missing BP)
        and attaches `sbp_mean`, `dbp_mean`, `valid_session_count`, and `age_group`.
    """
    daily_df = _normalize_date_col(pd.DataFrame(daily))
    sessions_df = _normalize_date_col(pd.DataFrame(sessions))

    if len(sessions_df):
        assessed = assessed_frame(sessions_df)
    else:
        assessed = sessions_df.assign(
            sbp_mean=pd.Series(dtype=float),
            dbp_mean=pd.Series(dtype=float),
            is_valid=pd.Series(dtype=bool),
            valid_pair_count=pd.Series(dtype='int64'),
            review_status=pd.Series(dtype=object),
            review_reasons=pd.Series(dtype=object),
        )

    if len(daily_df) == 0:
        empty_panel = daily_df.assign(
            sbp_mean=pd.Series(dtype=float),
            dbp_mean=pd.Series(dtype=float),
            valid_session_count=pd.Series(dtype='int64'),
            age_group=pd.Series(dtype=object),
        )
        return empty_panel, assessed

    if profiles is not None and len(profiles):
        prof_df = pd.DataFrame(profiles)
        needed = [c for c in ('age', 'gender', 'occupation') if c in prof_df.columns and c not in daily_df.columns]
        if needed:
            daily_df = daily_df.merge(
                prof_df[['respondent_id', *needed]].drop_duplicates('respondent_id'),
                on='respondent_id',
                how='left',
                validate='many_to_one',
            )
        if len(assessed) and 'age' in prof_df.columns and 'age' not in assessed.columns:
            assessed = assessed.merge(
                prof_df[['respondent_id', 'age']].drop_duplicates('respondent_id'),
                on='respondent_id',
                how='left',
                validate='many_to_one',
            )

    valid = assessed[assessed['is_valid']].copy()
    if len(valid):
        daily_bp = (
            valid.groupby(['respondent_id', 'date'], as_index=False)
            .agg(
                sbp_mean=('sbp_mean', 'mean'),
                dbp_mean=('dbp_mean', 'mean'),
                valid_session_count=('sbp_mean', 'size'),
            )
        )
        panel = daily_df.merge(
            daily_bp,
            on=['respondent_id', 'date'],
            how='left',
            validate='one_to_one',
        )
    else:
        panel = daily_df.copy()
        panel['sbp_mean'] = np.nan
        panel['dbp_mean'] = np.nan
        panel['valid_session_count'] = 0

    panel['valid_session_count'] = panel['valid_session_count'].fillna(0).astype(int)
    age_series = panel['age'] if 'age' in panel.columns else pd.Series([np.nan] * len(panel), index=panel.index)
    panel['age_group'] = age_series.map(age_band)
    return panel, assessed


def _series_iqr(series: pd.Series) -> float | None:
    """Compute interquartile range (Q75 - Q25) for non-null values."""
    clean = series.dropna()
    if len(clean) < 2:
        return None
    q75, q25 = np.percentile(clean.astype(float), [75, 25])
    return _clean_float(q75 - q25, 2)


def summarize_category_associations(
    day_panel: pd.DataFrame,
    fields: Iterable[str] = CATEGORY_RISK_FIELDS,
    *,
    min_group_n: int = 5,
    min_respondents: int = 3,
) -> dict[str, dict]:
    """Summarize daily SBP/DBP per category for each categorical risk factor.

    Rows where either the risk category or `sbp_mean` is missing are excluded
    from group counts and reported explicitly in `missing_*` counts.
    """
    total_rows = int(len(day_panel))
    has_dbp = 'dbp_mean' in day_panel.columns
    results: dict[str, dict] = {}

    for field in fields:
        if field not in day_panel.columns or total_rows == 0:
            results[field] = {
                'field': field,
                'grain': GRAIN_DAILY,
                'total_daily_rows': total_rows,
                'valid_n': 0,
                'respondents': 0,
                'missing_factor_count': total_rows if field in day_panel.columns else None,
                'missing_sbp_count': int(day_panel['sbp_mean'].isna().sum()) if total_rows and 'sbp_mean' in day_panel.columns else total_rows,
                'small_group_threshold': {'min_n': min_group_n, 'min_respondents': min_respondents},
                'groups': [],
            }
            continue

        missing_factor = int(day_panel[field].isna().sum())
        missing_sbp = int(day_panel['sbp_mean'].isna().sum())
        valid = day_panel.dropna(subset=[field, 'sbp_mean'])
        valid_n = int(len(valid))
        unique_resp = int(valid['respondent_id'].nunique()) if valid_n else 0

        groups = []
        if valid_n:
            for category, grp in valid.groupby(field, sort=True):
                n = int(len(grp))
                n_resp = int(grp['respondent_id'].nunique())
                sbp_vals = grp['sbp_mean'].astype(float)
                groups.append({
                    'category': str(category),
                    'n': n,
                    'respondents': n_resp,
                    'share_of_valid_pct': round(100.0 * n / valid_n, 1),
                    'sbp_mean': _clean_float(sbp_vals.mean(), 1),
                    'sbp_std': _clean_float(sbp_vals.std(ddof=1), 2) if n >= 2 else None,
                    'sbp_median': _clean_float(sbp_vals.median(), 1),
                    'sbp_iqr': _series_iqr(sbp_vals),
                    'dbp_mean': _clean_float(grp['dbp_mean'].astype(float).mean(), 1) if has_dbp and grp['dbp_mean'].notna().any() else None,
                    'small_group': bool(n < min_group_n or n_resp < min_respondents),
                })

        results[field] = {
            'field': field,
            'grain': GRAIN_DAILY,
            'total_daily_rows': total_rows,
            'valid_n': valid_n,
            'respondents': unique_resp,
            'missing_factor_count': missing_factor,
            'missing_sbp_count': missing_sbp,
            'small_group_threshold': {'min_n': min_group_n, 'min_respondents': min_respondents},
            'groups': groups,
        }

    return results


def _safe_correlation(x: pd.Series, y: pd.Series, method: str) -> float | None:
    """Compute Pearson or Spearman correlation when at least 3 non-constant pairs exist."""
    if len(x) < 3 or x.nunique() < 2 or y.nunique() < 2:
        return None
    return _clean_float(x.astype(float).corr(y.astype(float), method=method), 4)


def summarize_numeric_associations(
    day_panel: pd.DataFrame,
    fields: Iterable[str] = NUMERIC_RISK_FIELDS,
    *,
    min_pairs: int = 10,
    min_respondents: int = 3,
) -> list[dict]:
    """Compute descriptive statistics, Pearson r, and Spearman rho against daily SBP.

    Missing values are never imputed to zero; completeness and small-sample flags
    are reported alongside every variable.
    """
    total_rows = int(len(day_panel))
    rows: list[dict] = []

    for field in fields:
        if field not in day_panel.columns or total_rows == 0:
            rows.append({
                'field': field,
                'grain': GRAIN_DAILY,
                'total_daily_rows': total_rows,
                'n': 0,
                'respondents': 0,
                'missing_factor_count': total_rows if field in day_panel.columns else None,
                'completeness_pct': 0.0 if total_rows else None,
                'mean': None,
                'std': None,
                'median': None,
                'min': None,
                'max': None,
                'pearson_r': None,
                'spearman_r': None,
                'small_sample': True,
                'unreliable_reason': 'Tidak ada data tersedia pada filter aktif.',
            })
            continue

        factor_series = pd.to_numeric(day_panel[field], errors='coerce')
        missing_factor = int(factor_series.isna().sum())
        completeness = round(100.0 * (total_rows - missing_factor) / total_rows, 1)

        pairs = day_panel.assign(_x=factor_series).dropna(subset=['_x', 'sbp_mean'])
        n = int(len(pairs))
        n_resp = int(pairs['respondent_id'].nunique()) if n else 0

        x = pairs['_x'].astype(float)
        y = pairs['sbp_mean'].astype(float)
        pearson_r = _safe_correlation(x, y, 'pearson')
        spearman_r = _safe_correlation(x, y, 'spearman')

        small_sample = bool(n < min_pairs or n_resp < min_respondents)
        reason = None
        if n < 3:
            reason = 'Pasangan lengkap kurang dari 3; korelasi tidak dihitung.'
        elif x.nunique() < 2 or y.nunique() < 2:
            reason = 'Salah satu variabel tidak memiliki variasi nilai.'
        elif small_sample:
            reason = f'Sampel kecil (n={n}, responden={n_resp}); interpretasi sangat terbatas.'

        rows.append({
            'field': field,
            'grain': GRAIN_DAILY,
            'total_daily_rows': total_rows,
            'n': n,
            'respondents': n_resp,
            'missing_factor_count': missing_factor,
            'completeness_pct': completeness,
            'mean': _clean_float(x.mean(), 2) if n else None,
            'std': _clean_float(x.std(ddof=1), 2) if n >= 2 else None,
            'median': _clean_float(x.median(), 2) if n else None,
            'min': _clean_float(x.min(), 2) if n else None,
            'max': _clean_float(x.max(), 2) if n else None,
            'pearson_r': pearson_r,
            'spearman_r': spearman_r,
            'small_sample': small_sample,
            'unreliable_reason': reason,
        })

    return rows


def summarize_stress_levels(
    day_panel: pd.DataFrame,
    *,
    min_group_n: int = 5,
    min_respondents: int = 3,
) -> list[dict]:
    """Summarize daily SBP across ordinal stress levels (1..5)."""
    if len(day_panel) == 0 or 'stress' not in day_panel.columns:
        return []
    valid = day_panel.dropna(subset=['stress', 'sbp_mean']).copy()
    if len(valid) == 0:
        return []
    valid['_stress_int'] = pd.to_numeric(valid['stress'], errors='coerce')
    valid = valid.dropna(subset=['_stress_int'])

    levels = []
    for level, grp in valid.groupby('_stress_int', sort=True):
        n = int(len(grp))
        n_resp = int(grp['respondent_id'].nunique())
        sbp_vals = grp['sbp_mean'].astype(float)
        levels.append({
            'stress_level': int(level) if float(level).is_integer() else float(level),
            'n': n,
            'respondents': n_resp,
            'sbp_mean': _clean_float(sbp_vals.mean(), 1),
            'sbp_median': _clean_float(sbp_vals.median(), 1),
            'sbp_iqr': _series_iqr(sbp_vals),
            'small_group': bool(n < min_group_n or n_resp < min_respondents),
        })
    return levels


def summarize_age_group_bp(
    assessed_sessions: pd.DataFrame,
    *,
    min_group_n: int = 10,
    min_respondents: int = 3,
) -> list[dict]:
    """Summarize valid session SBP and DBP across canonical age bands."""
    if len(assessed_sessions) == 0 or 'is_valid' not in assessed_sessions.columns:
        return []
    valid = assessed_sessions[assessed_sessions['is_valid']].copy()
    if len(valid) == 0:
        return []

    age_col = valid['age'] if 'age' in valid.columns else pd.Series([np.nan] * len(valid), index=valid.index)
    valid['age_group'] = age_col.map(age_band)

    groups = []
    for label in AGE_GROUPS:
        grp = valid[valid['age_group'] == label]
        if len(grp) == 0:
            continue
        n = int(len(grp))
        n_resp = int(grp['respondent_id'].nunique()) if 'respondent_id' in grp.columns else 0
        groups.append({
            'age_group': label,
            'grain': GRAIN_SESSION,
            'n_sessions': n,
            'respondents': n_resp,
            'sbp_mean': _clean_float(grp['sbp_mean'].astype(float).mean(), 1),
            'sbp_median': _clean_float(grp['sbp_mean'].astype(float).median(), 1),
            'dbp_mean': _clean_float(grp['dbp_mean'].astype(float).mean(), 1),
            'dbp_median': _clean_float(grp['dbp_mean'].astype(float).median(), 1),
            'small_group': bool(n < min_group_n or n_resp < min_respondents),
        })
    return groups


def summarize_missing_and_quality(
    day_panel: pd.DataFrame,
    assessed_sessions: pd.DataFrame | None = None,
    fields: Iterable[str] = ALL_RISK_FIELDS,
) -> dict:
    """Report missingness across all lifestyle risk factors and BP session status."""
    total_daily = int(len(day_panel))
    has_sbp = day_panel['sbp_mean'].notna() if total_daily and 'sbp_mean' in day_panel.columns else pd.Series(dtype=bool)

    field_missing = []
    for field in fields:
        present = field in day_panel.columns
        if not present or total_daily == 0:
            field_missing.append({
                'field': field,
                'total_daily_rows': total_daily,
                'missing_count': total_daily if present else None,
                'missing_pct': 100.0 if (present and total_daily > 0) else None,
                'complete_with_sbp_count': 0,
            })
            continue

        not_na = day_panel[field].notna()
        missing_cnt = int((~not_na).sum())
        complete_cnt = int((not_na & has_sbp).sum())
        field_missing.append({
            'field': field,
            'total_daily_rows': total_daily,
            'missing_count': missing_cnt,
            'missing_pct': round(100.0 * missing_cnt / total_daily, 1),
            'complete_with_sbp_count': complete_cnt,
        })

    session_total = int(len(assessed_sessions)) if assessed_sessions is not None else 0
    valid_sessions = int(assessed_sessions['is_valid'].sum()) if session_total and 'is_valid' in assessed_sessions.columns else 0
    pending_review = (
        int((assessed_sessions['review_status'] == 'pending_review').sum())
        if session_total and 'review_status' in assessed_sessions.columns
        else 0
    )

    return {
        'daily_records': total_daily,
        'daily_with_valid_bp': int(has_sbp.sum()) if total_daily else 0,
        'daily_without_valid_bp': int((~has_sbp).sum()) if total_daily else 0,
        'session_records': session_total,
        'valid_sessions': valid_sessions,
        'incomplete_or_pending_sessions': session_total - valid_sessions,
        'pending_review_sessions': pending_review,
        'fields': field_missing,
    }


def build_risk_analysis_report(
    profiles: pd.DataFrame,
    sessions: pd.DataFrame,
    daily: pd.DataFrame,
    *,
    source_kind: str = 'synthetic',
    min_group_n: int = 5,
    min_respondents: int = 3,
) -> dict:
    """Build a complete, non-causal descriptive risk-analysis report.

    Suitable for offline audit reports, notebooks, and future API integration
    (route wiring coordinated through Hugo).
    """
    day_panel, assessed_sessions = build_daily_bp_panel(sessions, daily, profiles)
    missing_summary = summarize_missing_and_quality(day_panel, assessed_sessions)

    respondents = int(day_panel['respondent_id'].nunique()) if len(day_panel) else 0
    respondents_bp = (
        int(day_panel.loc[day_panel['sbp_mean'].notna(), 'respondent_id'].nunique())
        if len(day_panel)
        else 0
    )

    empty = len(day_panel) == 0 or missing_summary['valid_sessions'] == 0
    return {
        'source_kind': source_kind,
        'bp_policy_version': POLICY_VERSION,
        'grain': GRAIN_DAILY,
        'is_causal': False,
        'is_diagnosis': False,
        'empty': empty,
        'disclaimer': DISCLAIMER_ID,
        'sample_summary': {
            'respondents': respondents,
            'respondents_with_valid_bp': respondents_bp,
            'daily_records': missing_summary['daily_records'],
            'valid_sessions': missing_summary['valid_sessions'],
            'pending_review_sessions': missing_summary['pending_review_sessions'],
        },
        'missing_summary': missing_summary,
        'category_associations': summarize_category_associations(
            day_panel,
            min_group_n=min_group_n,
            min_respondents=min_respondents,
        ),
        'numeric_associations': summarize_numeric_associations(
            day_panel,
            min_pairs=max(min_group_n, 10),
            min_respondents=min_respondents,
        ),
        'stress_levels': summarize_stress_levels(
            day_panel,
            min_group_n=min_group_n,
            min_respondents=min_respondents,
        ),
        'age_group_bp': summarize_age_group_bp(
            assessed_sessions,
            min_group_n=max(min_group_n, 10),
            min_respondents=min_respondents,
        ),
    }
