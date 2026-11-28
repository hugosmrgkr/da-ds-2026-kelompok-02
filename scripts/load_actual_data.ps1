# Memuat DATA AKTUAL (data/private/incoming) ke database utama menggantikan data dummy.
# Langkah: cek file -> backup -> dry-run -> konfirmasi -> commit -> restart backend.
# Praproses (Makan/Tidak Makan, Makan Buah/Tidak Makan Buah, tidur dalam jam) dijalankan oleh
# backend/app/survey_schema.py saat langkah dry-run/commit ini.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    $profile = 'data/private/incoming/form_awal.csv'
    $daily   = 'data/private/incoming/catatan_harian.csv'
    foreach ($f in @($profile, $daily)) { if (-not (Test-Path $f)) { throw "File tidak ditemukan: $f" } }
    $dc = @('compose', '-p', 'tension-dashboard', '-f', 'compose.yaml')

    & docker @dc up -d --wait db
    & docker @dc build maintenance

    Write-Output '== 1/4 Backup database (data/private/backups, diabaikan Git) =='
    New-Item -ItemType Directory -Force data/private/backups | Out-Null
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $backup = "data/private/backups/toba_health_$stamp.dump"
    & docker @dc exec -T db sh -c 'pg_dump -U toba -d toba_health -Fc -f /tmp/backup.dump'
    if ($LASTEXITCODE -ne 0) { throw 'Backup gagal; proses dihentikan.' }
    & docker @dc cp db:/tmp/backup.dump $backup
    Write-Output "Backup: $backup"

    Write-Output '== 2/4 Dry-run validasi + praproses (tanpa mengubah database) =='
    & docker @dc run --rm --no-deps maintenance python -m etl.import_data --profile $profile --daily $daily --source-kind actual --dry-run --summary
    if ($LASTEXITCODE -ne 0) { throw 'Validasi gagal / batch ditolak. Database tidak diubah.' }

    $json = (& docker @dc run --rm --no-deps maintenance python -m etl.verify_warehouse) -join "`n"
    $hash = ($json | ConvertFrom-Json).natural_content_sha256

    $answer = Read-Host 'Ganti isi warehouse dengan DATA AKTUAL? Ketik YA untuk lanjut'
    if ($answer -ne 'YA') { Write-Output 'Dibatalkan. Database tidak diubah.'; return }

    Write-Output '== 3/4 Commit ETL =='
    & docker @dc run --rm --no-deps maintenance python -m etl.import_data --profile $profile --daily $daily --source-kind actual --commit --expected-current-hash $hash --allow-source-change --summary
    if ($LASTEXITCODE -ne 0) { throw 'Commit ditolak quality gate. Database tidak diubah.' }

    Write-Output '== 4/4 Build ulang & restart backend + frontend (kode baru) =='
    & docker @dc up -d --build --wait backend frontend
    Write-Output 'Selesai. Pastikan .env berisi ALLOW_ACTUAL_DATA_VIEW=true lalu buka http://127.0.0.1:8080'
} finally { Pop-Location }