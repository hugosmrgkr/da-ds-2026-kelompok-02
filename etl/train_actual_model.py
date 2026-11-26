"""CLI runner for Nahesson's actual-data readiness check & temporal release pipeline.

Never connects to the active PostgreSQL database and never modifies historical
CP3, P2, or Week 10 synthetic artifacts (`models/experiments/`, `models/tuning_week10/`,
`models/baseline_*`).

Usage (from project root):
    python -m etl.train_actual_model                 # Checks actual readiness + runs synthetic protocol dry-run
    python -m etl.train_actual_model --actual-only   # Evaluates actual data only (fails closed if missing/ineligible)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.app.actual_experiment import (
    ExperimentIneligibleError,
    run_actual_experiment,
    verify_release_package,
)
from backend.app.baseline import sha256

ROOT = Path(__file__).resolve().parents[1]


def legacy_artifact_hashes() -> dict[str, str]:
    """Snapshot SHA-256 hashes of CP3/P2/Week10 artifacts that must stay untouched."""
    models_dir = ROOT / 'models'
    if not models_dir.exists():
        return {}
    return {
        str(path.relative_to(ROOT)).replace('\\', '/'): sha256(path)
        for path in sorted(models_dir.rglob('*'))
        if path.is_file() and 'releases' not in path.parts
    }


def execute(*, run_synthetic_protocol: bool = True, actual_profiles: Path | None = None, actual_daily: Path | None = None) -> dict:
    """Check actual-data eligibility and optionally verify the release protocol on the synthetic fixture."""
    before_hashes = legacy_artifact_hashes()
    report_dir = ROOT / 'reports' / 'actual_model'
    release_root = ROOT / 'models' / 'releases'

    actual_prof = actual_profiles or (ROOT / 'data' / 'actual' / 'Data_Responden_Aktual.csv')
    actual_day = actual_daily or (ROOT / 'data' / 'actual' / 'Data_Harian_Aktual.csv')

    actual_status: dict
    try:
        actual_res = run_actual_experiment(
            actual_prof,
            actual_day,
            source_kind='actual',
            release_root=release_root,
            report_dir=report_dir / 'actual',
        )
        actual_status = {
            'eligible': True,
            'release_id': actual_res['release_id'],
            'run_id': actual_res['run_id'],
        }
    except ExperimentIneligibleError as exc:
        actual_status = {
            'eligible': False,
            'message': str(exc),
            'reasons': exc.reasons,
        }

    protocol_res = None
    if run_synthetic_protocol:
        protocol_res = run_actual_experiment(
            ROOT / 'data' / 'sample' / 'Data_Responden_Sintetis.csv',
            ROOT / 'data' / 'sample' / 'Data_Harian_Sintetis.csv',
            source_kind='synthetic',
            release_root=release_root,
            report_dir=report_dir / 'protocol_dry_run',
            release_id='synthetic-protocol-v1',
        )
        # Verify the written release package can be reloaded & passes hash/schema checks
        verify_release_package(release_root / protocol_res['release_id'])

    after_hashes = legacy_artifact_hashes()
    assert before_hashes == after_hashes, 'Artefak sintetis CP3/P2/Minggu 10 tidak boleh berubah!'

    summary = {
        'actual_status': actual_status,
        'protocol_dry_run': {
            'release_id': protocol_res['release_id'],
            'run_id': protocol_res['run_id'],
            'selected_model': protocol_res['metrics']['selected_model'],
            'beats_naive_on_validation': protocol_res['metrics']['selection']['beats_naive_on_validation'],
            'cv_strategy': protocol_res['metrics']['selection']['cv_strategy'],
        } if protocol_res else None,
        'legacy_artifacts_untouched': before_hashes == after_hashes,
        'legacy_artifact_count': len(before_hashes),
    }

    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / 'pipeline_summary.json').write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + '\n',
        encoding='utf-8',
        newline='\n',
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description='Actual-data eligibility check and release pipeline.')
    parser.add_argument('--actual-only', action='store_true', help='Skip synthetic protocol dry-run.')
    parser.add_argument('--profiles', type=Path, default=None, help='Path to actual profile CSV.')
    parser.add_argument('--daily', type=Path, default=None, help='Path to actual daily CSV.')
    args = parser.parse_args()

    result = execute(
        run_synthetic_protocol=not args.actual_only,
        actual_profiles=args.profiles,
        actual_daily=args.daily,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
