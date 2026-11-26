"""CP2 field contracts. Index refers to the original, verified survey header order.

Categories describe this questionnaire/fixture contract, not clinical definitions.
Free-text answers are retained only where the questionnaire permits them.
"""
import re
from datetime import datetime, date


FRUIT_NO = "Tidak makan buah"
FRUIT_YES = "Makan buah"
# Kontrak CSV sintetis lama tetap utuh agar fingerprint/artefak model sintetis tidak berubah.
FRUIT_SYNTHETIC = ["Tidak mengonsumsi buah", "1 porsi", "2 porsi", "3 porsi atau lebih"]

# Pertanyaan asin/olahan (soal 21) menggabungkan dua jenis makanan berbeda ("makanan asin ATAU
# makanan olahan") dalam satu hitungan frekuensi, sehingga angka 1/2/3 kali tidak bisa dipastikan
# mengacu ke jenis yang mana. Tim memutuskan data AKTUAL disederhanakan jadi biner. Label
# menyebutkan "asin/olahan" secara eksplisit (bukan sekadar "Makan"/"Tidak Makan") karena frasa
# generik itu bisa disalahpahami sebagai "makan apa pun hari ini", padahal soalnya spesifik
# tentang makanan asin/olahan.
SALTY_NO = "Tidak mengonsumsi asin/olahan"
SALTY_YES = "Mengonsumsi asin/olahan"
# Kontrak CSV sintetis lama tetap utuh agar fingerprint/artefak model sintetis tidak berubah.
SALTY_SYNTHETIC = ["Tidak sama sekali", "1 kali", "2 kali", "3 kali atau lebih"]
_NUMBER_WORDS = ("satu", "dua", "tiga", "empat", "lima", "enam", "tujuh", "delapan", "sembilan", "sepuluh")


def field(technical, kind="text", unit="—", bounds=None, categories=(), max_length=None, note=""):
    return dict(technical=technical, kind=kind, unit=unit, bounds=bounds,
                categories=list(categories), max_length=max_length, note=note)


YES_NO = ["Ya", "Tidak"]
CONDITION_NAMES = ["diagnosed_bp", "bp_medication", "diabetes", "kidney", "cholesterol",
                   "heart", "stroke", "mother_bp", "father_bp", "family_diabetes", "family_heart"]
CONTEXT = ["Berolahraga", "Tidak ada kegiatan di atas", "Minum kopi, teh, atau minuman berkafein", "Merokok"]
ACTIVITIES = ["Tidak melakukan aktivitas fisik atau olahraga hari ini",
              "Jalan kaki untuk pergi bekerja, sekolah, berbelanja, atau keperluan lain",
              "Pekerjaan fisik, seperti bertani, mengangkat barang, atau pekerjaan lapangan",
              "Latihan kekuatan atau angkat beban", "Pekerjaan rumah atau berkebun, seperti menyapu, mengepel, atau mencangkul",
              "Jalan kaki untuk olahraga", "Jogging atau lari", "Senam atau aerobik",
              "Olahraga permainan, seperti bulu tangkis, sepak bola, atau bola voli", "Bersepeda", "Aktivitas lainnya"]

