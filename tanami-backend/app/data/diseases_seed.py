"""Reviewed disease knowledge base (``design.md`` 9.3, 11.5).

One row per class in the model's label set, for chili. The advice text is what
the app shows next to a scan result; the model never writes it (TQA 8.3).

Two editorial rules are enforced by the schema and repeated here so nobody adds
a row that breaks them:

* every active row needs ``reviewed_by`` and ``reviewed_at``,
* chemical treatments carry a safety note and **no dose**, because a dose would
  be a medical recommendation until an agronomist signs off on one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

COMMODITY = "chili"

# The review that signed off on this text. Bump both when the content changes.
REVIEWED_BY = "Tim Agronomi Tanami"
REVIEWED_AT = date(2026, 9, 1)

SAFETY_NOTE = (
    "Gunakan sarung tangan dan masker. Baca label kemasan dan ikuti dosis anjuran. "
    "Jangan mencampur beberapa bahan kimia tanpa panduan penyuluh."
)


@dataclass(frozen=True, slots=True)
class DiseaseSeed:
    code: str
    name_id: str
    cause_category: str
    symptoms: str
    causes_text: str
    prevention: str
    name_latin: str | None = None
    severity_note: str | None = None
    treatments: dict[str, Any] = field(default_factory=dict)


def _treatments(
    *,
    first_aid: list[str],
    organic: list[dict[str, str]],
    chemical: list[dict[str, str]] | None = None,
    when_to_call_expert: str,
) -> dict[str, Any]:
    return {
        "first_aid": first_aid,
        "organic": organic,
        "chemical": chemical or [],
        "safety_note": SAFETY_NOTE,
        "when_to_call_expert": when_to_call_expert,
    }


DISEASES: tuple[DiseaseSeed, ...] = (
    DiseaseSeed(
        code="healthy",
        name_id="Sehat",
        cause_category="healthy",
        symptoms=(
            "Daun berwarna hijau merata, tidak ada bercak, tidak menggulung, dan "
            "pertumbuhan tunas baru terlihat normal."
        ),
        causes_text=(
            "Tidak ada penyakit yang terdeteksi. Kondisi ini menunjukkan perawatan "
            "dan pemupukan yang cukup."
        ),
        prevention=(
            "Lanjutkan penyiraman pagi hari, pemupukan berimbang, dan pemeriksaan "
            "daun bagian bawah setiap minggu."
        ),
        treatments=_treatments(
            first_aid=["Tidak ada tindakan darurat yang diperlukan."],
            organic=[
                {
                    "title": "Perawatan rutin",
                    "how": "Bersihkan gulma di sekitar tanaman dan pertahankan mulsa.",
                }
            ],
            when_to_call_expert=(
                "Hubungi penyuluh bila muncul bercak atau daun menggulung yang tidak biasa."
            ),
        ),
    ),
    DiseaseSeed(
        code="anthracnose",
        name_id="Antraknosa",
        cause_category="fungus",
        name_latin="Colletotrichum spp.",
        symptoms=(
            "Bercak cokelat kehitaman yang melebar pada daun, batang, dan buah. Pada "
            "buah muncul lekukan basah yang lama-lama menghitam dan mengerut."
        ),
        causes_text=(
            "Infeksi jamur Colletotrichum yang menyebar lewat percikan air hujan, "
            "benih terinfeksi, dan sisa tanaman sakit. Kelembapan tinggi mempercepat "
            "penyebaran."
        ),
        prevention=(
            "Gunakan benih bersertifikat, rotasi tanaman, jangan menyiram dari atas, "
            "dan buang buah serta daun yang terinfeksi jauh dari lahan."
        ),
        severity_note="Paling merugikan saat menyerang buah menjelang panen.",
        treatments=_treatments(
            first_aid=[
                "Petik dan buang buah serta daun yang bergejala ke luar lahan.",
                "Hentikan penyiraman dari atas dan kurangi kelembapan kanopi.",
            ],
            organic=[
                {
                    "title": "Fungisida nabati",
                    "how": "Aplikasikan ekstrak tanaman sesuai petunjuk produk, ulangi "
                    "sesuai label.",
                },
                {
                    "title": "Perbaikan sirkulasi",
                    "how": "Pangkas daun bagian bawah agar kanopi tidak lembap.",
                },
            ],
            chemical=[
                {
                    "title": "Fungisida berbahan aktif golongan azol atau strobilurin",
                    "how": "Pilih satu produk, baca label, dan jangan melebihi dosis anjuran.",
                }
            ],
            when_to_call_expert=(
                "Bila gejala meluas lebih dari sepertiga tanaman atau menyerang buah "
                "yang hampir panen."
            ),
        ),
    ),
    DiseaseSeed(
        code="cercospora_leaf_spot",
        name_id="Bercak Daun Cercospora",
        cause_category="fungus",
        name_latin="Cercospora capsici",
        symptoms=(
            "Bercak bulat kecil berwarna cokelat dengan tepi lebih gelap dan pusat "
            "kelabu. Bercak tua dapat berlubang dan daun menguning lalu gugur."
        ),
        causes_text=(
            "Jamur Cercospora yang bertahan pada sisa tanaman dan menyebar lewat "
            "percikan air serta angin pada kondisi lembap."
        ),
        prevention=(
            "Rotasi dengan tanaman non-solanaceae, sanitasi sisa tanaman, jarak tanam "
            "yang cukup, dan hindari daun tetap basah sepanjang malam."
        ),
        severity_note="Menurunkan hasil lewat kehilangan daun bila dibiarkan.",
        treatments=_treatments(
            first_aid=[
                "Buang daun bergejala paling parah, mulai dari bagian bawah.",
                "Kurangi kelembapan dengan memperbaiki drainase.",
            ],
            organic=[
                {
                    "title": "Perbaikan jarak tanam",
                    "how": "Renggangkan kanopi agar daun cepat kering setelah hujan.",
                }
            ],
            chemical=[
                {
                    "title": "Fungisida kontak berbahan aktif tembaga atau mankozeb",
                    "how": "Ikuti label kemasan; aplikasikan pagi atau sore hari.",
                }
            ],
            when_to_call_expert=(
                "Bila bercak menyebar ke lebih dari separuh daun dalam satu minggu."
            ),
        ),
    ),
    DiseaseSeed(
        code="bacterial_wilt",
        name_id="Layu Bakteri",
        cause_category="bacteria",
        name_latin="Ralstonia solanacearum",
        symptoms=(
            "Daun layu mendadak meski tanah lembap, dimulai dari daun muda. Batang "
            "yang dipotong menunjukkan berkas pembuluh kecokelatan."
        ),
        causes_text=(
            "Bakteri tular tanah yang masuk lewat luka akar dan menyebar melalui air "
            "irigasi serta alat pertanian yang tidak disterilkan."
        ),
        prevention=(
            "Gunakan lahan bebas penyakit, rotasi, sterilisasi alat, dan hindari penggenangan air."
        ),
        severity_note="Tidak dapat disembuhkan; tanaman harus dipisahkan.",
        treatments=_treatments(
            first_aid=[
                "Cabut dan musnahkan tanaman yang layu; jangan dikompos.",
                "Sterilkan alat yang dipakai dengan alkohol atau air pemutih.",
            ],
            organic=[
                {
                    "title": "Perbaikan drainase",
                    "how": "Buat bedengan lebih tinggi agar air tidak menggenang.",
                }
            ],
            chemical=[],
            when_to_call_expert=(
                "Segera hubungi penyuluh: penyakit ini menular cepat dan tidak punya "
                "perlakuan kuratif."
            ),
        ),
    ),
    DiseaseSeed(
        code="leaf_curl_virus",
        name_id="Keriting Daun (Virus)",
        cause_category="virus",
        symptoms=(
            "Daun menggulung ke atas atau ke bawah, mengerut, dan berwarna belang. "
            "Pertumbuhan tanaman terhambat dan bunga mudah rontok."
        ),
        causes_text=(
            "Virus yang ditularkan serangga pengisap seperti kutu kebul dan thrips. "
            "Tanaman terinfeksi menjadi sumber penularan bagi tanaman lain."
        ),
        prevention=(
            "Kendalikan serangga penular, gunakan mulsa reflektif, dan cabut tanaman "
            "bergejala sejak awal."
        ),
        severity_note="Tanaman terinfeksi tidak pulih; kendalikan penularnya.",
        treatments=_treatments(
            first_aid=[
                "Cabut tanaman yang gejalanya berat agar tidak menular.",
                "Pasang perangkap kuning atau lekat di sekitar bedengan.",
            ],
            organic=[
                {
                    "title": "Pengendalian serangga penular",
                    "how": "Gunakan sabun insektisida atau minyak nimba sesuai label.",
                }
            ],
            chemical=[],
            when_to_call_expert=("Bila lebih dari seperempat tanaman menunjukkan gejala keriting."),
        ),
    ),
    DiseaseSeed(
        code="pest_damage",
        name_id="Kerusakan Akibat Hama",
        cause_category="pest",
        symptoms=(
            "Daun berlubang, menguning, atau berkerut di bagian yang terserap; "
            "kadang terlihat kutu halus di bawah daun atau bekas luka gigitan."
        ),
        causes_text=(
            "Serangan kutu daun, thrips, atau tungau yang mengisap cairan tanaman; "
            "populasinya meledak pada cuaca kering dan penggunaan insektisida tidak "
            "tepat."
        ),
        prevention=(
            "Periksa daun bagian bawah setiap minggu, tanam tanaman penarik hama, dan "
            "gunakan musuh alami."
        ),
        severity_note="Serangan berat membuat daun rontok dan menurunkan hasil.",
        treatments=_treatments(
            first_aid=[
                "Semprot air bertekanan ke bawah daun untuk menurunkan populasi.",
                "Pasang perangkap kuning lekat.",
            ],
            organic=[
                {
                    "title": "Minyak nimba atau sabun insektisida",
                    "how": "Aplikasikan sore hari dan ulangi sesuai label produk.",
                }
            ],
            chemical=[
                {
                    "title": "Insektisida selektif untuk kutu atau thrips",
                    "how": "Baca label, rotasi bahan aktif, dan hindari penyemprotan saat "
                    "tanaman berbunga penuh.",
                }
            ],
            when_to_call_expert=(
                "Bila populasi tidak turun dalam satu minggu atau serangan mencapai "
                "sepertiga tajuk."
            ),
        ),
    ),
    DiseaseSeed(
        code="nutrient_deficiency",
        name_id="Kekurangan Hara",
        cause_category="nutrient_deficiency",
        symptoms=(
            "Daun menguning merata atau di antara tulang daun, pertumbuhan kerdil, "
            "dan buah kecil. Umumnya mulai dari daun tua."
        ),
        causes_text=(
            "Pasokan hara tidak seimbang, pH tanah tidak sesuai, atau akar terganggu "
            "sehingga penyerapan hara terhambat."
        ),
        prevention=(
            "Pemupukan berimbang sesuai umur tanaman, uji tanah secara berkala, dan "
            "jaga kelembapan tanah agar hara tersedia."
        ),
        severity_note="Bukan penyakit menular; perbaikan lewat nutrisi.",
        treatments=_treatments(
            first_aid=[
                "Periksa apakah tanah terlalu basah atau terlalu kering.",
                "Tambahkan pupuk sesuai hasil uji tanah atau anjuran penyuluh.",
            ],
            organic=[
                {
                    "title": "Pupuk organik matang",
                    "how": "Aplikasikan kompos matang di sekitar perakaran, bukan di batang.",
                }
            ],
            chemical=[],
            when_to_call_expert=(
                "Bila gejala tidak membaik setelah perbaikan pemupukan dalam dua minggu."
            ),
        ),
    ),
)


def disease_rows() -> list[dict[str, Any]]:
    """The rows ``seed_diseases`` upserts, in a form the ORM accepts directly."""
    return [
        {
            "code": seed.code,
            "commodity_code": COMMODITY,
            "name_id": seed.name_id,
            "name_latin": seed.name_latin,
            "cause_category": seed.cause_category,
            "symptoms": seed.symptoms,
            "causes_text": seed.causes_text,
            "prevention": seed.prevention,
            "severity_note": seed.severity_note,
            "treatments": seed.treatments,
            "reviewed_by": REVIEWED_BY,
            "reviewed_at": REVIEWED_AT,
            "is_active": True,
        }
        for seed in DISEASES
    ]
