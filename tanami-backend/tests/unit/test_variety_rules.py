"""Post-rapat: varietas ditulis bebas, komoditas diturunkan dari nama."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from app.core.errors import ValidationError
from app.domain import commodity_from_variety
from app.schemas.farm import PlantCreate


@pytest.mark.parametrize(
    ("variety", "expected"),
    [
        ("Mangga Arumanis", "mango"),
        ("mangga harum manis", "mango"),
        ("Jeruk Siam", "citrus"),
        ("Stroberi Frigo", "strawberry"),
        ("  Stroberi Frigo  ", "strawberry"),
    ],
)
def test_commodity_diturunkan_dari_nama_varietas(variety: str, expected: str) -> None:
    assert commodity_from_variety(variety) == expected


def test_varietas_tidak_dikenal_ditolak() -> None:
    with pytest.raises(ValidationError):
        commodity_from_variety("Alpukat Mentega")


def test_create_plant_menerima_varietas_bebas_tanpa_commodity_code() -> None:
    payload = PlantCreate(
        label="Pohon Mangga",
        variety="Mangga Arumanis",
        nursery_started_at=date.today() - timedelta(days=10),
        placement="indoor",
    )
    assert "commodity_code" not in payload.model_dump()
    assert payload.variety == "Mangga Arumanis"
    assert payload.placement == "indoor"
    assert payload.derived_commodity == "mango"  # hasil turunan, bukan input
