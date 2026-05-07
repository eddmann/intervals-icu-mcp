"""Workout folder and sharing management tools for Intervals.icu MCP server."""

import json
from typing import Annotated, Any

from fastmcp import Context

from ..auth import ICUConfig
from ..client import ICUAPIError, ICUClient
from ..models import Folder
from ..response_builder import ResponseBuilder

VALID_FOLDER_TYPES = ["FOLDER", "PLAN"]
VALID_VISIBILITIES = ["PRIVATE", "PUBLIC"]


def _folder_to_dict(folder: Folder) -> dict[str, Any]:
    """Build a response dict from a Folder model."""
    result: dict[str, Any] = {
        "id": folder.id,
        "name": folder.name,
    }
    if folder.type:
        result["type"] = folder.type
    if folder.description:
        result["description"] = folder.description
    if folder.visibility:
        result["visibility"] = folder.visibility
    if folder.blurb:
        result["blurb"] = folder.blurb
    if folder.num_workouts is not None:
        result["num_workouts"] = folder.num_workouts
    if folder.start_date_local:
        result["start_date"] = folder.start_date_local
    if folder.duration_weeks is not None:
        result["duration_weeks"] = folder.duration_weeks
    if folder.hours_per_week_min or folder.hours_per_week_max:
        result["hours_per_week"] = {
            "min": folder.hours_per_week_min,
            "max": folder.hours_per_week_max,
        }
    if folder.rollout_weeks is not None:
        result["rollout_weeks"] = folder.rollout_weeks
    if folder.starting_ctl is not None:
        result["starting_ctl"] = folder.starting_ctl
    if folder.starting_atl is not None:
        result["starting_atl"] = folder.starting_atl
    if folder.activity_types:
        result["activity_types"] = folder.activity_types
    if folder.workout_targets:
        result["workout_targets"] = folder.workout_targets
    if folder.read_only_workouts is not None:
        result["read_only_workouts"] = folder.read_only_workouts
    return result


async def create_folder(
    name: Annotated[str, "Folder or training plan name"],
    folder_type: Annotated[str, "FOLDER for a simple folder, PLAN for a training plan"] = "FOLDER",
    description: Annotated[str | None, "Description of the folder or plan"] = None,
    visibility: Annotated[str | None, "Visibility: PRIVATE or PUBLIC"] = None,
    copy_folder_id: Annotated[int | None, "Copy workouts from an existing folder ID"] = None,
    start_date: Annotated[str | None, "Plan start date (YYYY-MM-DD), for PLAN type"] = None,
    rollout_weeks: Annotated[int | None, "Number of weeks to roll out the plan"] = None,
    starting_ctl: Annotated[int | None, "Starting CTL (fitness) for the plan"] = None,
    starting_atl: Annotated[int | None, "Starting ATL (fatigue) for the plan"] = None,
    blurb: Annotated[str | None, "Short marketing description for the plan"] = None,
    ctx: Context | None = None,
) -> str:
    """Create a new workout folder or training plan.

    Folders organize workouts in your library. Training plans (PLAN type) can be
    assigned a start date and scheduled onto an athlete's calendar.

    Returns:
        JSON string with created folder data
    """
    assert ctx is not None
    config: ICUConfig = ctx.get_state("config")

    if folder_type.upper() not in VALID_FOLDER_TYPES:
        return ResponseBuilder.build_error_response(
            f"Invalid folder_type. Must be one of: {', '.join(VALID_FOLDER_TYPES)}",
            error_type="validation_error",
        )

    if visibility and visibility.upper() not in VALID_VISIBILITIES:
        return ResponseBuilder.build_error_response(
            f"Invalid visibility. Must be one of: {', '.join(VALID_VISIBILITIES)}",
            error_type="validation_error",
        )

    try:
        folder_data: dict[str, Any] = {
            "name": name,
            "type": folder_type.upper(),
        }

        if description is not None:
            folder_data["description"] = description
        if visibility is not None:
            folder_data["visibility"] = visibility.upper()
        if copy_folder_id is not None:
            folder_data["copy_folder_id"] = copy_folder_id
        if start_date is not None:
            folder_data["start_date_local"] = start_date
        if rollout_weeks is not None:
            folder_data["rollout_weeks"] = rollout_weeks
        if starting_ctl is not None:
            folder_data["starting_ctl"] = starting_ctl
        if starting_atl is not None:
            folder_data["starting_atl"] = starting_atl
        if blurb is not None:
            folder_data["blurb"] = blurb

        async with ICUClient(config) as client:
            folder = await client.create_folder(folder_data)

            return ResponseBuilder.build_response(
                data=_folder_to_dict(folder),
                query_type="create_folder",
                metadata={"message": f"Successfully created {folder_type.lower()}: {name}"},
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )


