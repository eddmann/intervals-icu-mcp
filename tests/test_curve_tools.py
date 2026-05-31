"""Tests for power / HR / pace curve tools after the API contract fix.

The Intervals.icu curves endpoints require .json extension, a required `type`
query param, and the `curves` window param. Responses are DataCurveSet with
parallel arrays inside list[0] — these tests verify the tools correctly issue
the right request and flatten the response.
"""

import json
from unittest.mock import MagicMock

from httpx import Response

from intervals_icu_mcp.tools.curves import get_hr_curves, get_pace_curves
from intervals_icu_mcp.tools.performance import get_power_curves


def _power_curve_response() -> dict:
    """Realistic-ish power curve response with 1s, 5s, 60s, 300s, 1200s points."""
    return {
        "list": [
            {
                "id": "90d",
                "label": "90 days",
                "days": 90,
                "start_date_local": "2026-02-19T00:00:00",
                "end_date_local": "2026-05-19T00:00:00",
                "moving_time": 0,
                "training_load": 0,
                "weight": 67.25,
                "secs": [1, 5, 60, 300, 1200, 3600],
                "values": [588, 549, 400, 300, 240, 200],
                "activity_id": ["a1", "a1", "a2", "a3", "a4", "a5"],
            }
        ],
        "activities": {},
    }


def _hr_curve_response() -> dict:
    return {
        "list": [
            {
                "id": "90d",
                "label": "90 days",
                "secs": [1, 60, 300, 1200],
                "values": [162, 158, 150, 141],
                "activity_id": ["a1", "a2", "a3", "a4"],
            }
        ],
        "activities": {},
    }


def _pace_curve_response() -> dict:
    # 400 m @ 90 s, 1000 m @ 273 s, 5000 m @ 1512 s, 10000 m @ 3196 s
    return {
        "list": [
            {
                "id": "90d",
                "label": "90 days",
                "distance": [400.0, 1000.0, 5000.0, 10_000.0],
                "values": [90, 273, 1512, 3196],
                "activity_id": ["r1", "r2", "r3", "r4"],
            }
        ],
        "activities": {},
    }


class TestPowerCurves:
    async def test_returns_peak_efforts_and_ftp_analysis(self, mock_config, respx_mock):
        ctx = MagicMock()
        ctx.get_state.return_value = mock_config

        route = respx_mock.get("/athlete/i123456/power-curves.json").mock(
            return_value=Response(200, json=_power_curve_response())
        )

        result = await get_power_curves(ctx=ctx)
        assert route.called
        # Verify the API was hit with the right required params.
        request = route.calls.last.request
        assert "type=Ride" in str(request.url)
        assert "curves=90d" in str(request.url)

        r = json.loads(result)
        assert "data" in r
        d = r["data"]
        # 20-min power point exists.
        assert d["peak_efforts"]["20_min"]["watts"] == 240
        # FTP = 95% of 20-min = 228.
        assert d["ftp_analysis"]["twenty_min_power"] == 240
        assert d["ftp_analysis"]["estimated_ftp"] == 228
        assert "power_zones" in d["ftp_analysis"]
        assert d["summary"]["athlete_weight_kg"] == 67.25

    async def test_days_back_maps_to_curves_param(self, mock_config, respx_mock):
        ctx = MagicMock()
        ctx.get_state.return_value = mock_config
        route = respx_mock.get("/athlete/i123456/power-curves.json").mock(
            return_value=Response(200, json=_power_curve_response())
        )
        await get_power_curves(days_back=42, ctx=ctx)
        assert "curves=42d" in str(route.calls.last.request.url)

    async def test_time_period_year_maps_to_1y(self, mock_config, respx_mock):
        ctx = MagicMock()
        ctx.get_state.return_value = mock_config
        route = respx_mock.get("/athlete/i123456/power-curves.json").mock(
            return_value=Response(200, json=_power_curve_response())
        )
        await get_power_curves(time_period="year", ctx=ctx)
        assert "curves=1y" in str(route.calls.last.request.url)

    async def test_empty_curve_returns_friendly_message(self, mock_config, respx_mock):
        ctx = MagicMock()
        ctx.get_state.return_value = mock_config
        respx_mock.get("/athlete/i123456/power-curves.json").mock(
            return_value=Response(200, json={"list": [], "activities": {}})
        )
        result = await get_power_curves(ctx=ctx)
        r = json.loads(result)
        assert "data" in r
        assert r["data"]["power_curve"] == []
        assert "No power curve data" in r["metadata"]["message"]


class TestHRCurves:
    async def test_returns_peak_efforts_and_zones(self, mock_config, respx_mock):
        ctx = MagicMock()
        ctx.get_state.return_value = mock_config
        route = respx_mock.get("/athlete/i123456/hr-curves.json").mock(
            return_value=Response(200, json=_hr_curve_response())
        )
        result = await get_hr_curves(ctx=ctx)
        assert route.called
        request_url = str(route.calls.last.request.url)
        assert "type=Ride" in request_url

        r = json.loads(result)
        d = r["data"]
        assert d["peak_efforts"]["20_min"]["bpm"] == 141
        # Max HR derived zones present.
        assert "hr_zones" in d
        assert d["summary"]["max_hr_bpm"] == 162


class TestPaceCurves:
    async def test_returns_best_efforts_at_standard_distances(self, mock_config, respx_mock):
        ctx = MagicMock()
        ctx.get_state.return_value = mock_config
        route = respx_mock.get("/athlete/i123456/pace-curves.json").mock(
            return_value=Response(200, json=_pace_curve_response())
        )
        result = await get_pace_curves(ctx=ctx)
        assert route.called
        request_url = str(route.calls.last.request.url)
        assert "type=Run" in request_url

        r = json.loads(result)
        d = r["data"]
        # 1 km = 273 s = 4:33 pace.
        assert d["best_efforts"]["1km"]["time_seconds"] == 273
        assert d["best_efforts"]["1km"]["pace_formatted"] == "4:33 /km"
        # 5 km = 1512 s over 5000 m = 5:02.4 / km.
        assert d["best_efforts"]["5km"]["pace_formatted"] in ("5:02 /km", "5:03 /km")
        # 10 km present.
        assert "10km" in d["best_efforts"]

    async def test_gap_flag_passed_to_api(self, mock_config, respx_mock):
        ctx = MagicMock()
        ctx.get_state.return_value = mock_config
        route = respx_mock.get("/athlete/i123456/pace-curves.json").mock(
            return_value=Response(200, json=_pace_curve_response())
        )
        await get_pace_curves(use_gap=True, ctx=ctx)
        assert "gap=true" in str(route.calls.last.request.url)
