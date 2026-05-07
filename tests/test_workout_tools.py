"""Tests for workout library tools."""

import json
from unittest.mock import MagicMock

from httpx import Response

from intervals_icu_mcp.tools.workout_library import (
    bulk_create_workouts,
    create_workout,
    delete_workout,
    duplicate_workouts,
    get_workout,
    get_workout_tags,
    update_workout,
)


def make_workout_response(**kwargs):
    base = {
        "id": 501,
        "name": "Test Workout",
        "folder_id": 10,
        "type": "Ride",
        "moving_time": 3600,
    }
    base.update(kwargs)
    return base


class TestGetWorkout:
    async def test_get_workout_success(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state.return_value = mock_config

        workout_data = make_workout_response(workout_doc={"steps": [{"duration": 300}]})
        respx_mock.get("/athlete/i123456/workouts/501").mock(
            return_value=Response(200, json=workout_data)
        )

        result = await get_workout(workout_id=501, ctx=mock_ctx)

        response = json.loads(result)
        assert "data" in response
        assert response["data"]["id"] == 501
        assert response["data"]["workout_doc"]["steps"][0]["duration"] == 300


class TestCreateWorkout:
    async def test_create_workout_basic(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state.return_value = mock_config

        workout_data = make_workout_response()
        respx_mock.post("/athlete/i123456/workouts").mock(
            return_value=Response(200, json=workout_data)
        )

        result = await create_workout(folder_id=10, name="Test Workout", ctx=mock_ctx)

        response = json.loads(result)
        assert "data" in response
        assert response["data"]["name"] == "Test Workout"
        assert response["data"]["folder_id"] == 10

    async def test_create_workout_with_workout_doc(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state.return_value = mock_config

        doc = {"steps": [{"duration": 600, "power": {"value": 300, "units": "W"}}]}
        workout_data = make_workout_response(workout_doc=doc)
        respx_mock.post("/athlete/i123456/workouts").mock(
            return_value=Response(200, json=workout_data)
        )

        result = await create_workout(
            folder_id=10,
            name="FTP Test",
            workout_doc=json.dumps(doc),
            ctx=mock_ctx,
        )

        response = json.loads(result)
        assert "data" in response
        assert "workout_doc" in response["data"]

    async def test_create_workout_invalid_workout_doc(self, mock_config):
        mock_ctx = MagicMock()
        mock_ctx.get_state.return_value = mock_config

        result = await create_workout(
            folder_id=10,
            name="Bad",
            workout_doc="{bad json",
            ctx=mock_ctx,
        )

        response = json.loads(result)
        assert "error" in response

    async def test_create_workout_with_tags(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state.return_value = mock_config

        workout_data = make_workout_response(tags=["intervals", "vo2max"])
        respx_mock.post("/athlete/i123456/workouts").mock(
            return_value=Response(200, json=workout_data)
        )

        result = await create_workout(
            folder_id=10,
            name="VO2max",
            tags="intervals,vo2max",
            ctx=mock_ctx,
        )

        response = json.loads(result)
        assert "data" in response
        assert response["data"]["tags"] == ["intervals", "vo2max"]


class TestUpdateWorkout:
    async def test_update_workout_name(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state.return_value = mock_config

        workout_data = make_workout_response(name="Updated Name")
        respx_mock.put("/athlete/i123456/workouts/501").mock(
            return_value=Response(200, json=workout_data)
        )

        result = await update_workout(workout_id=501, name="Updated Name", ctx=mock_ctx)

        response = json.loads(result)
        assert "data" in response
        assert response["data"]["name"] == "Updated Name"

    async def test_update_workout_no_fields_error(self, mock_config):
        mock_ctx = MagicMock()
        mock_ctx.get_state.return_value = mock_config

        result = await update_workout(workout_id=501, ctx=mock_ctx)

        response = json.loads(result)
        assert "error" in response


class TestDeleteWorkout:
    async def test_delete_workout_success(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state.return_value = mock_config

        respx_mock.delete("/athlete/i123456/workouts/501").mock(return_value=Response(204))

        result = await delete_workout(workout_id=501, ctx=mock_ctx)

        response = json.loads(result)
        assert "data" in response
        assert response["data"]["deleted"] is True


class TestBulkCreateWorkouts:
    async def test_bulk_create_valid(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state.return_value = mock_config

        workouts_response = [
            make_workout_response(id=501, name="Workout 1"),
            make_workout_response(id=502, name="Workout 2"),
        ]
        respx_mock.post("/athlete/i123456/workouts/bulk").mock(
            return_value=Response(200, json=workouts_response)
        )

        workouts_json = json.dumps(
            [
                {"folder_id": 10, "name": "Workout 1"},
                {"folder_id": 10, "name": "Workout 2"},
            ]
        )

        result = await bulk_create_workouts(workouts=workouts_json, ctx=mock_ctx)

        response = json.loads(result)
        assert "data" in response
        assert response["metadata"]["count"] == 2

    async def test_bulk_create_missing_folder_id(self, mock_config):
        mock_ctx = MagicMock()
        mock_ctx.get_state.return_value = mock_config

        workouts_json = json.dumps([{"name": "Missing folder_id"}])
        result = await bulk_create_workouts(workouts=workouts_json, ctx=mock_ctx)

        response = json.loads(result)
        assert "error" in response

    async def test_bulk_create_missing_name(self, mock_config):
        mock_ctx = MagicMock()
        mock_ctx.get_state.return_value = mock_config

        workouts_json = json.dumps([{"folder_id": 10}])
        result = await bulk_create_workouts(workouts=workouts_json, ctx=mock_ctx)

        response = json.loads(result)
        assert "error" in response


class TestGetWorkoutTags:
    async def test_get_workout_tags(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state.return_value = mock_config

        respx_mock.get("/athlete/i123456/workout-tags").mock(
            return_value=Response(200, json=["intervals", "endurance", "recovery"])
        )

        result = await get_workout_tags(ctx=mock_ctx)

        response = json.loads(result)
        assert "data" in response
        assert response["data"]["count"] == 3
        assert "intervals" in response["data"]["tags"]


class TestDuplicateWorkouts:
    async def test_duplicate_workouts(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state.return_value = mock_config

        created = [make_workout_response(id=601), make_workout_response(id=602)]
        respx_mock.post("/athlete/i123456/duplicate-workouts").mock(
            return_value=Response(200, json=created)
        )

        result = await duplicate_workouts(
            workout_ids="[501]",
            num_copies=2,
            weeks_between=1,
            ctx=mock_ctx,
        )

        response = json.loads(result)
        assert "data" in response
        assert response["metadata"]["count"] == 2

    async def test_duplicate_workouts_invalid_json(self, mock_config):
        mock_ctx = MagicMock()
        mock_ctx.get_state.return_value = mock_config

        result = await duplicate_workouts(workout_ids="not-json", ctx=mock_ctx)
        response = json.loads(result)
        assert "error" in response