PROFILE_FIELDS = [
    field("submitted_at", "timestamp", note="Metadata audit; bukan tanggal pengamatan; tidak dimuat ke dimensi."),
    field("respondent_id", "id", max_length=40, note="Wajib; tidak membuat ID otomatis atau mengubah digit ID."),
    field("direct_identity", "excluded", note="Nama tidak dimuat, tidak disalin ke laporan atau dataset analitik."),
    field("age", "integer", "tahun", [0, 120], note="Rentang teknis; kriteria inklusi penelitian belum final."),
    field("gender", "category", categories=["Laki-laki", "Perempuan"], max_length=35),
    field("province", max_length=100, note="Teks lokasi; belum ada registry wilayah untuk verifikasi geografis."),
    field("city", max_length=100, note="Kabupaten/kota, bukan kecamatan; ejaan tidak ditebak."),
    field("occupation", max_length=220, note="Pilihan/teks lain dari formulir; dipertahankan, bukan enum tebakan."),
    field("education", max_length=150, note="Pilihan/teks lain dari formulir; dipertahankan."),
    *[field(name, "category", categories=YES_NO, note="Disimpan sebagai kunci conditions_json; kosong bukan Tidak.") for name in CONDITION_NAMES],
    field("height_cm", "number", "cm", [80, 250]),
    field("weight_kg", "number", "kg", [15, 300]),
    field("usual_activity", note="Multi-pilihan utuh; jangan split koma karena label juga mengandung koma."),
    field("active_days_week", "integer", "hari/minggu", [0, 7]),
]
DAILY_FIELDS = [
    field("submitted_at", "timestamp", note="Metadata audit saja; tidak menggantikan tanggal pengamatan."),
    field("respondent_id", "id", max_length=40, note="Wajib cocok dengan profil diterima."),
    field("date", "date", note="Tanggal ISO atau DD/MM/YYYY eksplisit; pasangan ID-tanggal unik."),
]
for prefix in ("morning", "evening"):
    DAILY_FIELDS.extend([
        field(prefix + "_time", "time", "HH:MM[:SS]", note="Waktu lokal pengukuran; tidak disamakan dengan durasi."),
        field(prefix + "_sbp1", "number", "mmHg", [60, 260]),
        field(prefix + "_dbp1", "number", "mmHg", [35, 170]),
        field(prefix + "_sbp2", "number", "mmHg", [60, 260]),
        field(prefix + "_dbp2", "number", "mmHg", [35, 170]),
        field(prefix + "_context", "open_category", categories=CONTEXT, max_length=220),
    ])
DAILY_FIELDS.extend([
    field("activity_type", "open_category", categories=ACTIVITIES),
    field("activity_minutes", "integer", "menit", [0, 1440]),
    field("heavy_minutes", "integer", "menit", [0, 1440]),
    field("sitting", "category", categories=["Kurang dari 4 jam", "4–7 jam", "8–10 jam", "Lebih dari 10 jam"], max_length=90),
    field("sleep_hours", "sleep", "jam", [0, 18], note="HH:MM sebagai durasi hanya untuk simulasi. Data aktual tetap NA sampai definisi disetujui."),
    field("salty_food", "binary_salty", categories=[SALTY_NO, SALTY_YES], max_length=90,
          note="Data AKTUAL (bukan sintetis): soal 21 menggabungkan asin dan olahan dalam satu "
               "frekuensi, jadi jumlah pasti tidak dipakai; '1/2/3 kali atau lebih' = Mengonsumsi "
               "asin/olahan, 'Tidak sama sekali' = Tidak mengonsumsi asin/olahan. Jawaban di luar "
               "4 pilihan formulir tidak ditebak."),
    field("fruit", "binary_fruit", categories=[FRUIT_NO, FRUIT_YES], max_length=90,
          note="Data AKTUAL (bukan sintetis): keputusan tim, jawaban bernilai (1 porsi, 2, dua, satu, dst.) = Makan buah; kosong, 0, '-' atau 'tidak' = Tidak makan buah."),
    field("vegetable", "category", categories=["Tidak mengonsumsi sayur", "1 porsi", "2 porsi", "3 porsi atau lebih"], max_length=90),
    field("caffeine", "category", categories=["Tidak mengonsumsi", "1 gelas", "2 gelas", "3 gelas atau lebih"], max_length=90),
    field("smoked", "category", categories=["Ya", "Tidak", "Tidak berlaku karena saya tidak merokok"], max_length=110),
    field("smoke_count", "integer", "kali/hari (sesuai pertanyaan, bukan otomatis batang)", [0, 100], note="Kosong tetap NA, termasuk tidak berlaku; tidak diisi nol otomatis."),
    field("medication", "category", categories=["Ya", "Tidak", "Saya tidak menggunakan obat tekanan darah"], max_length=180),
    field("stress", "stress", "skor", [1, 5], note="Terima integer 1–5 atau label persis formulir."),
])


