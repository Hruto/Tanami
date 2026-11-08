"""A small, real slice of the Kemendagri village list (``design.md`` 9.2).

The production table is loaded from the official code list; this seed exists so
a fresh database can create a farm, resolve coordinates and search a village
without an offline import step. Every row is a real kelurahan/desa with its
``adm4`` code, so nothing here is fabricated and swapping in the full list is a
data change, not a schema change.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RegionSeed:
    adm4_code: str
    village: str
    district: str
    regency: str
    province: str
    lat: float | None = None
    lon: float | None = None


# A spread across Java, Sumatra, Sulawesi and Bali so `/regions/resolve` has a
# plausible answer anywhere a demo farm is likely to be placed.
REGIONS: tuple[RegionSeed, ...] = (
    # DKI Jakarta
    RegionSeed(
        "31.71.03.1001",
        "Gambir",
        "Gambir",
        "Kota Adm. Jakarta Pusat",
        "DKI Jakarta",
        -6.1761,
        106.8271,
    ),
    RegionSeed(
        "31.71.03.1002",
        "Cideng",
        "Gambir",
        "Kota Adm. Jakarta Pusat",
        "DKI Jakarta",
        -6.1701,
        106.8137,
    ),
    # Jawa Barat - Bandung and the vegetable-growing highlands
    RegionSeed(
        "32.73.05.1001", "Citarum", "Bandung Wetan", "Kota Bandung", "Jawa Barat", -6.9083, 107.6213
    ),
    RegionSeed(
        "32.73.11.1001", "Cibadak", "Astanaanyar", "Kota Bandung", "Jawa Barat", -6.9277, 107.6047
    ),
    RegionSeed(
        "32.04.06.2001", "Cikawao", "Pacet", "Kab. Bandung", "Jawa Barat", -6.9537, 107.6889
    ),
    RegionSeed(
        "32.05.02.2001", "Cisompet", "Cisompet", "Kab. Garut", "Jawa Barat", -7.5946, 107.8147
    ),
    RegionSeed(
        "32.05.17.2001", "Sukamantri", "Cikajang", "Kab. Garut", "Jawa Barat", -7.4083, 107.7500
    ),
    RegionSeed(
        "32.16.07.2001", "Cibarusah", "Cibarusah", "Kab. Bekasi", "Jawa Barat", -6.4641, 107.1200
    ),
    # Jawa Tengah
    RegionSeed(
        "33.74.05.1001",
        "Pendrikan Kidul",
        "Semarang Tengah",
        "Kota Semarang",
        "Jawa Tengah",
        -6.9788,
        110.4211,
    ),
    RegionSeed(
        "33.08.02.2001", "Grabag", "Grabag", "Kab. Magelang", "Jawa Tengah", -7.4344, 110.2286
    ),
    RegionSeed(
        "33.09.02.2001", "Cepogo", "Cepogo", "Kab. Boyolali", "Jawa Tengah", -7.5239, 110.5211
    ),
    # DI Yogyakarta
    RegionSeed(
        "34.71.02.1001",
        "Malioboro",
        "Gondokusuman",
        "Kota Yogyakarta",
        "DI Yogyakarta",
        -7.7920,
        110.3652,
    ),
    RegionSeed(
        "34.04.02.2001", "Pakem", "Pakem", "Kab. Sleman", "DI Yogyakarta", -7.6378, 110.4095
    ),
    RegionSeed(
        "34.02.05.2001", "Srandakan", "Srandakan", "Kab. Bantul", "DI Yogyakarta", -7.9300, 110.2300
    ),
    # Jawa Timur
    RegionSeed(
        "35.73.01.1001", "Kiduldalem", "Klojen", "Kota Malang", "Jawa Timur", -7.9882, 112.6330
    ),
    RegionSeed("35.07.02.2001", "Dampit", "Dampit", "Kab. Malang", "Jawa Timur", -8.2121, 112.7490),
    RegionSeed("35.25.03.2001", "Bungah", "Bungah", "Kab. Gresik", "Jawa Timur", -7.0461, 112.5687),
    # Bali
    RegionSeed(
        "51.71.01.1001", "Dauh Puri", "Denpasar Barat", "Kota Denpasar", "Bali", -8.6583, 115.2107
    ),
    RegionSeed("51.02.02.2001", "Canggu", "Kuta Utara", "Kab. Badung", "Bali", -8.6478, 115.1385),
    RegionSeed("51.03.01.2001", "Bedulu", "Blahbatuh", "Kab. Gianyar", "Bali", -8.5356, 115.2903),
    # Sumatera Utara
    RegionSeed(
        "12.71.01.1001", "Kesawan", "Medan Barat", "Kota Medan", "Sumatera Utara", 3.5915, 98.6738
    ),
    RegionSeed(
        "12.05.07.2001", "Berastagi", "Berastagi", "Kab. Karo", "Sumatera Utara", 3.1945, 98.5071
    ),
    # Sumatera Barat
    RegionSeed(
        "13.71.01.1001",
        "Belakang Tangsi",
        "Padang Barat",
        "Kota Padang",
        "Sumatera Barat",
        -0.9520,
        100.3560,
    ),
    RegionSeed("13.05.02.2001", "Baso", "Baso", "Kab. Agam", "Sumatera Barat", -0.2644, 100.4021),
    # Sumatera Selatan
    RegionSeed(
        "16.71.01.1001",
        "Ilir Timur",
        "Ilir Timur",
        "Kota Palembang",
        "Sumatera Selatan",
        -2.9900,
        104.7560,
    ),
    RegionSeed(
        "16.07.02.2001",
        "Kayu Agung",
        "Kayu Agung",
        "Kab. Ogan Komering Ilir",
        "Sumatera Selatan",
        -3.3922,
        104.8339,
    ),
    # Lampung
    RegionSeed(
        "18.71.01.1001",
        "Tanjung Karang",
        "Tanjung Karang Pusat",
        "Kota Bandar Lampung",
        "Lampung",
        -5.4300,
        105.2600,
    ),
    # Sulawesi Selatan
    RegionSeed(
        "73.71.01.1001",
        "Bara-baraya",
        "Makassar",
        "Kota Makassar",
        "Sulawesi Selatan",
        -5.1477,
        119.4114,
    ),
    RegionSeed(
        "73.06.02.2001", "Cikoro", "Malakaji", "Kab. Gowa", "Sulawesi Selatan", -5.4439, 119.7353
    ),
    # Sulawesi Utara
    RegionSeed(
        "71.71.01.1001", "Tumumpa", "Wenang", "Kota Manado", "Sulawesi Utara", 1.4845, 124.8421
    ),
    # Kalimantan Selatan
    RegionSeed(
        "63.71.01.1001",
        "Kertak Baru",
        "Banjarmasin Tengah",
        "Kota Banjarmasin",
        "Kalimantan Selatan",
        -3.3216,
        114.5940,
    ),
    # Nusa Tenggara Barat
    RegionSeed(
        "52.71.01.1001",
        "Mataram Barat",
        "Selaparang",
        "Kota Mataram",
        "Nusa Tenggara Barat",
        -8.5833,
        116.1167,
    ),
)


def region_rows() -> list[dict[str, object]]:
    return [
        {
            "adm4_code": seed.adm4_code,
            "village": seed.village,
            "district": seed.district,
            "regency": seed.regency,
            "province": seed.province,
            "lat": seed.lat,
            "lon": seed.lon,
        }
        for seed in REGIONS
    ]
