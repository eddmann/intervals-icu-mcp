"""Tests for activity analysis tools, focused on the get_activity_streams fix.

The Intervals.icu streams endpoint returns a list of stream objects (each with
`type` and `data` fields), but the prior code assumed a flat dict shape. Every
call therefore failed with `ActivityStreams() argument after ** must be a
mapping, not list`. The fix unflattens the list at the client boundary.
"""

import json
from unittest.mock import MagicMock

from httpx import Response

from intervals_icu_mcp.tools.activity_analysis import get_activity_streams


def _streams_response() -> list[dict]:
    """The real shape of /activity/{id}/streams responses."""
    return [
        {
            "type": "watts",
            "name": "Power",
            "data": [0, 0, 120, 180, 220, 250, 230, 210],
            "valueType": "int",
            "valueTypeIsArray": False,
        },
        {
            "type": "heartrate",
            "name": "Heart Rate",
            "data": [60, 62, 95, 120, 135, 145, 150, 148],
            "valueType": "int",
            "valueTypeIsArray": False,
        },
        {
            "type": "cadence",
            "name": "Cadence",
            "data": [0, 0, 80, 85, 88, 90, 87, 85],
            "valueType": "int",
            "valueTypeIsArray": False,
        },
        # Real API includes types the model doesn't define (torque, l/r balance).
        # Pydantic v2 ignores unknown fields by default, so these must not fail.
        {"type": "torque", "name": "Torque", "data": [0.0] * 8},
        {"type": "left_right_balance", "name": "L/R", "data": [50] * 8},
    ]


class TestActivityStreams:
    async def test_list_response_is_flattened_into_streams(self, mock_config, respx_mock):
        """The pre-fix bug: code did ActivityStreams(**raw) where raw was a list."""
        ctx = MagicMock()
        ctx.get_state.return_value = mock_config
        respx_mock.get("/activity/i123/streams").mock(
            return_value=Response(200, json=_streams_response())
        )

        result = await get_activity_streams(activity_id="i123", ctx=ctx)
        r = json.loads(result)
        assert "data" in r, f"unexpected response shape: {r}"
        d = r["data"]
        assert set(d["available_streams"]) >= {"watts", "heartrate", "cadence"}
        assert d["stream_lengths"]["watts"] == 8
        assert d["stream_lengths"]["heartrate"] == 8
        assert d["streams"]["watts"][:3] == [0, 0, 120]
        assert d["streams"]["heartrate"][3] == 120

    async def test_filtered_stream_types_passes_through_query_param(
        self, mock_config, respx_mock
    ):
        ctx = MagicMock()
        ctx.get_state.return_value = mock_config
        route = respx_mock.get("/activity/i123/streams").mock(
            return_value=Response(200, json=_streams_response()[:2])
        )

        await get_activity_streams(activity_id="i123", streams=["watts", "heartrate"], ctx=ctx)
        url = str(route.calls.last.request.url)
        # httpx URL-encodes commas as %2C, accept either form.
        assert "types=watts%2Cheartrate" in url or "types=watts,heartrate" in url

    async def test_unknown_extra_stream_types_do_not_break_parsing(
        self, mock_config, respx_mock
    ):
        """torque and left_right_balance are not model fields. They must be ignored."""
        ctx = MagicMock()
        ctx.get_state.return_value = mock_config
        respx_mock.get("/activity/i123/streams").mock(
            return_value=Response(200, json=_streams_response())
        )
        result = await get_activity_streams(activity_id="i123", ctx=ctx)
        r = json.loads(result)
        assert "error" not in r
        assert "torque" not in r["data"]["streams"]

    async def test_empty_list_response_returns_friendly_message(
        self, mock_config, respx_mock
    ):
        ctx = MagicMock()
        ctx.get_state.return_value = mock_config
        respx_mock.get("/activity/i123/streams").mock(return_value=Response(200, json=[]))

        result = await get_activity_streams(activity_id="i123", ctx=ctx)
        r = json.loads(result)
        assert "data" in r
        assert r["data"]["available_streams"] == []
        assert "No stream data" in r["metadata"]["message"]
