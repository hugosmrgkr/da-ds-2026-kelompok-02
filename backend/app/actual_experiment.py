"""Actual-data eligibility gate, purged temporal validation, and release packager (Nahesson — DS).

Implements the model release pipeline defined in `docs/TUGAS_NAHESSON.md` and
`docs/MODEL_INTEGRATION_CONTRACT.md` without modifying or overwriting historical
CP3, P2, or Week 10 synthetic serving artifacts.

Key guarantees:
- Readiness & eligibility gate uses `data_readiness.build_readiness` and refuses
  ineligible/insufficient datasets via `ExperimentIneligibleError` instead of
  forcing training or fabricating scores.
- Outer split holds out respondent IDs AND enforces chronological target purge
  (`train.target_end.max() <= test.asof_date.min()`) with non-overlapping 7-day
  test targets (`test_target_stride_days=7`).
- Inner validation attempts strict respondent-and-time purged folds when the
  training calendar supports them; when the calendar is too short, it falls back
  to `GroupKFold` by respondent and explicitly records `chronological_inner_cv=False`
  as a documented limitation.
- Preprocessing (`SimpleImputer` + `StandardScaler`) is fit strictly on the
  fit/training fold and verified inside every fold.
- Releases are written to `models/releases/<release_id>/` with SHA-256 integrity
  verification (`utf8-lf-v1` for metrics text, exact binary bytes for joblib)
  and a structured `MODEL_CARD.md`.
"""

from __future__ import annotations

import hashlib
from io import BytesIO
import json
import math
import platform
import re
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.model_selection import GroupKFold, GroupShuffleSplit

from .baseline import (
    CONFIG,
    FEATURES,
    TARGET,
    leakage_audit,
    make_training,
    sha256,
    text_sha256,
)
from .bp_policy import assessed_frame
from .data_readiness import build_readiness
from .model_comparison import (
    HYPERPARAMETERS,
    LEARNED,
    NAIVE,
    build_model,
    column_key,
    metrics,
)
from .model_registry import FEATURE_SCHEMA_VERSION, HEX64
from .pipeline import prepare

CONTRACT_VERSION = 'release-v1'
DATASET_SCHEMA_VERSION = 'cp2-v1'
METRICS_HASH_MODE = 'utf8-lf-v1'
HISTORY_DAYS = 7
HORIZON_DAYS = 7
RELEASE_ID_PATTERN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{2,63}$')

DEFAULT_ELIGIBILITY_THRESHOLDS = {
    'min_profiles': 8,
    'min_total_respondents': 8,
    'min_train_ids': 5,
    'min_test_ids': 2,
    'min_train_windows': 15,
    'min_test_windows': 2,
    'min_calendar_days': 21,
}


class ExperimentIneligibleError(ValueError):
    """Raised when dataset fails readiness or temporal-split eligibility checks."""

    def __init__(self, message: str, reasons: list[str], report: dict | None = None):
        super().__init__(message)
        self.reasons = reasons
        self.report = report or {}


class ReleaseValidationError(ValueError):
    """Raised when a model release package fails manifest, hash, or schema checks."""


def _text_digest_str(text: str) -> str:
    normalized = text.replace('\r\n', '\n').encode('utf-8')
    return hashlib.sha256(normalized).hexdigest()


def _signed_bias_summary(actual: np.ndarray, predicted: np.ndarray) -> dict:
    """Compute signed error summary (bias = predicted - actual)."""
    errors = np.asarray(predicted, dtype=float) - np.asarray(actual, dtype=float)
    return {
        'mean_bias_mmhg': round(float(errors.mean()), 4),
        'median_bias_mmhg': round(float(np.median(errors)), 4),
        'underpredicted_count': int((errors < 0).sum()),
        'overpredicted_count': int((errors > 0).sum()),
        'exact_count': int((errors == 0).sum()),
    }


def _select_non_overlapping_test(frame: pd.DataFrame, stride_days: int = 7) -> pd.DataFrame:
    """Space test target windows per respondent so target intervals never overlap."""
    anchors = []
    for _, group in frame.groupby('respondent_id', sort=True):
        previous_end = None
        for index, row in group.sort_values('asof_date').iterrows():
            if previous_end is None or row.target_start > previous_end:
                anchors.append(index)
                previous_end = row.target_end
    return frame.loc[anchors].copy()


