"""Tests for folder management tools."""

import json
from unittest.mock import MagicMock

from httpx import Response

from intervals_icu_mcp.tools.folder_management import (
    create_folder,
    delete_folder,
    get_folder_sharing,
    update_folder,
    update_folder_sharing,
    update_plan_workouts,
)


def make_folder_response(**kwargs):
    base = {
        "id": 10,
        "name": "Test Folder",
        "type": "FOLDER",
    }
    base.update(kwargs)
    return base


class TestCreateFolder:
    async def test_create_folder_basic(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state.return_value = mock_config

        folder_data = make_folder_response()
        respx_mock.post("/athlete/i123456/folders").mock(
            return_value=Response(200, json=folder_data)
        )

        result = await create_folder(name="Test Folder", ctx=mock_ctx)

        response = json.loads(result)
        assert "data" in response
        assert response["data"]["name"] == "Test Folder"
        assert response["data"]["id"] == 10

    async def test_create_training_plan(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state.return_value = mock_config

        folder_data = make_folder_response(
            name="16-Week Base Build",
            type="PLAN",
            duration_weeks=16,
            start_date_local="2026-05-01",
        )
        respx_mock.post("/athlete/i123456/folders").mock(
            return_value=Response(200, json=folder_data)
        )

        result = await create_folder(
            name="16-Week Base Build",
            folder_type="PLAN",
            start_date="2026-05-01",
            rollout_weeks=16,
            ctx=mock_ctx,
        )

        response = json.loads(result)
        assert "data" in response
        assert response["data"]["type"] == "PLAN"

    async def test_create_folder_invalid_type(self, mock_config):
        mock_ctx = MagicMock()
        mock_ctx.get_state.return_value = mock_config

        result = await create_folder(name="Bad", folder_type="INVALID", ctx=mock_ctx)
        response = json.loads(result)
        assert "error" in response

    async def test_create_folder_invalid_visibility(self, mock_config):
        mock_ctx = MagicMock()
        mock_ctx.get_state.return_value = mock_config

        result = await create_folder(name="Bad", visibility="HIDDEN", ctx=mock_ctx)
        response = json.loads(result)
        assert "error" in response


class TestUpdateFolder:
    async def test_update_folder_name(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state.return_value = mock_config

        folder_data = make_folder_response(name="Renamed Folder")
        respx_mock.put("/athlete/i123456/folders/10").mock(
            return_value=Response(200, json=folder_data)
        )

        result = await update_folder(folder_id=10, name="Renamed Folder", ctx=mock_ctx)

        response = json.loads(result)
        assert "data" in response
        assert response["data"]["name"] == "Renamed Folder"

    async def test_update_folder_no_fields_error(self, mock_config):
        mock_ctx = MagicMock()
        mock_ctx.get_state.return_value = mock_config

        result = await update_folder(folder_id=10, ctx=mock_ctx)
        response = json.loads(result)
        assert "error" in response


class TestDeleteFolder:
    async def test_delete_folder_success(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state.return_value = mock_config

        respx_mock.delete("/athlete/i123456/folders/10").mock(return_value=Response(204))

        result = await delete_folder(folder_id=10, ctx=mock_ctx)

        response = json.loads(result)
        assert "data" in response
        assert response["data"]["deleted"] is True


class TestUpdatePlanWorkouts:
    async def test_update_plan_workouts(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state.return_value = mock_config

        workouts = [{"id": 501, "name": "W1", "folder_id": 10}]
        respx_mock.put("/athlete/i123456/folders/10/workouts").mock(
            return_value=Response(200, json=workouts)
        )

        result = await update_plan_workouts(folder_id=10, hide_from_athlete=True, ctx=mock_ctx)

        response = json.loads(result)
        assert "data" in response
        assert response["data"]["updated_count"] == 1

    async def test_update_plan_workouts_no_fields_error(self, mock_config):
        mock_ctx = MagicMock()
        mock_ctx.get_state.return_value = mock_config

        result = await update_plan_workouts(folder_id=10, ctx=mock_ctx)
        response = json.loads(result)
        assert "error" in response


class TestFolderSharing:
    async def test_get_folder_sharing(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state.return_value = mock_config

        shared = [{"id": "i999", "name": "Buddy", "canEdit": False, "email": "buddy@example.com"}]
        respx_mock.get("/athlete/i123456/folders/10/shared-with").mock(
            return_value=Response(200, json=shared)
        )

        result = await get_folder_sharing(folder_id=10, ctx=mock_ctx)

        response = json.loads(result)
        assert "data" in response
        assert response["data"]["count"] == 1
        assert response["data"]["shared_with"][0]["id"] == "i999"

    async def test_update_folder_sharing(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state.return_value = mock_config

        updated = [{"id": "i999", "name": "Buddy", "canEdit": True}]
        respx_mock.put("/athlete/i123456/folders/10/shared-with").mock(
            return_value=Response(200, json=updated)
        )

        athletes_json = json.dumps([{"id": "i999", "canEdit": True}])
        result = await update_folder_sharing(folder_id=10, athletes=athletes_json, ctx=mock_ctx)

        response = json.loads(result)
        assert "data" in response
        assert response["data"]["count"] == 1

    async def test_update_folder_sharing_empty_removes_all(self, mock_config, respx_mock):
        mock_ctx = MagicMock()
        mock_ctx.get_state.return_value = mock_config

        respx_mock.put("/athlete/i123456/folders/10/shared-with").mock(
            return_value=Response(200, json=[])
        )

        result = await update_folder_sharing(folder_id=10, athletes="[]", ctx=mock_ctx)

        response = json.loads(result)
        assert "data" in response
        assert response["data"]["count"] == 0
