"""Tests for event management tools."""

import json
from unittest.mock import MagicMock

from httpx import Response

from intervals_icu_mcp.tools.event_management import (
    bulk_create_events,
    create_event,
    duplicate_event,
    update_event,
)


def make_event_response(**kwargs):
    base = {
        "id": 1001,
        "start_date_local": "2026-04-01",
        "category": "WORKOUT",
        "name": "Test Workout",
    }
    base.update(kwargs)
    return base


class TestCreateEvent:
    async def test_create_basic_event(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state.return_value = mock_config

        event_data = make_event_response()
        respx_mock.post("/athlete/i123456/events").mock(return_value=Response(200, json=event_data))

        result = await create_event(
            start_date="2026-04-01",
            name="Test Workout",
            category="WORKOUT",
            ctx=mock_ctx,
        )

        response = json.loads(result)
        assert "data" in response
        assert response["data"]["id"] == 1001
        assert response["data"]["name"] == "Test Workout"
        assert response["data"]["category"] == "WORKOUT"

    async def test_create_event_with_workout_doc(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state.return_value = mock_config

        event_data = make_event_response(
            workout_doc={"steps": [{"duration": 300, "power": {"value": 250, "units": "W"}}]}
        )
        respx_mock.post("/athlete/i123456/events").mock(return_value=Response(200, json=event_data))

        workout_doc_json = json.dumps(
            {"steps": [{"duration": 300, "power": {"value": 250, "units": "W"}}]}
        )

        result = await create_event(
            start_date="2026-04-01",
            name="Structured Workout",
            category="WORKOUT",
            workout_doc=workout_doc_json,
            ctx=mock_ctx,
        )

        response = json.loads(result)
        assert "data" in response
        assert "workout_doc" in response["data"]
        assert response["data"]["workout_doc"]["steps"][0]["duration"] == 300

    async def test_create_event_with_tags(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state.return_value = mock_config

        event_data = make_event_response(tags=["intervals", "threshold"])
        respx_mock.post("/athlete/i123456/events").mock(return_value=Response(200, json=event_data))

        result = await create_event(
            start_date="2026-04-01",
            name="Threshold Work",
            category="WORKOUT",
            tags="intervals,threshold",
            ctx=mock_ctx,
        )

        response = json.loads(result)
        assert "data" in response
        assert response["data"]["tags"] == ["intervals", "threshold"]

    async def test_create_event_invalid_category(self, mock_config):
        mock_ctx = MagicMock()
        mock_ctx.get_state.return_value = mock_config

        result = await create_event(
            start_date="2026-04-01",
            name="Bad Event",
            category="INVALID",
            ctx=mock_ctx,
        )

        response = json.loads(result)
        assert "error" in response

    async def test_create_event_invalid_date(self, mock_config):
        mock_ctx = MagicMock()
        mock_ctx.get_state.return_value = mock_config

        result = await create_event(
            start_date="not-a-date",
            name="Test",
            category="WORKOUT",
            ctx=mock_ctx,
        )

        response = json.loads(result)
        assert "error" in response

    async def test_create_event_all_14_categories(self, mock_config, respx_mock):
        """Verify all 14 event categories are accepted."""
        mock_ctx = MagicMock()
        mock_ctx.get_state.return_value = mock_config

        categories = [
            "WORKOUT",
            "RACE_A",
            "RACE_B",
            "RACE_C",
            "NOTE",
            "PLAN",
            "HOLIDAY",
            "SICK",
            "INJURED",
            "SET_EFTP",
            "FITNESS_DAYS",
            "SEASON_START",
            "TARGET",
            "SET_FITNESS",
        ]

        for cat in categories:
            event_data = make_event_response(category=cat)
            respx_mock.post("/athlete/i123456/events").mock(
                return_value=Response(200, json=event_data)
            )
            result = await create_event(
                start_date="2026-04-01", name=f"Test {cat}", category=cat, ctx=mock_ctx
            )
            response = json.loads(result)
            assert "data" in response, f"Category {cat} should be valid but got error"

    async def test_create_event_invalid_workout_doc_json(self, mock_config):
        mock_ctx = MagicMock()
        mock_ctx.get_state.return_value = mock_config

        result = await create_event(
            start_date="2026-04-01",
            name="Bad Workout",
            category="WORKOUT",
            workout_doc="{invalid json",
            ctx=mock_ctx,
        )

        response = json.loads(result)
        assert "error" in response

    async def test_create_event_with_indoor_and_target(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state.return_value = mock_config

        event_data = make_event_response(indoor=True, target="POWER")
        respx_mock.post("/athlete/i123456/events").mock(return_value=Response(200, json=event_data))

        result = await create_event(
            start_date="2026-04-01",
            name="Indoor Ride",
            category="WORKOUT",
            indoor=True,
            target="POWER",
            ctx=mock_ctx,
        )

        response = json.loads(result)
        assert "data" in response
        assert response["data"]["indoor"] is True
        assert response["data"]["target"] == "POWER"


class TestUpdateEvent:
    async def test_update_event_basic(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state.return_value = mock_config

        event_data = make_event_response(name="Updated Workout")
        respx_mock.put("/athlete/i123456/events/1001").mock(
            return_value=Response(200, json=event_data)
        )

        result = await update_event(event_id=1001, name="Updated Workout", ctx=mock_ctx)

        response = json.loads(result)
        assert "data" in response
        assert response["data"]["name"] == "Updated Workout"

    async def test_update_event_with_workout_doc(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state.return_value = mock_config

        new_doc = {"steps": [{"duration": 600}]}
        event_data = make_event_response(workout_doc=new_doc)
        respx_mock.put("/athlete/i123456/events/1001").mock(
            return_value=Response(200, json=event_data)
        )

        result = await update_event(
            event_id=1001,
            workout_doc=json.dumps(new_doc),
            ctx=mock_ctx,
        )

        response = json.loads(result)
        assert "data" in response
        assert response["data"]["workout_doc"]["steps"][0]["duration"] == 600

    async def test_update_event_no_fields_error(self, mock_config):
        mock_ctx = MagicMock()
        mock_ctx.get_state.return_value = mock_config

        result = await update_event(event_id=1001, ctx=mock_ctx)

        response = json.loads(result)
        assert "error" in response


class TestBulkCreateEvents:
    async def test_bulk_create_valid(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state.return_value = mock_config

        events_response = [
            make_event_response(id=1001, name="Ride 1"),
            make_event_response(id=1002, name="Run 1"),
        ]
        respx_mock.post("/athlete/i123456/events/bulk").mock(
            return_value=Response(200, json=events_response)
        )

        events_json = json.dumps(
            [
                {"start_date_local": "2026-04-01", "name": "Ride 1", "category": "WORKOUT"},
                {"start_date_local": "2026-04-02", "name": "Run 1", "category": "WORKOUT"},
            ]
        )

        result = await bulk_create_events(events=events_json, ctx=mock_ctx)

        response = json.loads(result)
        assert "data" in response
        assert response["metadata"]["count"] == 2

    async def test_bulk_create_accepts_new_categories(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state.return_value = mock_config

        events_response = [make_event_response(category="RACE_A")]
        respx_mock.post("/athlete/i123456/events/bulk").mock(
            return_value=Response(200, json=events_response)
        )

        events_json = json.dumps(
            [{"start_date_local": "2026-05-01", "name": "A Race", "category": "RACE_A"}]
        )

        result = await bulk_create_events(events=events_json, ctx=mock_ctx)

        response = json.loads(result)
        assert "data" in response

    async def test_bulk_create_invalid_json(self, mock_config):
        mock_ctx = MagicMock()
        mock_ctx.get_state.return_value = mock_config

        result = await bulk_create_events(events="not json", ctx=mock_ctx)
        response = json.loads(result)
        assert "error" in response


class TestDuplicateEvent:
    async def test_duplicate_event(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state.return_value = mock_config

        event_data = make_event_response(start_date_local="2026-04-08")
        respx_mock.post("/athlete/i123456/events/1001/duplicate").mock(
            return_value=Response(200, json=event_data)
        )

        result = await duplicate_event(event_id=1001, new_date="2026-04-08", ctx=mock_ctx)

        response = json.loads(result)
        assert "data" in response
        assert response["data"]["original_event_id"] == 1001

    async def test_duplicate_event_invalid_date(self, mock_config):
        mock_ctx = MagicMock()
        mock_ctx.get_state.return_value = mock_config

        result = await duplicate_event(event_id=1001, new_date="bad-date", ctx=mock_ctx)
        response = json.loads(result)
        assert "error" in response