def temporal_purged_partitions(
    frame: pd.DataFrame,
    *,
    heldout_id_fraction: float = CONFIG['heldout_id_fraction'],
    calendar_train_fraction: float = CONFIG['calendar_train_fraction'],
    seed: int = CONFIG['seed'],
    min_train_ids: int = DEFAULT_ELIGIBILITY_THRESHOLDS['min_train_ids'],
    min_test_ids: int = DEFAULT_ELIGIBILITY_THRESHOLDS['min_test_ids'],
    min_train_windows: int = DEFAULT_ELIGIBILITY_THRESHOLDS['min_train_windows'],
    min_test_windows: int = DEFAULT_ELIGIBILITY_THRESHOLDS['min_test_windows'],
) -> dict:
    """Split complete windows by held-out respondent IDs AND chronological target purge.

    No respondent appears in both `train` and `test`, all training target intervals
    end on or before `cutoff`, all test origins start on or after `cutoff`, and
    primary test targets are spaced to avoid overlapping 7-day target intervals.
    """
    if frame.empty:
        raise ExperimentIneligibleError(
            'Tidak ada window 14-hari lengkap untuk dilakukan split.',
            ['no_complete_windows'],
        )
    if frame['target'].isna().any():
        raise ExperimentIneligibleError(
            'Target mengandung missing value; imputasi target dilarang.',
            ['missing_target_forbidden'],
        )

    n_ids = int(frame['respondent_id'].nunique())
    if n_ids < (min_train_ids + min_test_ids):
        raise ExperimentIneligibleError(
            f'Jumlah responden dengan window lengkap ({n_ids}) kurang dari minimum ({min_train_ids + min_test_ids}).',
            ['insufficient_window_respondents'],
        )

    splitter = GroupShuffleSplit(n_splits=1, test_size=heldout_id_fraction, random_state=seed)
    train_idx, test_idx = next(splitter.split(frame, groups=frame['respondent_id']))

    first = pd.Timestamp(frame['history_start'].min())
    last = pd.Timestamp(frame['target_end'].max())
    span_days = int((last - first).days + 1)
    cutoff = (first + pd.Timedelta(days=int(span_days * calendar_train_fraction) - 1)).date().isoformat()

    train_pool = frame.iloc[train_idx].copy()
    test_pool = frame.iloc[test_idx].copy()

    train = train_pool[train_pool['target_end'] <= cutoff].copy()
    rolling_test = test_pool[test_pool['asof_date'] >= cutoff].copy()
    test = _select_non_overlapping_test(rolling_test, stride_days=HORIZON_DAYS)

    reasons = []
    if len(train) < min_train_windows:
        reasons.append(f'train_windows_below_minimum ({len(train)} < {min_train_windows})')
    if len(test) < min_test_windows:
        reasons.append(f'test_windows_below_minimum ({len(test)} < {min_test_windows})')
    if train['respondent_id'].nunique() < min_train_ids:
        reasons.append(f'train_ids_below_minimum ({train["respondent_id"].nunique()} < {min_train_ids})')
    if test['respondent_id'].nunique() < min_test_ids:
        reasons.append(f'test_ids_below_minimum ({test["respondent_id"].nunique()} < {min_test_ids})')

    if reasons:
        raise ExperimentIneligibleError(
            'Split temporal dengan purge target tidak memenuhi ukuran sampel minimum.',
            reasons,
        )

    return {
        'train': train.reset_index(drop=True),
        'test': test.reset_index(drop=True),
        'rolling_test': rolling_test.reset_index(drop=True),
        'cutoff': cutoff,
        'calendar_span_days': span_days,
    }