async def update_folder(
    folder_id: Annotated[int, "Folder ID to update"],
    name: Annotated[str | None, "Updated folder name"] = None,
    description: Annotated[str | None, "Updated description"] = None,
    visibility: Annotated[str | None, "Updated visibility: PRIVATE or PUBLIC"] = None,
    start_date: Annotated[str | None, "Updated plan start date (YYYY-MM-DD)"] = None,
    rollout_weeks: Annotated[int | None, "Updated rollout weeks"] = None,
    starting_ctl: Annotated[int | None, "Updated starting CTL"] = None,
    starting_atl: Annotated[int | None, "Updated starting ATL"] = None,
    blurb: Annotated[str | None, "Updated short description"] = None,
    ctx: Context | None = None,
) -> str:
    """Update an existing folder or training plan.

    Only provide the fields you want to change — others remain unchanged.

    Returns:
        JSON string with updated folder data
    """
    assert ctx is not None
    config: ICUConfig = ctx.get_state("config")

    if visibility and visibility.upper() not in VALID_VISIBILITIES:
        return ResponseBuilder.build_error_response(
            f"Invalid visibility. Must be one of: {', '.join(VALID_VISIBILITIES)}",
            error_type="validation_error",
        )

    try:
        folder_data: dict[str, Any] = {}

        if name is not None:
            folder_data["name"] = name
        if description is not None:
            folder_data["description"] = description
        if visibility is not None:
            folder_data["visibility"] = visibility.upper()
        if start_date is not None:
            folder_data["start_date_local"] = start_date
        if rollout_weeks is not None:
            folder_data["rollout_weeks"] = rollout_weeks
        if starting_ctl is not None:
            folder_data["starting_ctl"] = starting_ctl
        if starting_atl is not None:
            folder_data["starting_atl"] = starting_atl
        if blurb is not None:
            folder_data["blurb"] = blurb

        if not folder_data:
            return ResponseBuilder.build_error_response(
                "No fields provided to update.", error_type="validation_error"
            )

        async with ICUClient(config) as client:
            folder = await client.update_folder(folder_id, folder_data)

            return ResponseBuilder.build_response(
                data=_folder_to_dict(folder),
                query_type="update_folder",
                metadata={"message": f"Successfully updated folder {folder_id}"},
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )


async def delete_folder(
    folder_id: Annotated[int, "Folder ID to delete"],
    ctx: Context | None = None,
) -> str:
    """Delete a folder and all workouts inside it.

    Permanently removes the folder and all its workouts. Cannot be undone.

    Returns:
        JSON string with deletion confirmation
    """
    assert ctx is not None
    config: ICUConfig = ctx.get_state("config")

    try:
        async with ICUClient(config) as client:
            await client.delete_folder(folder_id)

            return ResponseBuilder.build_response(
                data={"folder_id": folder_id, "deleted": True},
                query_type="delete_folder",
                metadata={
                    "message": f"Successfully deleted folder {folder_id} and all its workouts"
                },
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )


async def update_plan_workouts(
    folder_id: Annotated[int, "Folder/plan ID whose workouts to update"],
    hide_from_athlete: Annotated[bool | None, "Set visibility for all matching workouts"] = None,
    oldest: Annotated[str | None, "Oldest date in range to update (YYYY-MM-DD)"] = None,
    newest: Annotated[str | None, "Newest date in range to update (YYYY-MM-DD)"] = None,
    ctx: Context | None = None,
) -> str:
    """Batch update workouts on a training plan.

    Updates properties on multiple workouts at once, optionally restricted to
    a date range. Useful for bulk-hiding workouts from an athlete.

    Returns:
        JSON string with updated workout count
    """
    assert ctx is not None
    config: ICUConfig = ctx.get_state("config")

    try:
        workout_data: dict[str, Any] = {}

        if hide_from_athlete is not None:
            workout_data["hide_from_athlete"] = hide_from_athlete

        if not workout_data:
            return ResponseBuilder.build_error_response(
                "No fields provided to update.", error_type="validation_error"
            )

        async with ICUClient(config) as client:
            updated = await client.update_plan_workouts(
                folder_id, workout_data, oldest=oldest, newest=newest
            )

            return ResponseBuilder.build_response(
                data={"folder_id": folder_id, "updated_count": len(updated)},
                query_type="update_plan_workouts",
                metadata={
                    "message": f"Successfully updated {len(updated)} workouts in folder {folder_id}"
                },
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )


async def get_folder_sharing(
    folder_id: Annotated[int, "Folder ID to get sharing info for"],
    ctx: Context | None = None,
) -> str:
    """List athletes a folder is shared with.

    Returns:
        JSON string with list of athletes who have access to the folder
    """
    assert ctx is not None
    config: ICUConfig = ctx.get_state("config")

    try:
        async with ICUClient(config) as client:
            shared_with = await client.get_folder_shared_with(folder_id)

            athletes = [
                {
                    "id": sw.id,
                    "name": sw.name,
                    "email": sw.email,
                    "can_edit": sw.can_edit,
                }
                for sw in shared_with
            ]

            return ResponseBuilder.build_response(
                data={"folder_id": folder_id, "shared_with": athletes, "count": len(athletes)},
                query_type="get_folder_sharing",
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )


async def update_folder_sharing(
    folder_id: Annotated[int, "Folder ID to update sharing for"],
    athletes: Annotated[
        str,
        'JSON array of athlete share objects, e.g. [{"id": "athlete123", "canEdit": false}]. '
        "To remove sharing, provide an empty array [].",
    ],
    ctx: Context | None = None,
) -> str:
    """Add or remove athletes from a folder's share list.

    Replaces the current share list with the provided list. To remove all sharing,
    provide an empty array.

    Returns:
        JSON string with updated share list
    """
    assert ctx is not None
    config: ICUConfig = ctx.get_state("config")

    try:
        try:
            parsed = json.loads(athletes)
        except json.JSONDecodeError as e:
            return ResponseBuilder.build_error_response(
                f"Invalid JSON format: {str(e)}", error_type="validation_error"
            )

        if not isinstance(parsed, list):
            return ResponseBuilder.build_error_response(
                "athletes must be a JSON array", error_type="validation_error"
            )

        share_list: list[dict[str, Any]] = parsed  # type: ignore[assignment]

        async with ICUClient(config) as client:
            updated = await client.update_folder_shared_with(folder_id, share_list)

            result = [
                {
                    "id": sw.id,
                    "name": sw.name,
                    "email": sw.email,
                    "can_edit": sw.can_edit,
                }
                for sw in updated
            ]

            return ResponseBuilder.build_response(
                data={"folder_id": folder_id, "shared_with": result, "count": len(result)},
                query_type="update_folder_sharing",
                metadata={"message": f"Successfully updated sharing for folder {folder_id}"},
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )
