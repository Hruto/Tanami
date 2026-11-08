"""Reminder rules (design 12.3) - pure functions, no database."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

from app.domain import ReminderType
from app.providers.weather import WeatherDay, WeatherForecast, WeatherSlot
from app.services.reminder import (
    PlantContext,
    ReminderThresholds,
    build_scan_followups,
    build_weather_reminders,
    dedupe_key,
    is_fungal_risk,
    is_harvest_soon,
    is_heat_stress,
    is_heavy_rain_before_harvest,
    local_today,
)

T = ReminderThresholds()
TODAY = date(2026, 11, 7)
NOW = datetime(2026, 11, 7, 1, 0, tzinfo=UTC)  # 08:00 WIB


def slots(
    day: date, *, hu: float = 90, t: float = 27, desc: str = "Hujan Ringan", tp: float | None = None
) -> list[WeatherSlot]:
    return [
        WeatherSlot(
            local_datetime=f"{day.isoformat()} {hour:02d}:00:00",
            temperature_c=t,
            humidity_pct=hu,
            weather_desc=desc,
            wind_speed=5,
            wind_direction="TL",
            precipitation_mm=tp,
        )
        for hour in range(0, 24, 3)
    ]


def forecast(*days: list[WeatherSlot]) -> WeatherForecast:
    return WeatherForecast(
        adm4_code="31.71.03.1001",
        source="bmkg",
        fetched_at=NOW,
        days=[WeatherDay(date=day[0].local_datetime[:10], slots=day) for day in days],
    )


def three_days(**kwargs: object) -> WeatherForecast:
    return forecast(*(slots(TODAY + timedelta(days=i), **kwargs) for i in range(3)))  # type: ignore[arg-type]


def plant(**overrides: object) -> PlantContext:
    values: dict[str, object] = {
        "plant_id": uuid4(),
        "user_id": uuid4(),
        "farm_id": uuid4(),
        "label": "Cabai Blok A",
        "health_status": "healthy",
        "expected_harvest_min": None,
        "last_scan_at": NOW,
    }
    values.update(overrides)
    return PlantContext(**values)  # type: ignore[arg-type]


def test_fungal_risk_needs_48_humid_hours_with_rain() -> None:
    assert is_fungal_risk(three_days(hu=90, desc="Hujan Ringan"), T)


def test_fungal_risk_rejects_short_humid_spell() -> None:
    assert not is_fungal_risk(
        forecast(slots(TODAY, hu=95), slots(TODAY + timedelta(days=1), hu=60)), T
    )


def test_partly_cloudy_is_not_thick_cloud() -> None:
    assert not is_fungal_risk(three_days(hu=90, desc="Cerah Berawan"), T)
    assert is_fungal_risk(three_days(hu=90, desc="Berawan Tebal"), T)


def test_heat_stress_three_consecutive_slots() -> None:
    hot = slots(TODAY, t=36)
    assert is_heat_stress(forecast(hot), T)
    mixed = slots(TODAY, t=36)
    mixed[2] = WeatherSlot(mixed[2].local_datetime, 30, 80, "Cerah", 5, "TL")
    mixed[5] = WeatherSlot(mixed[5].local_datetime, 30, 80, "Cerah", 5, "TL")
    assert not is_heat_stress(forecast(mixed), T)


def test_heavy_rain_by_bmkg_wording_inside_window() -> None:
    fc = forecast(slots(TODAY, desc="Cerah"), slots(TODAY + timedelta(days=1), desc="Hujan Lebat"))
    assert is_heavy_rain_before_harvest(fc, TODAY + timedelta(days=2), T, today=TODAY)


def test_heavy_rain_after_harvest_start_does_not_count() -> None:
    fc = forecast(slots(TODAY, desc="Cerah"), slots(TODAY + timedelta(days=2), desc="Hujan Lebat"))
    assert not is_heavy_rain_before_harvest(fc, TODAY + timedelta(days=1), T, today=TODAY)


def test_heavy_rain_by_daily_precipitation_total() -> None:
    fc = forecast(slots(TODAY, desc="Hujan Sedang", tp=7.0))  # 8 slots x 7 mm = 56 mm
    assert is_heavy_rain_before_harvest(fc, TODAY, T, today=TODAY)
    light = forecast(slots(TODAY, desc="Hujan Ringan", tp=1.0))
    assert not is_heavy_rain_before_harvest(light, TODAY, T, today=TODAY)


def test_heavy_rain_ignores_far_harvest_and_wind() -> None:
    windy = forecast(slots(TODAY, desc="Berawan"))
    assert not is_heavy_rain_before_harvest(windy, TODAY + timedelta(days=1), T, today=TODAY)
    stormy = three_days(desc="Hujan Lebat")
    assert not is_heavy_rain_before_harvest(stormy, TODAY + timedelta(days=5), T, today=TODAY)


def test_harvest_soon_window() -> None:
    soon = plant(
        expected_harvest_min=TODAY + timedelta(days=2),
        expected_harvest_max=TODAY + timedelta(days=4),
    )
    assert is_harvest_soon(soon, T, today=TODAY)
    later = plant(expected_harvest_min=TODAY + timedelta(days=5))
    assert not is_harvest_soon(later, T, today=TODAY)


def test_stale_or_finished_estimate_stops_harvest_reminders() -> None:
    passed = plant(
        expected_harvest_min=TODAY - timedelta(days=9),
        expected_harvest_max=TODAY - timedelta(days=6),
    )
    assert not is_harvest_soon(passed, T, today=TODAY)
    finished = plant(expected_harvest_min=TODAY, growth_stage="finished")
    assert not is_harvest_soon(finished, T, today=TODAY)


def test_build_weather_reminders_types_priorities_and_keys() -> None:
    fungal_history = plant(
        had_fungal_issue=True,
        expected_harvest_min=TODAY + timedelta(days=1),
        expected_harvest_max=TODAY + timedelta(days=3),
    )
    fc = forecast(
        *(slots(TODAY + timedelta(days=i), hu=92, t=36, desc="Hujan Lebat") for i in range(3))
    )
    out = build_weather_reminders(
        plants=[fungal_history], forecast=fc, thresholds=T, now=NOW, today=TODAY
    )
    by_type = {item.type: item for item in out}
    assert set(by_type) == {
        ReminderType.FUNGAL_RISK,
        ReminderType.HARVEST_SOON,
        ReminderType.HEAVY_RAIN_HARVEST,
        ReminderType.HEAT_STRESS,
    }
    assert by_type[ReminderType.FUNGAL_RISK].priority.value == "high"
    assert by_type[ReminderType.HEAVY_RAIN_HARVEST].priority.value == "high"
    assert by_type[ReminderType.HARVEST_SOON].body.endswith("dalam 1-3 hari.")
    key = by_type[ReminderType.HEAT_STRESS].dedupe_key
    assert key == f"heat_stress:{fungal_history.plant_id}:2026-11-07"


def test_harvest_today_text() -> None:
    ready = plant(expected_harvest_min=TODAY, expected_harvest_max=TODAY)
    out = build_weather_reminders(
        plants=[ready],
        forecast=forecast(slots(TODAY, hu=50, desc="Cerah")),
        thresholds=T,
        now=NOW,
        today=TODAY,
    )
    assert [item.body for item in out] == ["Cabai Blok A diperkirakan sudah siap panen hari ini."]


def test_quiet_forecast_creates_nothing() -> None:
    fc = three_days(hu=60, desc="Cerah")
    assert (
        build_weather_reminders(plants=[plant()], forecast=fc, thresholds=T, now=NOW, today=TODAY)
        == []
    )


def test_scan_followup_after_five_days_for_sick_or_at_risk() -> None:
    sick = plant(health_status="sick", last_scan_at=NOW - timedelta(days=6))
    at_risk = plant(health_status="at_risk", last_scan_at=NOW - timedelta(days=5))
    recent = plant(health_status="sick", last_scan_at=NOW - timedelta(days=1))
    healthy = plant(health_status="healthy", last_scan_at=NOW - timedelta(days=30))
    out = build_scan_followups(
        plants=[sick, at_risk, recent, healthy], followup_days=5, now=NOW, today=TODAY
    )
    assert {item.plant_id for item in out} == {sick.plant_id, at_risk.plant_id}
    bodies = {item.plant_id: item.body for item in out}
    assert "terdeteksi sakit" in bodies[sick.plant_id]
    assert "perlu diperiksa ulang" in bodies[at_risk.plant_id]


def test_local_date_drives_dedupe_key() -> None:
    # 23:30 UTC is already the next day in WIB.
    late = datetime(2026, 11, 7, 23, 30, tzinfo=UTC)
    assert local_today(late, "Asia/Jakarta") == date(2026, 11, 8)
    assert dedupe_key(ReminderType.GENERAL, "x", date(2026, 11, 8)) == "general:x:2026-11-08"