def assess_experiment_eligibility(
    profiles: pd.DataFrame | list[dict],
    sessions: pd.DataFrame | list[dict],
    daily: pd.DataFrame | list[dict],
    quality: dict,
    *,
    source_kind: str,
    thresholds: dict | None = None,
) -> dict:
    """Assess whether data passes Aldi's readiness rules and Nahesson's ML thresholds.

    Returns a structured dictionary with `eligible: bool`, `reasons: list[str]`,
    `readiness: dict`, `limitations: list[str]`, and (when windows exist) `window_summary`.
    """
    cfg = {**DEFAULT_ELIGIBILITY_THRESHOLDS, **(thresholds or {})}
    prof_df = pd.DataFrame(profiles)
    sess_df = pd.DataFrame(sessions)
    daily_df = pd.DataFrame(daily)

    if len(sess_df) and 'review_status' not in sess_df.columns:
        sess_df = assessed_frame(sess_df)

    readiness = build_readiness(prof_df, sess_df, daily_df, quality or {}, source_kind)
    reasons: list[str] = []
    limitations: list[str] = []

    if source_kind not in ('actual', 'synthetic'):
        reasons.append(f'source_kind_not_trainable ({source_kind})')
    if readiness['profiles'] < cfg['min_profiles']:
        reasons.append(f'profiles_below_minimum ({readiness["profiles"]} < {cfg["min_profiles"]})')
    if readiness['date_count'] < cfg['min_calendar_days']:
        reasons.append(f'calendar_days_below_minimum ({readiness["date_count"]} < {cfg["min_calendar_days"]})')
    if readiness['training_window_respondents'] < cfg['min_total_respondents']:
        reasons.append(
            f'window_respondents_below_minimum ({readiness["training_window_respondents"]} < {cfg["min_total_respondents"]})'
        )
    if readiness['unresolved_session_reviews'] > 0:
        limitations.append(
            f'{readiness["unresolved_session_reviews"]} sesi pending_review dikecualikan dari target & fitur BP.'
        )

    window_summary = {
        'complete_windows': 0,
        'train_windows': 0,
        'test_windows': 0,
        'train_ids': 0,
        'test_ids': 0,
        'cutoff': None,
        'chronological_inner_cv_supported': False,
    }

    if len(prof_df) and len(sess_df) and len(daily_df) and not reasons:
        frame = make_training(prof_df, daily_df, sess_df)
        window_summary['complete_windows'] = int(len(frame))
        try:
            parts = temporal_purged_partitions(
                frame,
                min_train_ids=cfg['min_train_ids'],
                min_test_ids=cfg['min_test_ids'],
                min_train_windows=cfg['min_train_windows'],
                min_test_windows=cfg['min_test_windows'],
            )
            train, test = parts['train'], parts['test']
            inner_chronological = _has_purged_inner_split(train)
            window_summary.update({
                'train_windows': int(len(train)),
                'test_windows': int(len(test)),
                'train_ids': int(train['respondent_id'].nunique()),
                'test_ids': int(test['respondent_id'].nunique()),
                'cutoff': parts['cutoff'],
                'chronological_inner_cv_supported': inner_chronological,
            })
            if not inner_chronological:
                limitations.append(
                    'Kalender training belum cukup panjang untuk inner CV kronologis murni; '
                    'inner validation menggunakan GroupKFold berbasis responden (kalender fit/val dapat beririsan).'
                )
            if len(test) < 15:
                limitations.append(
                    f'Ukuran test utama kecil ({len(test)} origin dari {test["respondent_id"].nunique()} ID); '
                    'metrik test bersifat tidak stabil dan bukan bukti generalisasi klinis.'
                )
        except ExperimentIneligibleError as exc:
            reasons.extend(exc.reasons)

    if source_kind == 'synthetic':
        limitations.append(
            'Dataset berstatus DATA SINTETIS / SIMULASI; tidak boleh digunakan untuk klaim penelitian aktual.'
        )

    return {
        'eligible': len(reasons) == 0,
        'source_kind': source_kind,
        'reasons': reasons,
        'thresholds': cfg,
        'readiness': readiness,
        'window_summary': window_summary,
        'limitations': limitations,
    }


