"""Unit & integration tests for Nahesson's `app.risk_analysis` module.

Verifies daily-grain aggregation, `bp_policy` exclusion of invalid/pending
sessions, preservation of missing values (especially `sleep_hours` and
`smoke_count`), small-group flagging, correlation edge cases, and consistency
with the `/api/analytics` contract on the labelled synthetic fixture.
"""

import pandas as pd
import pytest

from test_cp3_stage1 import client, loaded  # noqa: F401 - expose dependent pytest fixture
from app.risk_analysis import (
    ALL_RISK_FIELDS,
    CATEGORY_RISK_FIELDS,
    NUMERIC_RISK_FIELDS,
    build_daily_bp_panel,
    build_risk_analysis_report,
    summarize_category_associations,
    summarize_numeric_associations,
    summarize_stress_levels,
)


def _sample_frames():
    profiles = pd.DataFrame([
        {'respondent_id': 'R1', 'age': 28, 'occupation': 'Pegawai'},
        {'respondent_id': 'R2', 'age': 42, 'occupation': 'Wiraswasta'},
        {'respondent_id': 'R3', 'age': 51, 'occupation': 'Petani'},
    ])
    daily = pd.DataFrame([
        {
            'respondent_id': 'R1', 'date': '2026-09-01',
            'sleep_hours': 7.5, 'stress': 2, 'activity_minutes': 45,
            'salty_food': '1 kali', 'fruit': '1 porsi', 'vegetable': '2 porsi',
            'caffeine': '1 gelas', 'smoked': 'Tidak berlaku karena saya tidak merokok',
            'smoke_count': None, 'medication': 'Saya tidak menggunakan obat tekanan darah',
            'sitting': '4–7 jam', 'activity_type': 'Jalan kaki untuk olahraga',
        },
        {
            'respondent_id': 'R2', 'date': '2026-09-01',
            'sleep_hours': None, 'stress': 4, 'activity_minutes': 15,
            'salty_food': '3 kali atau lebih', 'fruit': 'Tidak mengonsumsi buah', 'vegetable': '1 porsi',
            'caffeine': '2 gelas', 'smoked': 'Ya',
            'smoke_count': 5, 'medication': 'Ya',
            'sitting': '8–10 jam', 'activity_type': 'Jalan kaki untuk pergi bekerja',
        },
        {
            'respondent_id': 'R3', 'date': '2026-09-01',
            'sleep_hours': 6.0, 'stress': 3, 'activity_minutes': 60,
            'salty_food': '1 kali', 'fruit': '2 porsi', 'vegetable': '2 porsi',
            'caffeine': 'Tidak mengonsumsi', 'smoked': 'Tidak',
            'smoke_count': None, 'medication': 'Tidak',
            'sitting': 'Kurang dari 4 jam', 'activity_type': 'Pekerjaan fisik',
        },
    ])
    sessions = pd.DataFrame([
        # R1 has morning + evening valid sessions -> should average to 120.0 (1 daily row, not 2)
        {'respondent_id': 'R1', 'date': '2026-09-01', 'session': 'Pagi', 'sbp1': 118, 'dbp1': 78, 'sbp2': 118, 'dbp2': 78},
        {'respondent_id': 'R1', 'date': '2026-09-01', 'session': 'Malam', 'sbp1': 122, 'dbp1': 82, 'sbp2': 122, 'dbp2': 82},
        # R2 has 1 valid session + 1 pending_review session (sbp <= dbp) -> only valid counts
        {'respondent_id': 'R2', 'date': '2026-09-01', 'session': 'Pagi', 'sbp1': 140, 'dbp1': 90, 'sbp2': 140, 'dbp2': 90},
        {'respondent_id': 'R2', 'date': '2026-09-01', 'session': 'Malam', 'sbp1': 80, 'dbp1': 95, 'sbp2': None, 'dbp2': None},
        # R3 has only an incomplete unpaired session -> R3 stays in daily_panel with sbp_mean = NaN
        {'respondent_id': 'R3', 'date': '2026-09-01', 'session': 'Pagi', 'sbp1': 130, 'dbp1': None, 'sbp2': None, 'dbp2': None},
    ])
    return profiles, sessions, daily


def test_daily_panel_preserves_daily_grain_and_bp_policy_gate():
    profiles, sessions, daily = _sample_frames()
    panel, assessed = build_daily_bp_panel(sessions, daily, profiles)

    # Grain strictly 1 row per (respondent_id, date) — not duplicated by 2 sessions
    assert len(panel) == 3
    assert set(panel['respondent_id']) == {'R1', 'R2', 'R3'}

    r1 = panel.loc[panel['respondent_id'] == 'R1'].iloc[0]
    assert r1['sbp_mean'] == pytest.approx(120.0)
    assert r1['dbp_mean'] == pytest.approx(80.0)
    assert r1['valid_session_count'] == 2

    # Pending review session for R2 is excluded by bp_policy
    r2 = panel.loc[panel['respondent_id'] == 'R2'].iloc[0]
    assert r2['sbp_mean'] == pytest.approx(140.0)
    assert r2['valid_session_count'] == 1
    assert (assessed['review_status'] == 'pending_review').sum() == 2

    # R3 has no valid BP -> daily row preserved with sbp_mean = NA
    r3 = panel.loc[panel['respondent_id'] == 'R3'].iloc[0]
    assert pd.isna(r3['sbp_mean'])
    assert r3['valid_session_count'] == 0