def text(value):
    if value is None:
        return None
    s = str(value).strip()
    return None if s.casefold() in ("", "nan", "none", "nat", "<na>") else s


def parse_numeric(value, unit=None, bounds=None, integer=False):
    s = text(value)
    if s is None:
        return None
    suffix = {"tahun": "tahun", "cm": "cm", "kg": "kg", "menit": "menit", "hari/minggu": "hari"}.get(unit)
    pattern = r"(-?\d+(?:[.,]\d+)?)" + (r"\s*(?:" + suffix + r")?" if suffix else "")
    match = re.fullmatch(pattern, s, re.I)
    if not match:
        return None
    n = float(match.group(1).replace(",", "."))
    if bounds and not bounds[0] <= n <= bounds[1]:
        return None
    if integer and not n.is_integer():
        return None
    return int(n) if integer else n


def parse_fruit_binary(value):
    """Kelompokkan jawaban buah menjadi dua kategori: Makan buah / Tidak makan buah.

    Kosong, 0, '-' dan jawaban negatif -> Tidak makan buah. Angka/kata bilangan > 0
    (termasuk salah ketik seperti '1 prsi') -> Makan buah. Jawaban yang bertentangan
    atau tidak dikenali tidak ditebak: (None, 'invalid_category') agar masuk review.
    """
    s = text(value)
    if s is None:
        return FRUIT_NO, None
    n = re.sub(r"\s+", " ", s.casefold()).strip(" .")
    if re.fullmatch(r"[-\u2013\u2014_]+", n):
        return FRUIT_NO, None
    negative = bool(re.search(r"\b(tidak|tdk|tak|ga|gak|nggak|belum|nol)\b", n))
    number = re.search(r"-?\d+(?:[.,]\d+)?", n)
    positive = (float(number.group().replace(",", ".")) > 0) if number else bool(
        re.search(r"\b(" + "|".join(_NUMBER_WORDS) + r")\b", n))
    zero = bool(number) and float(number.group().replace(",", ".")) == 0
    if negative and positive:
        return None, "invalid_category"
    if negative or zero:
        return FRUIT_NO, None
    if positive:
        return FRUIT_YES, None
    return None, "invalid_category"


def parse_salty_binary(value):
    """Kelompokkan jawaban soal 21 (asin/olahan) menjadi dua kategori.

    Soal 21 adalah pilihan ganda tertutup (radio button), bukan teks bebas seperti buah, jadi
    jawaban aktual seharusnya persis salah satu dari empat label SALTY_SYNTHETIC. 'Tidak sama
    sekali' -> Tidak mengonsumsi asin/olahan; '1/2/3 kali atau lebih' -> Mengonsumsi asin/olahan.
    Jawaban di luar keempat pilihan itu tidak ditebak: (None, 'invalid_category') agar masuk
    review, bukan dipaksa masuk salah satu kelompok.
    """
    s = text(value)
    if s is None:
        return None, None
    canonical = {v.casefold(): v for v in SALTY_SYNTHETIC}.get(re.sub(r"\s+", " ", s).casefold())
    if canonical is None:
        return None, "invalid_category"
    return (SALTY_NO, None) if canonical == SALTY_SYNTHETIC[0] else (SALTY_YES, None)


def _binary_category_contract(kind):
    """(synthetic_labels, no_label, yes_label, parser) for a binary-coded daily field."""
    if kind == "binary_fruit":
        return FRUIT_SYNTHETIC, FRUIT_NO, FRUIT_YES, parse_fruit_binary
    if kind == "binary_salty":
        return SALTY_SYNTHETIC, SALTY_NO, SALTY_YES, parse_salty_binary
    return None


