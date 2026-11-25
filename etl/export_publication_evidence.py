"""Export verifiable model-evaluation evidence for the Toba Health Insight project.

Place this file at: etl/export_publication_evidence.py
Run from the repository root:
    python etl/export_publication_evidence.py --check-only
    python etl/export_publication_evidence.py

The script does not train or modify models. It verifies the evaluation inputs,
Week 10 tuning metrics, and selected model artifact before exporting a compact
CSV, Markdown summary, and provenance JSON.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any


# This file is expected to live inside the repository's `etl/` directory.
ROOT = Path(__file__).resolve().parents[1]

EVALUATION_FILE = ROOT / "reports" / "week10_evaluation" / "evaluation.json"
TUNING_FILE = ROOT / "models" / "tuning_week10" / "tuning_metrics.json"
MANIFEST_FILE = ROOT / "models" / "tuning_week10" / "tuning_manifest.json"
OUTPUT_DIR = ROOT / "reports" / "publication_evidence"

METRIC_FIELDS = ("model", "stage", "split", "mae", "rmse", "r2", "n")
NUMERIC_FIELDS = ("mae", "rmse", "r2", "n")
EXPECTED_HASH_MODE = "utf8-lf-v1"


class EvidenceError(Exception):
    """Raised when an evidence source cannot be trusted or parsed."""


def relative_to_root(path: Path) -> str:
    """Return a repository-relative POSIX path for reports and provenance."""
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def load_json(path: Path) -> dict[str, Any]:
    """Read a JSON object and provide a useful error when it is invalid."""
    if not path.is_file():
        raise EvidenceError(f"File tidak ditemukan: {relative_to_root(path)}")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"JSON tidak valid: {relative_to_root(path)} ({exc})") from exc

    if not isinstance(data, dict):
        raise EvidenceError(f"Struktur JSON harus berupa object: {relative_to_root(path)}")
    return data


def text_sha256(path: Path) -> str:
    """Hash text files as UTF-8 after normalizing CRLF to LF.

    This follows the project's `utf8-lf-v1` hash convention. It is important
    for CSV/JSON files that may have different physical line endings on Windows.
    """
    raw = path.read_bytes()
    raw.decode("utf-8")  # Fail clearly if a supposedly-text source is not UTF-8.
    normalized = raw.replace(b"\r\n", b"\n")
    return hashlib.sha256(normalized).hexdigest()


def file_sha256(path: Path) -> str:
    """Hash a binary artifact without changing its bytes."""
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_model_path(model_name: Any) -> Path | None:
    """Resolve a manifest model filename without allowing path traversal."""
    if not isinstance(model_name, str) or not model_name.strip():
        return None

    # The manifest currently stores only a filename (e.g. selected_model.joblib).
    # Reject absolute paths, nested paths, and '..' segments.
    candidate = PurePosixPath(model_name.replace("\\", "/"))
    if candidate.is_absolute() or len(candidate.parts) != 1 or candidate.name in (".", ".."):
        return None

    return MANIFEST_FILE.parent / candidate.name


def _is_finite_number(value: Any) -> bool:
    """Check numeric JSON values while rejecting booleans and NaN/Infinity."""
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _validate_summary(summary: Any) -> list[str]:
    errors: list[str] = []

    if not isinstance(summary, list) or not summary:
        return ["evaluation.json tidak memiliki summary yang valid atau masih kosong."]

    for index, row in enumerate(summary, start=1):
        if not isinstance(row, dict):
            errors.append(f"Baris summary ke-{index} bukan object.")
            continue

        missing = [field for field in METRIC_FIELDS if field not in row]
        if missing:
            errors.append(
                f"Baris summary ke-{index} kehilangan kolom: {', '.join(missing)}."
            )
            continue

        for field in NUMERIC_FIELDS:
            if not _is_finite_number(row[field]):
                errors.append(
                    f"Nilai {field!r} pada baris summary ke-{index} bukan angka finite."
                )

        if _is_finite_number(row.get("n")) and float(row["n"]) < 0:
            errors.append(f"Nilai n pada baris summary ke-{index} tidak boleh negatif.")

    return errors


def verify_sources(
    evaluation: dict[str, Any],
    tuning: dict[str, Any],
    manifest: dict[str, Any],
) -> tuple[list[str], dict[str, str]]:
    """Verify run IDs and hashes for every source used in publication evidence.

    Returns a pair: (errors, verified_sources). The selected model is checked
    using a raw binary SHA-256; JSON/CSV inputs use the project's UTF-8/LF hash.
    """
    errors: list[str] = []
    verified_sources: dict[str, str] = {}

    # 1. All three artifacts must belong to the same experiment run.
    run_ids = [evaluation.get("run_id"), tuning.get("run_id"), manifest.get("run_id")]
    if any(not isinstance(run_id, str) or not run_id.strip() for run_id in run_ids):
        errors.append("run_id tidak ditemukan atau kosong pada salah satu sumber.")
    elif len(set(run_ids)) != 1:
        errors.append(
            "run_id tidak konsisten antara evaluation.json, tuning_metrics.json, "
            "dan tuning_manifest.json."
        )

    # 2. Verify the tuning metrics JSON against the model manifest.
    declared_hash_mode = manifest.get("metrics_hash_mode")
    if declared_hash_mode != EXPECTED_HASH_MODE:
        errors.append(
            f"Mode hash manifest tidak sesuai: {declared_hash_mode!r}; "
            f"seharusnya {EXPECTED_HASH_MODE!r}."
        )

    expected_tuning_hash = manifest.get("metrics_sha256")
    if not isinstance(expected_tuning_hash, str) or not expected_tuning_hash:
        errors.append("metrics_sha256 tidak tersedia pada tuning_manifest.json.")
    elif not TUNING_FILE.is_file():
        errors.append(f"File tuning metrics tidak ditemukan: {relative_to_root(TUNING_FILE)}")
    else:
        try:
            actual_tuning_hash = text_sha256(TUNING_FILE)
            if actual_tuning_hash != expected_tuning_hash:
                errors.append(
                    "Hash tuning_metrics.json tidak cocok dengan tuning_manifest.json."
                )
            else:
                verified_sources[relative_to_root(TUNING_FILE)] = actual_tuning_hash
        except (OSError, UnicodeDecodeError) as exc:
            errors.append(f"Gagal menghitung hash tuning_metrics.json: {exc}")

    # 3. Verify the selected model binary from the same manifest.
    model_path = _safe_model_path(manifest.get("model_file"))
    if model_path is None:
        errors.append("model_file pada tuning_manifest.json tidak valid.")
    elif not model_path.is_file():
        errors.append(f"File model tidak ditemukan: {relative_to_root(model_path)}")
    else:
        expected_model_hash = manifest.get("model_sha256")
        if not isinstance(expected_model_hash, str) or not expected_model_hash:
            errors.append("model_sha256 tidak tersedia pada tuning_manifest.json.")
        else:
            try:
                actual_model_hash = file_sha256(model_path)
                if actual_model_hash != expected_model_hash:
                    errors.append("Hash selected model tidak cocok dengan tuning_manifest.json.")
                else:
                    verified_sources[relative_to_root(model_path)] = actual_model_hash
            except OSError as exc:
                errors.append(f"Gagal menghitung hash file model: {exc}")

    # 4. Verify every source file listed by evaluation.json.
    input_hashes = evaluation.get("input_hashes")
    if not isinstance(input_hashes, dict) or not input_hashes:
        errors.append("evaluation.json tidak memiliki input_hashes yang valid.")
    else:
        for relative_path, expected_hash in input_hashes.items():
            if not isinstance(relative_path, str) or not relative_path.strip():
                errors.append("Ada path kosong/tidak valid pada input_hashes.")
                continue

            source_relative = Path(relative_path)
            if source_relative.is_absolute() or ".." in source_relative.parts:
                errors.append(f"Path sumber di luar repository ditolak: {relative_path}")
                continue

            source_path = ROOT / source_relative
            if not source_path.is_file():
                errors.append(f"File input evaluasi tidak ditemukan: {relative_path}")
                continue

            if not isinstance(expected_hash, str) or not expected_hash:
                errors.append(f"Hash sumber tidak valid untuk: {relative_path}")
                continue

            try:
                actual_hash = text_sha256(source_path)
            except (OSError, UnicodeDecodeError) as exc:
                errors.append(f"Gagal membaca sumber {relative_path}: {exc}")
                continue

            if actual_hash != expected_hash:
                errors.append(f"Hash sumber tidak cocok: {relative_path}")
            else:
                verified_sources[relative_path.replace("\\", "/")] = actual_hash

    # 5. Validate rows to prevent exporting malformed metrics.
    errors.extend(_validate_summary(evaluation.get("summary")))

    return errors, verified_sources


def _format_metric(value: Any, digits: int = 4) -> str:
    if not _is_finite_number(value):
        return "—"
    return f"{float(value):.{digits}f}"


def _markdown_table(summary: list[dict[str, Any]]) -> str:
    headers = ["Model", "Tahap", "Split", "MAE", "RMSE", "R²", "n"]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]

    for row in summary:
        values = [
            str(row["model"]).replace("|", "\\|"),
            str(row["stage"]).replace("|", "\\|"),
            str(row["split"]).replace("|", "\\|"),
            _format_metric(row["mae"]),
            _format_metric(row["rmse"]),
            _format_metric(row["r2"]),
            str(row["n"]),
        ]
        lines.append("| " + " | ".join(values) + " |")

    return "\n".join(lines)


def _collect_limitations(evaluation: dict[str, Any], tuning: dict[str, Any]) -> list[str]:
    """Collect documented limitations without inventing evaluation claims."""
    result: list[str] = []
    for source in (evaluation, tuning):
        value = source.get("limitation")
        if isinstance(value, str) and value.strip() and value.strip() not in result:
            result.append(value.strip())
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str) and item.strip() and item.strip() not in result:
                    result.append(item.strip())

        values = source.get("limitations")
        if isinstance(values, list):
            for item in values:
                if isinstance(item, str) and item.strip() and item.strip() not in result:
                    result.append(item.strip())

    # These caveats are explicitly part of the Week 10 evaluation context.
    standard_caveats = [
        "Data yang digunakan bersifat sintetis/simulasi, bukan data operasional nyata.",
        "Hasil ini bukan validasi klinis dan tidak digunakan untuk diagnosis medis.",
        "Hasil tuning Week 10 tidak otomatis berarti model dipromosikan ke model serving.",
    ]
    for item in standard_caveats:
        if item not in result:
            result.append(item)
    return result


def export_csv(summary: list[dict[str, Any]], output_dir: Path = OUTPUT_DIR) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "model_metrics.csv"

    with output_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=METRIC_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in summary:
            writer.writerow({field: row.get(field) for field in METRIC_FIELDS})

    return output_path


def export_markdown(
    evaluation: dict[str, Any],
    tuning: dict[str, Any],
    output_dir: Path = OUTPUT_DIR,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "results_summary.md"
    summary = evaluation["summary"]
    limitations = _collect_limitations(evaluation, tuning)

    lines = [
        "# Ringkasan Hasil Evaluasi Model",
        "",
        f"- **Run ID:** `{evaluation.get('run_id', 'tidak tersedia')}`",
        f"- **Target:** {tuning.get('target', 'tidak dicantumkan')} ",
        f"- **Data sintetis:** `{tuning.get('is_synthetic', 'tidak dicantumkan')}`",
        f"- **Dipromosikan ke serving:** `{tuning.get('promoted_to_serving', 'tidak dicantumkan')}`",
        "",
        "## Metrik evaluasi",
        "",
        _markdown_table(summary),
        "",
        "## Batasan interpretasi",
        "",
    ]
    lines.extend(f"- {item}" for item in limitations)
    lines.extend(
        [
            "",
            "## Catatan penggunaan",
            "",
            "Angka pada tabel diekspor langsung dari `evaluation.json`. File ini "
            "merupakan ringkasan bukti eksperimen, bukan klaim bahwa model terbaik "
            "mengungguli baseline atau siap digunakan pada layanan produksi.",
            "",
        ]
    )

    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def export_provenance(
    evaluation: dict[str, Any],
    tuning: dict[str, Any],
    manifest: dict[str, Any],
    verified_sources: dict[str, str],
    output_dir: Path = OUTPUT_DIR,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "provenance.json"

    model_name = manifest.get("model_file")
    provenance = {
        "schema_version": "1.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "run_id": evaluation.get("run_id"),
        "integrity_status": "VALID",
        "hash_convention": EXPECTED_HASH_MODE,
        "selected_model": model_name,
        "selected_model_promoted_to_serving": tuning.get("promoted_to_serving"),
        "target": tuning.get("target"),
        "is_synthetic": tuning.get("is_synthetic"),
        "is_diagnosis": tuning.get("is_diagnosis"),
        "real_model_validated": tuning.get("real_model_validated"),
        "target_approved": tuning.get("target_approved"),
        "verified_source_sha256": dict(sorted(verified_sources.items())),
        "evaluation_rows": len(evaluation.get("summary", [])),
        "limitations": _collect_limitations(evaluation, tuning),
    }

    output_path.write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verifikasi dan ekspor bukti evaluasi model untuk publikasi/laporan."
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Hanya memeriksa integritas sumber tanpa membuat file keluaran.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        evaluation = load_json(EVALUATION_FILE)
        tuning = load_json(TUNING_FILE)
        manifest = load_json(MANIFEST_FILE)
    except EvidenceError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    errors, verified_sources = verify_sources(evaluation, tuning, manifest)

    if errors:
        print("Status integritas: INVALID")
        for error in errors:
            print(f"- {error}")
        print("Tidak ada file keluaran yang dibuat.")
        return 1

    print(f"Run ID: {evaluation.get('run_id')}")
    print(f"Sumber terverifikasi: {len(verified_sources)}")
    print("Status integritas: VALID")

    if args.check_only:
        print("Mode pemeriksaan: tidak ada file yang dibuat.")
        return 0

    try:
        summary = evaluation["summary"]
        outputs = [
            export_csv(summary),
            export_markdown(evaluation, tuning),
            export_provenance(evaluation, tuning, manifest, verified_sources),
        ]
    except (OSError, KeyError, TypeError, ValueError) as exc:
        print(f"ERROR saat mengekspor bukti: {exc}", file=sys.stderr)
        return 1

    print("File berhasil diekspor:")
    for path in outputs:
        print(f"- {relative_to_root(path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