def test_missing_values_never_coerced_to_zero_and_small_groups_flagged():
    profiles, sessions, daily = _sample_frames()
    report = build_risk_analysis_report(profiles, sessions, daily, source_kind='synthetic')

    assert report['is_causal'] is False
    assert report['is_diagnosis'] is False
    assert report['grain'] == 'ID x tanggal'

    missing_by_field = {row['field']: row for row in report['missing_summary']['fields']}
    # R2 has missing sleep_hours; R1 and R3 have missing smoke_count -> preserved, not 0
    assert missing_by_field['sleep_hours']['missing_count'] == 1
    assert missing_by_field['smoke_count']['missing_count'] == 2
    assert set(ALL_RISK_FIELDS).issubset(missing_by_field.keys())

    # Categorical groups exclude rows where SBP is missing (R3) and flag small groups
    salty_groups = report['category_associations']['salty_food']['groups']
    assert sum(g['n'] for g in salty_groups) == 2  # only R1 and R2 have valid SBP
    assert all(g['small_group'] is True for g in salty_groups)


def test_numeric_correlations_return_none_when_fewer_than_three_pairs_or_constant():
    profiles, sessions, daily = _sample_frames()
    panel, _ = build_daily_bp_panel(sessions, daily, profiles)

    # Only 2 valid SBP rows -> n < 3 -> pearson_r & spearman_r must be None
    num = {row['field']: row for row in summarize_numeric_associations(panel)}
    assert set(NUMERIC_RISK_FIELDS).issubset(num.keys())
    assert num['activity_minutes']['n'] == 2
    assert num['activity_minutes']['pearson_r'] is None
    assert num['activity_minutes']['spearman_r'] is None
    assert num['activity_minutes']['small_sample'] is True
    assert num['smoke_count']['n'] == 1
    assert num['smoke_count']['missing_factor_count'] == 2


def test_empty_frames_return_structured_empty_report():
    empty_profiles = pd.DataFrame(columns=['respondent_id', 'age'])
    empty_sessions = pd.DataFrame(columns=['respondent_id', 'date', 'session', 'sbp1', 'dbp1', 'sbp2', 'dbp2'])
    empty_daily = pd.DataFrame(columns=['respondent_id', 'date', *ALL_RISK_FIELDS])

    report = build_risk_analysis_report(empty_profiles, empty_sessions, empty_daily, source_kind='empty')
    assert report['empty'] is True
    assert report['is_causal'] is False
    assert report['is_diagnosis'] is False
    assert report['sample_summary']['daily_records'] == 0
    assert report['sample_summary']['valid_sessions'] == 0
    assert report['stress_levels'] == []
    assert report['age_group_bp'] == []


def test_synthetic_fixture_consistency_with_analytics_v2(prepared, loaded):
    """Cross-check risk_analysis output against the repository's CP2 synthetic fixture and /api/analytics."""
    profiles, daily, sessions, _ = prepared
    report = build_risk_analysis_report(profiles, sessions, daily, source_kind='synthetic')
    api_data = loaded.get('/api/analytics').json()

    assert report['empty'] is False
    assert report['sample_summary']['respondents'] == api_data['kpis']['respondents'] == 19
    assert report['sample_summary']['daily_records'] == api_data['kpis']['daily_records'] == 570
    assert report['sample_summary']['valid_sessions'] == api_data['kpis']['sessions'] == 1140

    missing_by_field = {row['field']: row for row in report['missing_summary']['fields']}
    assert missing_by_field['sleep_hours']['missing_count'] == api_data['filtered_quality']['missing_sleep_hours'] == 6
    assert missing_by_field['sitting']['missing_count'] == api_data['filtered_quality']['missing_sitting'] == 3
    assert missing_by_field['smoke_count']['missing_count'] == api_data['filtered_quality']['missing_smoke_count'] == 550

    for field in CATEGORY_RISK_FIELDS:
        cat_info = report['category_associations'][field]
        assert cat_info['valid_n'] == sum(g['n'] for g in cat_info['groups'])
        api_groups = {g['category']: g for g in api_data['categories'][field]}
        for group in cat_info['groups']:
            assert group['n'] == api_groups[group['category']]['n']
            assert group['respondents'] == api_groups[group['category']]['respondents']
            assert group['sbp_mean'] == api_groups[group['category']]['sbp']

    num_by_field = {row['field']: row for row in report['numeric_associations']}
    api_corr = {row['field']: row for row in api_data['correlations']}
    for field in NUMERIC_RISK_FIELDS:
        assert num_by_field[field]['n'] == api_corr[field]['n']
        assert num_by_field[field]['respondents'] == api_corr[field]['respondents']
        assert num_by_field[field]['pearson_r'] == pytest.approx(api_corr[field]['r'], abs=1e-4)

    # Matches documented CP2 EDA finding: activity_minutes ~ -0.012, sleep_hours ~ 0.059
    assert num_by_field['activity_minutes']['pearson_r'] == pytest.approx(-0.012, abs=0.002)
    assert num_by_field['sleep_hours']['pearson_r'] == pytest.approx(0.059, abs=0.002)
    assert num_by_field['stress']['n'] == 570
    assert len(report['stress_levels']) == 5