def _inner_purge_cutoff(train: pd.DataFrame) -> str | None:
    """Return a chronological inner cutoff if `train` supports respondent+time purged CV."""
    if train.empty or train['respondent_id'].nunique() < 3:
        return None
    earliest_target_end = pd.Timestamp(train['target_end'].min())
    latest_asof = pd.Timestamp(train['asof_date'].max())
    if latest_asof <= earliest_target_end:
        return None
    mid = (earliest_target_end + pd.Timedelta(days=(latest_asof - earliest_target_end).days // 2)).date().isoformat()
    early = train[train['target_end'] <= mid]
    late = train[train['asof_date'] >= mid]
    if early['respondent_id'].nunique() < 2 or late['respondent_id'].nunique() < 2:
        return None
    return mid


def _has_purged_inner_split(train: pd.DataFrame) -> bool:
    """Check whether `train` calendar is long enough for respondent+time purged CV."""
    return _inner_purge_cutoff(train) is not None


def purged_inner_cv_splits(train: pd.DataFrame, max_folds: int = 4) -> tuple[list[tuple[np.ndarray, np.ndarray, dict]], str]:
    """Generate respondent-separated inner CV splits with chronological purge when feasible.

    When `train` spans enough calendar days, each fold fits strictly on earlier
    non-validation-ID windows (`target_end <= mid`) and validates on future
    validation-ID windows (`asof_date >= mid`). When the training calendar is too
    short, falls back to `GroupKFold` by respondent and records
    `chronological_purged=False` on every fold.
    """
    n_ids = int(train['respondent_id'].nunique())
    if n_ids < 3:
        raise ExperimentIneligibleError(
            'Minimal 3 responden pada train diperlukan untuk inner cross-validation.',
            ['insufficient_train_ids_for_cv'],
        )
    folds = min(max_folds, n_ids)
    splitter = GroupKFold(n_splits=folds)
    inner_cutoff = _inner_purge_cutoff(train)
    splits = []
    all_chronological = inner_cutoff is not None

    for fold_num, (raw_fit_idx, raw_val_idx) in enumerate(splitter.split(train, groups=train['respondent_id'])):
        if inner_cutoff is not None:
            fit_mask = (train.index.isin(raw_fit_idx)) & (train['target_end'] <= inner_cutoff)
            val_mask = (train.index.isin(raw_val_idx)) & (train['asof_date'] >= inner_cutoff)
            fit_idx = np.flatnonzero(fit_mask.to_numpy())
            val_idx = np.flatnonzero(val_mask.to_numpy())
            if len(fit_idx) == 0 or len(val_idx) == 0:
                all_chronological = False
                fit_idx, val_idx = raw_fit_idx, raw_val_idx
        else:
            fit_idx, val_idx = raw_fit_idx, raw_val_idx

        fit, val = train.iloc[fit_idx], train.iloc[val_idx]
        if set(fit['respondent_id']) & set(val['respondent_id']):
            raise AssertionError('ID responden bocor antara fit dan validasi inner CV')
        chronological = bool(fit['target_end'].max() <= val['asof_date'].min())
        if not chronological:
            all_chronological = False
        splits.append((
            fit_idx,
            val_idx,
            {
                'fold': fold_num,
                'fit_rows': int(len(fit)),
                'validation_rows': int(len(val)),
                'fit_ids': sorted(fit['respondent_id'].unique().tolist()),
                'validation_ids': sorted(val['respondent_id'].unique().tolist()),
                'fit_target_end_max': str(fit['target_end'].max()),
                'validation_origin_min': str(val['asof_date'].min()),
                'chronological_purged': chronological,
            },
        ))

    strategy = (
        'respondent_group_kfold_chronological_purged'
        if all_chronological
        else 'respondent_group_kfold_non_chronological_short_calendar'
    )
    return splits, strategy


def evaluate_candidates_on_train(train: pd.DataFrame, max_folds: int = 4) -> dict:
    """Validate Naive baseline + candidate regressors using fit-only preprocessing inside train."""
    splits, cv_strategy = purged_inner_cv_splits(train, max_folds=max_folds)
    predictions = {name: np.full(len(train), np.nan) for name in (NAIVE, *LEARNED)}
    fold_of = np.full(len(train), -1)
    fold_metadata = []

    for fit_idx, val_idx, meta in splits:
        fit, val = train.iloc[fit_idx], train.iloc[val_idx]
        fold_num = meta['fold']
        fold_of[val_idx] = fold_num
        fold_metadata.append(meta)

        predictions[NAIVE][val_idx] = val['past_7d_sbp'].to_numpy()
        for name in LEARNED:
            model = build_model(name).fit(fit[FEATURES], fit['target'])
            # Strict fit-only preprocessing verification inside every fold.
            np.testing.assert_allclose(
                model.named_steps['impute'].statistics_,
                fit[FEATURES].median().fillna(0).to_numpy(),
            )
            imputed_fit = model.named_steps['impute'].transform(fit[FEATURES])
            np.testing.assert_allclose(model.named_steps['scale'].mean_, imputed_fit.mean(axis=0))
            predictions[name][val_idx] = model.predict(val[FEATURES])

    eval_mask = fold_of >= 0
    actual = train['target'].to_numpy()[eval_mask]
    scores = {name: metrics(actual, values[eval_mask]) for name, values in predictions.items()}
    all_actual = train['target'].to_numpy()
    per_fold = {
        name: [
            {'fold': meta['fold'], **metrics(all_actual[fold_of == meta['fold']], predictions[name][fold_of == meta['fold']])}
            for meta in fold_metadata
        ]
        for name in predictions
    }

    ranked = sorted(LEARNED, key=lambda n: (scores[n]['rmse'], scores[n]['mae'], n))
    selected_name = ranked[0]
    selection = {
        'selected': selected_name,
        'ranking': ranked,
        'rule': 'RMSE validasi terkecil di antara model terlatih; tie dipecah MAE lalu nama',
        'beats_naive_on_validation': bool(scores[selected_name]['rmse'] < scores[NAIVE]['rmse']),
        'cv_strategy': cv_strategy,
    }
    return {
        'scores': scores,
        'per_fold': per_fold,
        'folds': fold_metadata,
        'selection': selection,
        'cv_strategy': cv_strategy,
        'predictions': predictions,
    }


def _render_model_card(manifest: dict, metrics_doc: dict) -> str:
    """Render a 1-page markdown Model Card from verified manifest & metrics."""
    rows = []
    for row in metrics_doc['comparison']:
        val, tst = row['validation'], row['test']
        r2_str = f"{tst['r2']:.3f}" if tst['r2'] is not None else 'N/A'
        rows.append(
            f"| {row['model']} | {row['kind']} | {val['mae']:.3f} | {val['rmse']:.3f} | "
            f"{tst['mae']:.3f} | {tst['rmse']:.3f} | {r2_str} |"
        )
    lims = '\n'.join(f'- {item}' for item in manifest['limitations']) or '- Tidak ada catatan tambahan.'
    return (
        f"# Model Card — Rilis `{manifest['release_id']}`\n\n"
        f"- **Status rilis:** `{manifest['release_status']}` (`source_kind={manifest['source_kind']}`)\n"
        f"- **Run ID:** `{manifest['run_id']}`\n"
        f"- **Algoritma terpilih:** **{manifest['algorithm']}**\n"
        f"- **Target & horizon:** `{manifest['target']}` (histori {manifest['history_days']} hari, horizon {manifest['horizon_days']} hari, satuan mmHg)\n"
        f"- **Fitur berurutan (`{manifest['feature_schema_version']}`):** {', '.join(manifest['features'])}\n"
        f"- **Persetujuan target dosen:** `{manifest['target_approval']['approved']}` ({manifest['target_approval']['note']})\n"
        f"- **Dilatih pada (UTC):** `{manifest['trained_on']}`\n"
        f"- **Training data fingerprint:** `{manifest['training_data_version']}`\n\n"
        f"## Ringkasan Evaluasi ({manifest['metrics_scope']})\n\n"
        f"Validasi memilih **{manifest['selection']['selected']}** berdasarkan `{manifest['selection']['rule']}`. "
        f"Mengalahkan baseline naif pada validasi: **{manifest['selection']['beats_naive_on_validation']}**.\n\n"
        "| Metode | Jenis | MAE Val | RMSE Val | MAE Test | RMSE Test | R² Test |\n"
        "|---|---|---:|---:|---:|---:|---:|\n"
        + '\n'.join(rows)
        + "\n\n## Keterbatasan & Batas Penggunaan\n\n"
        + lims
        + "\n"
    )


def save_release_package(
    release_dir: Path | str,
    *,
    release_id: str,
    model,
    metrics_doc: dict,
    training_data_version: str,
    source_kind: str,
    limitations: list[str],
    target_approved: bool = False,
    target_approval_note: str = 'Belum ada catatan persetujuan final dosen.',
    release_status: str = 'candidate',
) -> dict:
    """Persist a verified model release package to `models/releases/<release_id>/`."""
    if not RELEASE_ID_PATTERN.fullmatch(release_id):
        raise ReleaseValidationError(f'release_id tidak valid: {release_id}')
    if not HEX64.fullmatch(training_data_version):
        raise ReleaseValidationError('training_data_version harus SHA-256 hex 64 karakter.')
    if source_kind not in ('synthetic', 'actual'):
        raise ReleaseValidationError(f'source_kind tidak valid: {source_kind}')

    out = Path(release_dir)
    out.mkdir(parents=True, exist_ok=True)

    model_path = out / 'model.joblib'
    metrics_path = out / 'metrics.json'
    manifest_path = out / 'manifest.json'
    card_path = out / 'MODEL_CARD.md'

    joblib.dump(model, model_path)
    model_sha = sha256(model_path)

    metrics_payload = {
        **metrics_doc,
        'contract_version': CONTRACT_VERSION,
        'release_id': release_id,
        'model_file': 'model.joblib',
        'model_sha256': model_sha,
    }
    metrics_text = json.dumps(metrics_payload, indent=2, ensure_ascii=False) + '\n'
    metrics_path.write_text(metrics_text, encoding='utf-8', newline='\n')
    metrics_sha = text_sha256(metrics_path)

    trained_on = datetime.now(timezone.utc).isoformat()
    manifest = {
        'contract_version': CONTRACT_VERSION,
        'release_id': release_id,
        'run_id': metrics_doc['run_id'],
        'source_kind': source_kind,
        'training_data_version': training_data_version,
        'dataset_schema_version': DATASET_SCHEMA_VERSION,
        'feature_schema_version': FEATURE_SCHEMA_VERSION,
        'target': TARGET,
        'history_days': HISTORY_DAYS,
        'horizon_days': HORIZON_DAYS,
        'features': list(FEATURES),
        'algorithm': metrics_doc['selected_model'],
        'trained_on': trained_on,
        'model_file': 'model.joblib',
        'model_sha256': model_sha,
        'metrics_file': 'metrics.json',
        'metrics_sha256': metrics_sha,
        'metrics_hash_mode': METRICS_HASH_MODE,
        'metrics_scope': metrics_doc['metrics_scope'],
        'selection': metrics_doc['selection'],
        'sample_sizes': metrics_doc['sample_sizes'],
        'target_approval': {
            'approved': bool(target_approved),
            'note': target_approval_note,
        },
        'release_status': release_status,
        'feature_ranges': metrics_doc['feature_ranges'],
        'limitations': list(limitations),
        'versions': metrics_doc['versions'],
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + '\n',
        encoding='utf-8',
        newline='\n',
    )
    card_path.write_text(_render_model_card(manifest, metrics_doc), encoding='utf-8', newline='\n')

    return {
        'release_dir': str(out),
        'manifest_path': str(manifest_path),
        'metrics_path': str(metrics_path),
        'model_path': str(model_path),
        'model_card_path': str(card_path),
        'manifest': manifest,
    }


def _safe_release_file(folder: Path, filename: str) -> Path:
    if not isinstance(filename, str) or '/' in filename or '\\' in filename or ':' in filename or filename in ('.', '..'):
        raise ReleaseValidationError(f'Path file rilis tidak valid: {filename}')
    target = (folder / filename).resolve()
    if target.parent != folder.resolve():
        raise ReleaseValidationError(f'Path traversal terdeteksi pada: {filename}')
    if not target.is_file():
        raise ReleaseValidationError(f'File rilis tidak ditemukan: {filename}')
    return target


def verify_release_package(release_dir: Path | str) -> tuple[object, dict, dict]:
    """Strictly verify a release package's manifest, hashes, feature schema, and joblib model."""
    folder = Path(release_dir).resolve()
    manifest_path = _safe_release_file(folder, 'manifest.json')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))

    if manifest.get('contract_version') != CONTRACT_VERSION:
        raise ReleaseValidationError('Versi kontrak rilis tidak didukung.')
    if manifest.get('metrics_hash_mode') != METRICS_HASH_MODE:
        raise ReleaseValidationError('Mode hash metrik tidak didukung.')
    if (
        manifest.get('target') != TARGET
        or manifest.get('features') != FEATURES
        or manifest.get('history_days') != HISTORY_DAYS
        or manifest.get('horizon_days') != HORIZON_DAYS
        or manifest.get('feature_schema_version') != FEATURE_SCHEMA_VERSION
    ):
        raise ReleaseValidationError('Kontrak target, horizon, atau urutan fitur tidak cocok.')

    metrics_path = _safe_release_file(folder, manifest.get('metrics_file', ''))
    metrics_raw = metrics_path.read_bytes()
    metrics_text = metrics_raw.decode('utf-8')
    if not HEX64.fullmatch(str(manifest.get('metrics_sha256', ''))) or _text_digest_str(metrics_text) != manifest['metrics_sha256']:
        raise ReleaseValidationError('Hash metrik rilis tidak cocok.')
    metrics_doc = json.loads(metrics_text)

    model_path = _safe_release_file(folder, manifest.get('model_file', ''))
    model_raw = model_path.read_bytes()
    model_sha = hashlib.sha256(model_raw).hexdigest()
    if not HEX64.fullmatch(str(manifest.get('model_sha256', ''))) or model_sha != manifest['model_sha256']:
        raise ReleaseValidationError('Hash model joblib rilis tidak cocok.')

    if metrics_doc.get('run_id') != manifest.get('run_id') or metrics_doc.get('model_sha256') != model_sha:
        raise ReleaseValidationError('Metadata metrics.json dan manifest.json tidak konsisten.')

    model = joblib.load(BytesIO(model_raw))
    if (
        list(getattr(model, 'feature_names_in_', [])) != FEATURES
        or getattr(model, 'n_features_in_', None) != len(FEATURES)
        or not callable(getattr(model, 'predict', None))
    ):
        raise ReleaseValidationError('Model joblib tidak memiliki feature_names_in_ yang sesuai kontrak.')

    return model, manifest, metrics_doc


