"""Tests for calendar/event tools."""

import json
from unittest.mock import MagicMock

from httpx import Response

from intervals_icu_mcp.tools.events import get_calendar_events, get_upcoming_workouts, get_event


async def test_get_calendar_events_handles_iso_datetime(mock_config, respx_mock):
    """Ensure get_calendar_events accepts full ISO datetimes (with time/Z) and date-only strings."""
    mock_ctx = MagicMock()
    mock_ctx.get_state.return_value = mock_config

    events_payload = [
        {
            "id": 1001,
            "start_date_local": "2025-10-14T08:00:00Z",
            "category": "WORKOUT",
            "name": "Threshold Intervals",
            "type": "Ride",
        },
        {
            "id": 1002,
            "start_date_local": "2025-10-15",
            "category": "NOTE",
            "name": "Note",
        },
    ]

    respx_mock.get("/athlete/i123456/events").mock(return_value=Response(200, json=events_payload))

    result = await get_calendar_events(ctx=mock_ctx)
    response = json.loads(result)

    assert "data" in response
    assert "events_by_date" in response["data"]
    assert "2025-10-14" in response["data"]["events_by_date"]
    assert response["data"]["summary"]["total_events"] == 2


async def test_get_upcoming_workouts_handles_iso_datetime(mock_config, respx_mock):
    """Ensure get_upcoming_workouts accepts ISO datetimes and returns workouts with normalized dates."""
    mock_ctx = MagicMock()
    mock_ctx.get_state.return_value = mock_config

    events_payload = [
        {
            "id": 2001,
            "start_date_local": "2025-11-01T06:30:00",
            "category": "WORKOUT",
            "name": "Easy Ride",
            "moving_time": 3600,
        },
        {
            "id": 2002,
            "start_date_local": "2025-11-03",
            "category": "WORKOUT",
            "name": "Long Run",
        },
    ]

    respx_mock.get("/athlete/i123456/events").mock(return_value=Response(200, json=events_payload))

    result = await get_upcoming_workouts(ctx=mock_ctx)
    response = json.loads(result)

    assert "data" in response
    assert "workouts" in response["data"]
    assert any(w["date"] == "2025-11-01" for w in response["data"]["workouts"]) is True
    assert any(w["date"] == "2025-11-03" for w in response["data"]["workouts"]) is True
    assert response["data"]["count"] == 2


async def test_various_datetime_formats_are_normalized_for_calendar_and_workouts(mock_config, respx_mock):
    """Ensure various ISO datetime variants are accepted and normalized to YYYY-MM-DD."""
    mock_ctx = MagicMock()
    mock_ctx.get_state.return_value = mock_config

    events_payload = [
        {
            "id": 3001,
            "start_date_local": "2025-12-01T08:00Z",
            "category": "WORKOUT",
            "name": "Zulu Ride",
        },
        {
            "id": 3002,
            "start_date_local": "2025-12-02T08:00:00.123Z",
            "category": "WORKOUT",
            "name": "Millis Ride",
        },
        {
            "id": 3003,
            "start_date_local": "2025-12-03T08:00+00:00",
            "category": "WORKOUT",
            "name": "Offset Ride",
        },
        {
            "id": 3004,
            "start_date_local": "2025-12-05",
            "category": "NOTE",
            "name": "Date-only Note",
        },
    ]

    respx_mock.get("/athlete/i123456/events").mock(return_value=Response(200, json=events_payload))

    # Calendar should group events by normalized date
    cal_result = await get_calendar_events(ctx=mock_ctx)
    cal_resp = json.loads(cal_result)
    assert "2025-12-01" in cal_resp["data"]["events_by_date"]
    assert "2025-12-02" in cal_resp["data"]["events_by_date"]
    assert "2025-12-03" in cal_resp["data"]["events_by_date"]
    assert "2025-12-05" in cal_resp["data"]["events_by_date"]

    # Upcoming workouts should have normalized dates
    wk_result = await get_upcoming_workouts(ctx=mock_ctx)
    wk_resp = json.loads(wk_result)
    assert any(w["date"] == "2025-12-01" for w in wk_resp["data"]["workouts"]) is True
    assert any(w["date"] == "2025-12-02" for w in wk_resp["data"]["workouts"]) is True
    assert any(w["date"] == "2025-12-03" for w in wk_resp["data"]["workouts"]) is True


async def test_get_event_normalizes_date(mock_config, respx_mock):
    """Ensure single event fetch normalizes various ISO date inputs to YYYY-MM-DD."""
    mock_ctx = MagicMock()
    mock_ctx.get_state.return_value = mock_config

    payloads = [
        (4001, "2025-12-01T08:00Z", "2025-12-01"),
        (4002, "2025-12-02T08:00:00.123Z", "2025-12-02"),
    ]

    for eid, start, expected in payloads:
        event_payload = {
            "id": eid,
            "start_date_local": start,
            "category": "WORKOUT",
            "name": "Normalized Event",
        }

        respx_mock.get(f"/athlete/i123456/events/{eid}").mock(return_value=Response(200, json=event_payload))

        result = await get_event(eid, ctx=mock_ctx)
        resp = json.loads(result)

        assert "data" in resp
        assert resp["data"]["date"] == expected
