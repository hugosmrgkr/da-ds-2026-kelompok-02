"""Automated tests for etl/export_publication_evidence.py.

Place this file at: backend/tests/test_publication_evidence.py
Run from the repository root:
    python -m pytest backend/tests/test_publication_evidence.py -q
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any

import pytest


# Make the repository root importable when pytest is launched from different
# working directories or when backend/tests/conftest.py changes sys.path.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from etl import export_publication_evidence as evidence  # noqa: E402


@pytest.fixture
def evidence_bundle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Create an isolated, internally consistent set of evidence files."""
    root = tmp_path
    reports_dir = root / "reports" / "week10_evaluation"
    models_dir = root / "models" / "tuning_week10"
    data_dir = root / "data"
    reports_dir.mkdir(parents=True)
    models_dir.mkdir(parents=True)
    data_dir.mkdir(parents=True)

    input_file = data_dir / "predictions.csv"
    input_file.write_text("actual,predicted\n10,11\n12,13\n", encoding="utf-8")

    model_file = models_dir / "selected_model.joblib"
    model_file.write_bytes(b"test-model-binary-v1")

    tuning = {
        "run_id": "test-run-001",
        "target": "target_example",
        "is_synthetic": True,
        "is_diagnosis": False,
        "real_model_validated": False,
        "promoted_to_serving": False,
        "target_approved": False,
        "limitation": "Data pengujian dibuat untuk kebutuhan pengujian otomatis.",
    }
    tuning_file = models_dir / "tuning_metrics.json"
    tuning_file.write_text(json.dumps(tuning, indent=2) + "\n", encoding="utf-8")

    summary = [
        {
            "model": "Naive 7-day mean",
            "stage": "historical_test",
            "split": "test",
            "mae": 1.25,
            "rmse": 1.5,
            "r2": 0.75,
            "n": 2,
        },
        {
            "model": "Linear Regression",
            "stage": "historical_test",
            "split": "test",
            "mae": 2.5,
            "rmse": 3.0,
            "r2": 0.5,
            "n": 2,
        },
    ]
    evaluation = {
        "run_id": "test-run-001",
        "summary": summary,
        "input_hashes": {
            "data/predictions.csv": evidence.text_sha256(input_file),
        },
    }
    evaluation_file = reports_dir / "evaluation.json"
    evaluation_file.write_text(json.dumps(evaluation, indent=2) + "\n", encoding="utf-8")

    manifest = {
        "run_id": "test-run-001",
        "metrics_hash_mode": evidence.EXPECTED_HASH_MODE,
        "metrics_sha256": evidence.text_sha256(tuning_file),
        "model_file": model_file.name,
        "model_sha256": evidence.file_sha256(model_file),
    }
    manifest_file = models_dir / "tuning_manifest.json"
    manifest_file.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    # Point the production module at this temporary fixture, never at the
    # project's real evaluation artifacts.
    monkeypatch.setattr(evidence, "ROOT", root)
    monkeypatch.setattr(evidence, "EVALUATION_FILE", evaluation_file)
    monkeypatch.setattr(evidence, "TUNING_FILE", tuning_file)
    monkeypatch.setattr(evidence, "MANIFEST_FILE", manifest_file)

    return {
        "root": root,
        "evaluation": evaluation,
        "tuning": tuning,
        "manifest": manifest,
        "evaluation_file": evaluation_file,
        "tuning_file": tuning_file,
        "manifest_file": manifest_file,
        "model_file": model_file,
        "input_file": input_file,
        "summary": summary,
    }


def test_verify_sources_accepts_matching_hashes_and_run_ids(evidence_bundle: dict[str, Any]) -> None:
    errors, verified_sources = evidence.verify_sources(
        evidence_bundle["evaluation"],
        evidence_bundle["tuning"],
        evidence_bundle["manifest"],
    )

    assert errors == []
    assert len(verified_sources) == 3
    assert "models/tuning_week10/tuning_metrics.json" in verified_sources
    assert "models/tuning_week10/selected_model.joblib" in verified_sources
    assert "data/predictions.csv" in verified_sources


def test_verify_sources_rejects_tampered_tuning_metrics(evidence_bundle: dict[str, Any]) -> None:
    tuning_file = evidence_bundle["tuning_file"]
    tuning_file.write_text(tuning_file.read_text(encoding="utf-8") + " ", encoding="utf-8")

    errors, _ = evidence.verify_sources(
        evidence_bundle["evaluation"],
        evidence_bundle["tuning"],
        evidence_bundle["manifest"],
    )

    assert any("Hash tuning_metrics.json tidak cocok" in error for error in errors)


def test_verify_sources_rejects_tampered_model_binary(evidence_bundle: dict[str, Any]) -> None:
    evidence_bundle["model_file"].write_bytes(b"tampered-model-binary")

    errors, _ = evidence.verify_sources(
        evidence_bundle["evaluation"],
        evidence_bundle["tuning"],
        evidence_bundle["manifest"],
    )

    assert any("Hash selected model tidak cocok" in error for error in errors)


def test_verify_sources_rejects_tampered_evaluation_input(evidence_bundle: dict[str, Any]) -> None:
    evidence_bundle["input_file"].write_text("actual,predicted\n10,99\n", encoding="utf-8")

    errors, _ = evidence.verify_sources(
        evidence_bundle["evaluation"],
        evidence_bundle["tuning"],
        evidence_bundle["manifest"],
    )

    assert any("Hash sumber tidak cocok: data/predictions.csv" in error for error in errors)