def run_actual_experiment(
    profile_csv: Path | str,
    day_csv: Path | str,
    *,
    source_kind: str = 'actual',
    release_root: Path | str | None = None,
    report_dir: Path | str | None = None,
    release_id: str | None = None,
    thresholds: dict | None = None,
) -> dict:
    """Run readiness gate, temporal purged experiment, and save release package if eligible.

    If the dataset is ineligible (e.g., actual data absent or below sample/calendar
    thresholds), writes a structured limitation report and raises `ExperimentIneligibleError`.
    Never overwrites CP3, P2, or Week 10 synthetic artifacts.
    """
    profile_path, day_path = Path(profile_csv), Path(day_csv)
    if not profile_path.is_file() or not day_path.is_file():
        reasons = ['actual_export_files_missing']
        report = {
            'eligible': False,
            'source_kind': source_kind,
            'reasons': reasons,
            'limitations': [
                f'Berkas ekspor sumber ({profile_path.name}, {day_path.name}) belum tersedia.'
            ],
        }
        if report_dir is not None:
            _write_ineligible_report(Path(report_dir), report)
        raise ExperimentIneligibleError(
            'Berkas data sumber belum tersedia; eksperimen tidak dapat dijalankan.',
            reasons,
            report,
        )

    is_synthetic = source_kind == 'synthetic'
    profiles_raw = pd.read_csv(profile_path, dtype=str, keep_default_na=False)
    daily_raw = pd.read_csv(day_path, dtype=str, keep_default_na=False)
    profiles, days, sessions, quality = prepare(profiles_raw, daily_raw, synthetic=is_synthetic)

    eligibility = assess_experiment_eligibility(
        profiles,
        sessions,
        days,
        quality,
        source_kind=source_kind,
        thresholds=thresholds,
    )
    if not eligibility['eligible']:
        if report_dir is not None:
            _write_ineligible_report(Path(report_dir), eligibility)
        raise ExperimentIneligibleError(
            'Data belum memenuhi kriteria kelayakan training dan validasi temporal.',
            eligibility['reasons'],
            eligibility,
        )

    frame = make_training(profiles, days, sessions)
    cfg = eligibility['thresholds']
    parts = temporal_purged_partitions(
        frame,
        min_train_ids=cfg['min_train_ids'],
        min_test_ids=cfg['min_test_ids'],
        min_train_windows=cfg['min_train_windows'],
        min_test_windows=cfg['min_test_windows'],
    )
    train, test = parts['train'], parts['test']

    # Stage 1 & 2: inner validation and selection strictly on `train`
    validation = evaluate_candidates_on_train(train)
    selection = validation['selection']
    selected_name = selection['selected']

    # Stage 3: fit on full `train`, verify leakage audit, and evaluate `test` once
    fitted = {name: build_model(name).fit(train[FEATURES], train['target']) for name in LEARNED}
    audits = {name: leakage_audit(train, test, fitted[name]) for name in LEARNED}

    test_predictions = {
        NAIVE: test['past_7d_sbp'].to_numpy(),
        **{name: fitted[name].predict(test[FEATURES]) for name in LEARNED},
    }
    actual_test = test['target'].to_numpy()
    test_scores = {name: metrics(actual_test, vals) for name, vals in test_predictions.items()}
    bias_summary = {name: _signed_bias_summary(actual_test, vals) for name, vals in test_predictions.items()}

    comparison = [
        {
            'model': name,
            'kind': 'baseline naif' if name == NAIVE else 'terlatih',
            'validation': validation['scores'][name],
            'test': test_scores[name],
            'bias': bias_summary[name],
            'hyperparameters': HYPERPARAMETERS.get(name, {}),
        }
        for name in (NAIVE, *LEARNED)
    ]

    pred_rows = test[['respondent_id', 'asof_date', 'target_start', 'target_end', 'target']].rename(
        columns={'asof_date': 'date', 'target': 'actual'}
    ).copy()
    for name, vals in test_predictions.items():
        key = column_key(name)
        pred_rows[key] = vals
        pred_rows[f'{key}_residual'] = pred_rows['actual'] - vals

    provenance = {
        'text_hash_mode': METRICS_HASH_MODE,
        'profile_sha256': text_sha256(profile_path),
        'daily_sha256': text_sha256(day_path),
        'prepared_content_sha256': quality['prepared_content_sha256'],
        'code_sha256': text_sha256(__file__),
        'versions': {
            'python': platform.python_version(),
            'numpy': np.__version__,
            'pandas': pd.__version__,
            'sklearn': sklearn.__version__,
            'joblib': joblib.__version__,
        },
    }
    run_id = hashlib.sha256(
        json.dumps({'provenance': provenance, 'config': CONFIG, 'source_kind': source_kind}, sort_keys=True).encode()
    ).hexdigest()[:20]

    feature_ranges = {
        col: {'min': float(train[col].min()), 'max': float(train[col].max())}
        for col in FEATURES
        if math.isfinite(float(train[col].min())) and math.isfinite(float(train[col].max()))
    }

    metrics_scope = 'actual_purged_test' if source_kind == 'actual' else 'synthetic_protocol_dry_run'
    metrics_doc = {
        'run_id': run_id,
        'source_kind': source_kind,
        'metrics_scope': metrics_scope,
        'target': TARGET,
        'history_days': HISTORY_DAYS,
        'horizon_days': HORIZON_DAYS,
        'features': list(FEATURES),
        'cutoff': parts['cutoff'],
        'sample_sizes': {
            'profiles': len(profiles),
            'daily_records': len(days),
            'complete_windows': len(frame),
            'train_windows': len(train),
            'test_windows': len(test),
            'train_ids': int(train['respondent_id'].nunique()),
            'test_ids': int(test['respondent_id'].nunique()),
        },
        'selection': selection,
        'selected_model': selected_name,
        'comparison': comparison,
        'validation_folds': validation['folds'],
        'leakage_audit': audits[selected_name],
        'feature_ranges': feature_ranges,
        'actual_vs_predicted': json.loads(pred_rows.to_json(orient='records')),
        'versions': provenance['versions'],
        'limitations': eligibility['limitations'],
    }

    final_release_id = release_id or (
        f'actual-{run_id[:10]}' if source_kind == 'actual' else 'synthetic-protocol-v1'
    )
    release_info = None
    if release_root is not None:
        release_dir = Path(release_root) / final_release_id
        release_info = save_release_package(
            release_dir,
            release_id=final_release_id,
            model=fitted[selected_name],
            metrics_doc=metrics_doc,
            training_data_version=quality['prepared_content_sha256'],
            source_kind=source_kind,
            limitations=eligibility['limitations'],
            target_approved=False,
            release_status='candidate',
        )

    if report_dir is not None:
        _write_experiment_report(Path(report_dir), eligibility, metrics_doc, pred_rows, release_info)

    return {
        'eligible': True,
        'run_id': run_id,
        'release_id': final_release_id,
        'eligibility': eligibility,
        'metrics': metrics_doc,
        'predictions': pred_rows,
        'release': release_info,
    }


def _write_ineligible_report(report_dir: Path, eligibility: dict) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / 'eligibility_status.json').write_text(
        json.dumps(eligibility, indent=2, ensure_ascii=False) + '\n',
        encoding='utf-8',
        newline='\n',
    )
    reasons_md = '\n'.join(f'- `{r}`' for r in eligibility.get('reasons', [])) or '- Tidak ada'
    lims_md = '\n'.join(f'- {l}' for l in eligibility.get('limitations', [])) or '- Tidak ada'
    md = (
        "# Laporan Kelayakan Eksperimen Model Aktual\n\n"
        f"- **Status layak:** `False` (`source_kind={eligibility.get('source_kind', 'unknown')}`)\n\n"
        "## Alasan Penolakan Gate Kelayakan\n\n"
        f"{reasons_md}\n\n"
        "## Catatan Keterbatasan\n\n"
        f"{lims_md}\n\n"
        "Eksperimen aktual **tidak dijalankan** karena syarat readiness/validasi temporal belum terpenuhi. "
        "Artefak sintetis CP3, P2, dan Minggu 10 tetap dipertahankan tanpa perubahan.\n"
    )
    (report_dir / 'LIMITATIONS_REPORT.md').write_text(md, encoding='utf-8', newline='\n')


def _write_experiment_report(
    report_dir: Path,
    eligibility: dict,
    metrics_doc: dict,
    pred_rows: pd.DataFrame,
    release_info: dict | None,
) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / 'eligibility_status.json').write_text(
        json.dumps(eligibility, indent=2, ensure_ascii=False) + '\n',
        encoding='utf-8',
        newline='\n',
    )
    (report_dir / 'experiment_metrics.json').write_text(
        json.dumps(metrics_doc, indent=2, ensure_ascii=False) + '\n',
        encoding='utf-8',
        newline='\n',
    )
    pred_rows.to_csv(report_dir / 'test_predictions.csv', index=False, lineterminator='\n')

    comp_rows = [
        {
            'model': r['model'],
            'kind': r['kind'],
            'val_mae': r['validation']['mae'],
            'val_rmse': r['validation']['rmse'],
            'test_mae': r['test']['mae'],
            'test_rmse': r['test']['rmse'],
            'test_r2': r['test']['r2'],
            'mean_bias_mmhg': r['bias']['mean_bias_mmhg'],
        }
        for r in metrics_doc['comparison']
    ]
    pd.DataFrame(comp_rows).to_csv(report_dir / 'comparison_summary.csv', index=False, lineterminator='\n')

    if release_info:
        (report_dir / 'MODEL_CARD_COPY.md').write_text(
            Path(release_info['model_card_path']).read_text(encoding='utf-8'),
            encoding='utf-8',
            newline='\n',
        )
