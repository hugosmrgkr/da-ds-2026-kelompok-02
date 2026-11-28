
"""Explicit CLI-only promotion. The web application never calls this module."""

from sqlalchemy import text

from .pipeline import load_warehouse, DataQualityError
from .warehouse_audit import audit_warehouse


def apply_validated(
    db,
    profiles,
    days,
    sessions,
    quality,
    *,
    kind,
    expected_current_hash=None,
    allow_source_change=False,
):
    if kind not in ("synthetic", "actual"):
        raise DataQualityError(
            "Jenis sumber harus synthetic atau actual"
        )

    # Untuk data aktual, bedakan issue yang bisa ditangani saat
    # preprocessing dengan masalah yang membutuhkan keputusan.
    if kind == "actual":
        issues = quality.get("issues", [])

        blocking_issues = [
            issue
            for issue in issues
            if issue.get("action") not in (
                "set_null",
                "retain_for_review",
            )
        ]

        uniqueness = quality.get("uniqueness", {})
        consistency = quality.get("consistency", {})

        integrity_problems = {
            name: value
            for name, value in {
                "profile_duplicate_excess": uniqueness.get(
                    "profile_duplicate_excess", 0
                ),
                "daily_duplicate_excess": uniqueness.get(
                    "daily_duplicate_excess", 0
                ),
                "clean_profile_duplicate_excess": uniqueness.get(
                    "clean_profile_duplicate_excess", 0
                ),
                "clean_daily_duplicate_excess": uniqueness.get(
                    "clean_daily_duplicate_excess", 0
                ),
                "unmatched_daily_rows": consistency.get(
                    "unmatched_daily_rows", 0
                ),
                "clean_unmatched_daily_rows": consistency.get(
                    "clean_unmatched_daily_rows", 0
                ),
            }.items()
            if value
        }

        rejected_profiles = quality.get("rejected_profiles", 0)
        rejected_daily = quality.get("rejected_daily", 0)

        flagged_sessions = quality.get(
            "pressure_anomalies", {}
        ).get("flagged_sessions", 0)

        if (
            rejected_profiles
            or rejected_daily
            or blocking_issues
            or integrity_problems
            or flagged_sessions
        ):
            details = []

            if rejected_profiles:
                details.append(
                    f"rejected_profiles={rejected_profiles}"
                )

            if rejected_daily:
                details.append(
                    f"rejected_daily={rejected_daily}"
                )

            if blocking_issues:
                details.append(
                    f"blocking_issues={len(blocking_issues)}"
                )

            if integrity_problems:
                details.append(
                    f"integrity_problems={integrity_problems}"
                )

            if flagged_sessions:
                details.append(
                    f"pressure_anomalies={flagged_sessions}"
                )

            raise DataQualityError(
                "Quality gate aktual: ditemukan masalah yang "
                "memerlukan pemeriksaan sebelum commit. "
                "Database tidak diubah. Detail: "
                + "; ".join(details)
            )

    # Mengunci proses promosi agar dua proses ETL tidak berjalan
    # bersamaan pada PostgreSQL.
    if db.bind.dialect.name == "postgresql":
        db.execute(
            text("SELECT pg_advisory_xact_lock(73421031)")
        )

    # Periksa kondisi warehouse sebelum mengganti data.
    current = audit_warehouse(db)

    occupied = any(
        current["counts"][name]
        for name in (
            "dim_participant_v2",
            "fact_daily_behavior_v2",
            "fact_bp_session_v2",
        )
    )

    if occupied and not expected_current_hash:
        raise DataQualityError(
            "Warehouse berisi data. Persetujuan manual diperlukan: "
            "periksa verify_warehouse lalu berikan "
            "--expected-current-hash."
        )

    if (
        expected_current_hash
        and expected_current_hash != current["natural_content_sha256"]
    ):
        raise DataQualityError(
            "Isi warehouse berbeda dari hash yang disetujui. "
            "Validasi ulang target sebelum menerapkan ETL."
        )

    if (
        occupied
        and current["source_kind"] != kind
        and not allow_source_change
    ):
        raise DataQualityError(
            "Pergantian jenis sumber memerlukan "
            "--allow-source-change secara eksplisit; "
            "data sintetis dan aktual tidak digabungkan."
        )

    # Simpan informasi jenis sumber pada metadata kualitas.
    validated_quality = {
        **quality,
        "source_kind": kind,
    }

    load_warehouse(
        db,
        profiles,
        days,
        sessions,
        validated_quality,
        source_name=(
            "Dua formulir sintetis CP2"
            if kind == "synthetic"
            else "Dua formulir aktual - akses terbatas"
        ),
        kind=kind,
    )

    return audit_warehouse(db)