def test_verify_sources_rejects_mismatched_run_id(evidence_bundle: dict[str, Any]) -> None:
    evaluation = dict(evidence_bundle["evaluation"])
    evaluation["run_id"] = "different-run"

    errors, _ = evidence.verify_sources(
        evaluation,
        evidence_bundle["tuning"],
        evidence_bundle["manifest"],
    )

    assert any("run_id tidak konsisten" in error for error in errors)


def test_verify_sources_rejects_model_path_traversal(evidence_bundle: dict[str, Any]) -> None:
    manifest = dict(evidence_bundle["manifest"])
    manifest["model_file"] = "../../outside.joblib"

    errors, _ = evidence.verify_sources(
        evidence_bundle["evaluation"],
        evidence_bundle["tuning"],
        manifest,
    )

    assert any("model_file" in error and "tidak valid" in error for error in errors)


@pytest.mark.parametrize(
    ("field", "value", "expected_message"),
    [
        ("mae", float("nan"), "bukan angka finite"),
        ("rmse", float("inf"), "bukan angka finite"),
        ("r2", "0.75", "bukan angka finite"),
        ("n", -1, "tidak boleh negatif"),
        ("n", True, "bukan angka finite"),
    ],
)
def test_verify_sources_rejects_invalid_summary_values(
    evidence_bundle: dict[str, Any],
    field: str,
    value: Any,
    expected_message: str,
) -> None:
    evaluation = json.loads(json.dumps(evidence_bundle["evaluation"]))
    evaluation["summary"][0][field] = value

    errors, _ = evidence.verify_sources(
        evaluation,
        evidence_bundle["tuning"],
        evidence_bundle["manifest"],
    )

    assert any(expected_message in error for error in errors)


def test_export_csv_writes_expected_columns_and_metric_values(
    evidence_bundle: dict[str, Any], tmp_path: Path
) -> None:
    output = evidence.export_csv(evidence_bundle["summary"], output_dir=tmp_path)

    with output.open("r", encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))

    assert output.name == "model_metrics.csv"
    assert list(rows[0].keys()) == list(evidence.METRIC_FIELDS)
    assert len(rows) == 2
    assert rows[0]["model"] == "Naive 7-day mean"
    assert rows[0]["mae"] == "1.25"
    assert rows[1]["model"] == "Linear Regression"


def test_export_markdown_contains_metrics_and_limitations(
    evidence_bundle: dict[str, Any], tmp_path: Path
) -> None:
    output = evidence.export_markdown(
        evidence_bundle["evaluation"], evidence_bundle["tuning"], output_dir=tmp_path
    )
    content = output.read_text(encoding="utf-8")

    assert "# Ringkasan Hasil Evaluasi Model" in content
    assert "test-run-001" in content
    assert "Naive 7-day mean" in content
    assert "1.2500" in content
    assert "Data yang digunakan bersifat sintetis/simulasi" in content
    assert "bukan klaim bahwa model terbaik" in content


def test_export_provenance_records_verified_sources_and_caveats(
    evidence_bundle: dict[str, Any], tmp_path: Path
) -> None:
    errors, verified_sources = evidence.verify_sources(
        evidence_bundle["evaluation"],
        evidence_bundle["tuning"],
        evidence_bundle["manifest"],
    )
    assert errors == []

    output = evidence.export_provenance(
        evidence_bundle["evaluation"],
        evidence_bundle["tuning"],
        evidence_bundle["manifest"],
        verified_sources,
        output_dir=tmp_path,
    )
    provenance = json.loads(output.read_text(encoding="utf-8"))

    assert provenance["integrity_status"] == "VALID"
    assert provenance["run_id"] == "test-run-001"
    assert provenance["selected_model"] == "selected_model.joblib"
    assert provenance["selected_model_promoted_to_serving"] is False
    assert provenance["evaluation_rows"] == 2
    assert len(provenance["verified_source_sha256"]) == 3
    assert any("Data yang digunakan bersifat sintetis" in item for item in provenance["limitations"])


def test_hash_functions_follow_text_and_binary_hash_rules(tmp_path: Path) -> None:
    text_file = tmp_path / "windows-lines.txt"
    text_file.write_bytes(b"first\r\nsecond\r\n")
    normalized_file = tmp_path / "unix-lines.txt"
    normalized_file.write_bytes(b"first\nsecond\n")

    binary_file = tmp_path / "model.bin"
    binary_file.write_bytes(b"\x00\xff\x10\x80")

    assert evidence.text_sha256(text_file) == evidence.text_sha256(normalized_file)
    assert evidence.file_sha256(binary_file) != evidence.text_sha256(text_file)


def test_main_check_only_does_not_create_export_files(
    evidence_bundle: dict[str, Any], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output_dir = tmp_path / "publication_evidence"
    monkeypatch.setattr(evidence, "OUTPUT_DIR", output_dir)
    monkeypatch.setattr(sys, "argv", ["export_publication_evidence.py", "--check-only"])

    exit_code = evidence.main()

    assert exit_code == 0
    assert not output_dir.exists()
