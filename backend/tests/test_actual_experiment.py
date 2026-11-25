
import json
from pathlib import Path
import sys
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.actual_experiment import (
    CONTRACT_VERSION,
    ExperimentIneligibleError,
    ReleaseValidationError,
    assess_experiment_eligibility,
    evaluate_candidates_on_train,
    run_actual_experiment,
    temporal_purged_partitions,
    verify_release_package,
)
from app.baseline import FEATURES, TARGET, make_training
from etl.train_actual_model import execute as run_cli_execute, legacy_artifact_hashes


def _make_long_synthetic_panel(n_ids: int = 12, n_days: int = 45):
    """Build a synthetic multi-respondent panel spanning 45 days to test purged inner CV."""
    dates = pd.date_range('2026-07-01', periods=n_days, freq='D')
    profiles = pd.DataFrame([
        {'respondent_id': f'TST{i:03d}', 'age': 25 + i * 2, 'bmi': 22.0 + (i % 5)}
        for i in range(n_ids)
    ])
    daily_rows = []
    session_rows = []
    for i in range(n_ids):
        rid = f'TST{i:03d}'
        base_sbp = 115.0 + (i % 4) * 5.0
        for d_idx, dt in enumerate(dates):
            daily_rows.append({
                'respondent_id': rid,
                'date': dt.strftime('%Y-%m-%d'),
                'sleep_hours': 6.5 + (d_idx % 3) * 0.5,
                'stress': 1 + (d_idx % 5),
                'activity_minutes': 20 + (d_idx % 4) * 10,
            })
            sbp = base_sbp + (d_idx % 5) - 2.0
            session_rows.append({
                'respondent_id': rid,
                'date': dt.strftime('%Y-%m-%d'),
                'session': 'Pagi',
                'sbp1': sbp, 'dbp1': 76.0,
                'sbp2': sbp + 1.0, 'dbp2': 77.0,
            })
    return profiles, pd.DataFrame(session_rows), pd.DataFrame(daily_rows)


def test_eligibility_gate_rejects_insufficient_or_missing_actual_data(tmp_path):
    # 1) Missing actual CSV exports -> fails closed and writes limitation report
    report_dir = tmp_path / 'reports'
    with pytest.raises(ExperimentIneligibleError) as exc_info:
        run_actual_experiment(
            tmp_path / 'missing_profiles.csv',
            tmp_path / 'missing_daily.csv',
            source_kind='actual',
            report_dir=report_dir,
        )
    assert 'actual_export_files_missing' in exc_info.value.reasons
    assert (report_dir / 'LIMITATIONS_REPORT.md').is_file()
    assert (report_dir / 'eligibility_status.json').is_file()

    # 2) Too few respondents / short calendar -> rejected by eligibility gate
    profiles, sessions, daily = _make_long_synthetic_panel(n_ids=3, n_days=16)
    status = assess_experiment_eligibility(profiles, sessions, daily, {}, source_kind='actual')
    assert status['eligible'] is False
    assert any('minimum' in r for r in status['reasons'])


def test_temporal_purged_split_and_chronological_inner_cv_on_longer_calendar():
    profiles, sessions, daily = _make_long_synthetic_panel(n_ids=12, n_days=60)
    status = assess_experiment_eligibility(profiles, sessions, daily, {}, source_kind='synthetic')
    assert status['eligible'] is True
    assert status['window_summary']['chronological_inner_cv_supported'] is True

    frame = make_training(profiles, daily, sessions)
    parts = temporal_purged_partitions(frame)
    train, test = parts['train'], parts['test']

    # Zero respondent overlap + chronological target purge + non-overlapping test targets
    assert set(train['respondent_id']).isdisjoint(test['respondent_id'])
    assert train['target_end'].max() <= test['asof_date'].min()

    # Validate candidate models strictly on train with fit-only preprocessing & chronological purge
    val_res = evaluate_candidates_on_train(train)
    assert val_res['cv_strategy'] == 'respondent_group_kfold_chronological_purged'
    assert val_res['selection']['selected'] in ('Linear Regression', 'Random Forest', 'Hist Gradient Boosting')
    assert all(m['validation_rows'] > 0 and m['chronological_purged'] is True for m in val_res['folds'])


def test_short_calendar_records_non_chronological_inner_cv_limitation(prepared):
    profiles, daily, sessions, quality = prepared
    status = assess_experiment_eligibility(profiles, sessions, daily, quality, source_kind='synthetic')
    assert status['eligible'] is True
    assert status['window_summary']['chronological_inner_cv_supported'] is False
    assert any('GroupKFold' in lim for lim in status['limitations'])


def test_release_package_roundtrip_and_tamper_rejection(tmp_path):
    release_root = tmp_path / 'releases'
    report_dir = tmp_path / 'reports'

    res = run_actual_experiment(
        ROOT / 'data' / 'sample' / 'Data_Responden_Sintetis.csv',
        ROOT / 'data' / 'sample' / 'Data_Harian_Sintetis.csv',
        source_kind='synthetic',
        release_root=release_root,
        report_dir=report_dir,
        release_id='test-release-v1',
    )
    assert res['eligible'] is True
    rel_dir = Path(res['release']['release_dir'])

    model, manifest, metrics_doc = verify_release_package(rel_dir)
    assert manifest['contract_version'] == CONTRACT_VERSION
    assert manifest['features'] == FEATURES
    assert manifest['target'] == TARGET
    assert manifest['target_approval']['approved'] is False
    assert list(model.feature_names_in_) == FEATURES
    assert metrics_doc['leakage_audit']['labels_available_before_test'] is True

    # Tampering with metrics.json must be rejected by SHA-256 verification
    metrics_path = rel_dir / 'metrics.json'
    tampered = json.loads(metrics_path.read_text(encoding='utf-8'))
    tampered['selected_model'] = 'Tampered Model'
    metrics_path.write_text(json.dumps(tampered), encoding='utf-8')
    with pytest.raises(ReleaseValidationError, match='Hash metrik'):
        verify_release_package(rel_dir)


def test_cli_pipeline_preserves_cp3_p2_week10_artifacts():
    before = legacy_artifact_hashes()
    summary = run_cli_execute(run_synthetic_protocol=True)
    after = legacy_artifact_hashes()

    assert before == after
    assert summary['legacy_artifacts_untouched'] is True
    assert summary['actual_status']['eligible'] is False
    assert 'actual_export_files_missing' in summary['actual_status']['reasons']
    assert summary['protocol_dry_run']['release_id'] == 'synthetic-protocol-v1'
