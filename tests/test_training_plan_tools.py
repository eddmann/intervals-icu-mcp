"""Tests for training plan management tools."""

import json
from unittest.mock import MagicMock

from httpx import Response

from intervals_icu_mcp.tools.training_plan import (
    apply_plan_changes,
    get_training_plan,
    set_training_plan,
)


def make_plan_response(**kwargs):
    base = {
        "id": "i123456",
        "training_plan_id": 42,
        "training_plan_start_date": "2026-05-01",
        "training_plan_alias": "My Base Build",
        "training_plan": {
            "id": 42,
            "name": "16-Week Base Build",
            "duration_weeks": 16,
            "num_workouts": 64,
        },
    }
    base.update(kwargs)
    return base


class TestGetTrainingPlan:
    async def test_get_training_plan_with_plan(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state.return_value = mock_config

        plan_data = make_plan_response()
        respx_mock.get("/athlete/i123456/training-plan").mock(
            return_value=Response(200, json=plan_data)
        )

        result = await get_training_plan(ctx=mock_ctx)

        response = json.loads(result)
        assert "data" in response
        assert response["data"]["training_plan"]["training_plan_id"] == 42
        assert response["data"]["training_plan"]["start_date"] == "2026-05-01"

    async def test_get_training_plan_none_assigned(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state.return_value = mock_config

        respx_mock.get("/athlete/i123456/training-plan").mock(
            return_value=Response(200, json={"id": "i123456"})
        )

        result = await get_training_plan(ctx=mock_ctx)

        response = json.loads(result)
        assert "data" in response
        assert response["data"]["training_plan"] is None


class TestSetTrainingPlan:
    async def test_set_training_plan(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state.return_value = mock_config

        plan_data = make_plan_response()
        respx_mock.put("/athlete/i123456/training-plan").mock(
            return_value=Response(200, json=plan_data)
        )

        result = await set_training_plan(
            training_plan_id=42,
            start_date="2026-05-01",
            alias="My Base Build",
            ctx=mock_ctx,
        )

        response = json.loads(result)
        assert "data" in response
        assert response["data"]["training_plan"]["training_plan_id"] == 42

    async def test_set_training_plan_invalid_date(self, mock_config):
        mock_ctx = MagicMock()
        mock_ctx.get_state.return_value = mock_config

        result = await set_training_plan(
            training_plan_id=42,
            start_date="not-a-date",
            ctx=mock_ctx,
        )

        response = json.loads(result)
        assert "error" in response


class TestApplyPlanChanges:
    async def test_apply_plan_changes(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state.return_value = mock_config

        respx_mock.put("/athlete/i123456/apply-plan-changes").mock(
            return_value=Response(200, json={"applied": True, "count": 12})
        )

        result = await apply_plan_changes(ctx=mock_ctx)

        response = json.loads(result)
        assert "data" in response
        assert response["data"]["applied"] is True