def parse_value(value, spec, synthetic):
    """Return (clean_value, issue_code). No raw free-text values enter issue reports.

    `synthetic` has no default on purpose: a caller that forgets to pass it would otherwise risk
    a field like `fruit`/`salty_food` silently being parsed with the wrong contract (synthetic's
    original multi-category labels instead of the actual-data binary grouping, or vice versa).
    Omitting it is now a TypeError at the call site instead of a silent mis-parse.
    """
    kind = spec["kind"]
    binary_contract = _binary_category_contract(kind)
    if binary_contract:
        synthetic_labels, _no_label, _yes_label, parser = binary_contract
        s = text(value)
        if spec["max_length"] and s is not None and len(s) > spec["max_length"]:
            return None, "text_too_long"
        if synthetic:  # fixture sintetis: label asli, tanpa pengelompokan
            canonical = {v.casefold(): v for v in synthetic_labels}.get(re.sub(r"\s+", " ", s or "").casefold())
            return (canonical, None) if canonical else (None, None if s is None else "invalid_category")
        return parser(value)
    s = text(value)
    if kind == "excluded":
        return None, None
    if s is None:
        return None, None
    if spec["max_length"] and len(s) > spec["max_length"]:
        return None, "text_too_long"
    if kind == "id" and any(character.isspace() or ord(character)<32 for character in s):
        return None,"invalid_id_control_or_whitespace"
    if kind in ("number", "integer"):
        n = parse_numeric(s, spec["unit"], spec["bounds"], kind == "integer")
        return n, None if n is not None else "invalid_number_or_unit"
    if kind in ("date", "timestamp"):
        try:
            # Explicit formats prevent month/day guessing and reject Excel serials.
            if re.match(r"^\d{4}-\d{2}-\d{2}(?:$|[ T])", s):
                dt = datetime.fromisoformat(s)
            else:
                dt = next((datetime.strptime(s, fmt) for fmt in
                           (["%d/%m/%Y", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M"])
                           if _matches_date(s, fmt)), None)
                if dt is None:
                    raise ValueError()
            return (dt.date() if kind == "date" else dt.isoformat()), None
        except (ValueError, TypeError):
            return None, "invalid_date_or_timestamp"
    if kind == "time":
        for fmt in ("%H:%M", "%H:%M:%S"):
            try:
                return datetime.strptime(s, fmt).strftime("%H:%M:%S"), None
            except ValueError:
                pass
        return None, "invalid_time"
    if kind == "sleep":
        if not synthetic:
            return None, "sleep_semantics_unconfirmed"
        if re.fullmatch(r"\d{1,2}:\d{2}", s):
            h, m = map(int, s.split(":"))
            duration = h + m / 60
            return (round(duration, 3), None) if m < 60 and 0 <= duration <= 18 else (None, "invalid_sleep_duration")
        n = parse_numeric(s, bounds=[0, 18])
        if n is not None and 0 < n < 1:
            return None, "ambiguous_excel_sleep_fraction"
        return n, None if n is not None else "invalid_sleep_duration"
    if kind == "stress":
        labels = {"1 = sangat rendah": 1, "2 = rendah": 2, "3 = sedang": 3, "4 = tinggi": 4, "5 = sangat tinggi": 5}
        n = labels.get(s.casefold())
        if n is None:
            n = parse_numeric(s, bounds=[1, 5], integer=True)
        return n, None if n is not None else "invalid_stress"
    if kind in ("category", "open_category"):
        normalized = re.sub(r"\s+", " ", s)
        # Known corrupted fixture labels only; never infer this repair for actual data.
        if synthetic and spec["technical"] == "sitting":
            normalized = {"4\ufffd7 jam": "4–7 jam", "8\ufffd10 jam": "8–10 jam",
                          "4-7 jam": "4–7 jam", "8-10 jam": "8–10 jam"}.get(normalized, normalized)
        canonical = {v.casefold(): v for v in spec["categories"]}.get(normalized.casefold())
        if canonical is not None:
            return canonical, None
        if kind == "open_category":
            return normalized, "unmapped_other_category_review"
        return None, "invalid_category"
    return s, None


def _matches_date(s, fmt):
    try:
        datetime.strptime(s, fmt)
        return True
    except ValueError:
        return False
