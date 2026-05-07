"""Workout library tools for Intervals.icu MCP server."""

import base64
import json
from typing import Annotated, Any

from fastmcp import Context

from ..auth import ICUConfig
from ..client import ICUAPIError, ICUClient
from ..models import Workout
from ..response_builder import ResponseBuilder


def _workout_to_dict(workout: Workout) -> dict[str, Any]:
    """Build a response dict from a Workout model, including all populated fields."""
    result: dict[str, Any] = {
        "id": workout.id,
        "name": workout.name,
    }
    if workout.folder_id is not None:
        result["folder_id"] = workout.folder_id
    if workout.description:
        result["description"] = workout.description
    if workout.type:
        result["type"] = workout.type
    if workout.indoor is not None:
        result["indoor"] = workout.indoor
    if workout.color:
        result["color"] = workout.color
    if workout.target:
        result["target"] = workout.target
    if workout.tags:
        result["tags"] = workout.tags
    if workout.sub_type:
        result["sub_type"] = workout.sub_type
    if workout.day is not None:
        result["day"] = workout.day
    if workout.for_week is not None:
        result["for_week"] = workout.for_week
    if workout.hide_from_athlete is not None:
        result["hide_from_athlete"] = workout.hide_from_athlete
    if workout.updated:
        result["updated"] = workout.updated
    if workout.workout_doc:
        result["workout_doc"] = workout.workout_doc

    metrics: dict[str, Any] = {}
    if workout.moving_time:
        metrics["duration_seconds"] = workout.moving_time
    if workout.distance:
        metrics["distance_meters"] = workout.distance
    if workout.icu_training_load:
        metrics["training_load"] = workout.icu_training_load
    if workout.icu_intensity:
        metrics["intensity_factor"] = workout.icu_intensity
    if workout.joules:
        metrics["joules"] = workout.joules
    if workout.joules_above_ftp:
        metrics["joules_above_ftp"] = workout.joules_above_ftp
    if metrics:
        result["metrics"] = metrics

    return result


async def get_workout_library(
    ctx: Context | None = None,
) -> str:
    """Get workout library folders and training plans.

    Returns all workout folders and training plans available to you, including
    your personal workouts, shared workouts, and any training plans you follow.

    Returns:
        JSON string with workout folders/plans
    """
    assert ctx is not None
    config: ICUConfig = ctx.get_state("config")

    try:
        async with ICUClient(config) as client:
            folders = await client.get_workout_folders()

            if not folders:
                return ResponseBuilder.build_response(
                    data={"folders": [], "count": 0},
                    metadata={
                        "message": "No workout folders found. Create folders in Intervals.icu to organize your workouts."
                    },
                )

            folders_data: list[dict[str, Any]] = []
            for folder in folders:
                folder_item: dict[str, Any] = {
                    "id": folder.id,
                    "name": folder.name,
                }

                if folder.description:
                    folder_item["description"] = folder.description
                if folder.num_workouts:
                    folder_item["num_workouts"] = folder.num_workouts
                if folder.type:
                    folder_item["type"] = folder.type
                if folder.visibility:
                    folder_item["visibility"] = folder.visibility
                if folder.blurb:
                    folder_item["blurb"] = folder.blurb

                # Training plan info
                if folder.start_date_local:
                    folder_item["start_date"] = folder.start_date_local
                if folder.duration_weeks:
                    folder_item["duration_weeks"] = folder.duration_weeks
                if folder.hours_per_week_min or folder.hours_per_week_max:
                    folder_item["hours_per_week"] = {
                        "min": folder.hours_per_week_min,
                        "max": folder.hours_per_week_max,
                    }

                folders_data.append(folder_item)

            training_plans = [f for f in folders if f.duration_weeks is not None]
            regular_folders = [f for f in folders if f.duration_weeks is None]

            summary = {
                "total_folders": len(folders),
                "training_plans": len(training_plans),
                "regular_folders": len(regular_folders),
                "total_workouts": sum(f.num_workouts or 0 for f in folders),
            }

            return ResponseBuilder.build_response(
                data={"folders": folders_data, "summary": summary},
                query_type="workout_library",
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )


async def get_workouts_in_folder(
    folder_id: Annotated[int, "Folder ID to get workouts from"],
    ctx: Context | None = None,
) -> str:
    """Get all workouts in a specific folder or training plan.

    Returns detailed information about all workouts stored in a folder,
    including their structure, intensity, and training load.

    Returns:
        JSON string with workout details
    """
    assert ctx is not None
    config: ICUConfig = ctx.get_state("config")

    try:
        async with ICUClient(config) as client:
            workouts = await client.get_workouts_in_folder(folder_id)

            if not workouts:
                return ResponseBuilder.build_response(
                    data={"workouts": [], "count": 0, "folder_id": folder_id},
                    metadata={"message": f"No workouts found in folder {folder_id}"},
                )

            workouts_data = [_workout_to_dict(w) for w in workouts]

            total_duration = sum(w.moving_time or 0 for w in workouts)
            total_load = sum(w.icu_training_load or 0 for w in workouts)
            indoor_count = sum(1 for w in workouts if w.indoor)

            summary = {
                "total_workouts": len(workouts),
                "total_duration_seconds": total_duration,
                "total_training_load": total_load,
                "indoor_workouts": indoor_count,
            }

            return ResponseBuilder.build_response(
                data={"folder_id": folder_id, "workouts": workouts_data, "summary": summary},
                query_type="folder_workouts",
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )


async def get_workout(
    workout_id: Annotated[int, "Workout ID"],
    ctx: Context | None = None,
) -> str:
    """Get a single workout by ID, including its full structured definition.

    Returns all workout details including the workout_doc with intervals and targets.

    Returns:
        JSON string with workout details
    """
    assert ctx is not None
    config: ICUConfig = ctx.get_state("config")

    try:
        async with ICUClient(config) as client:
            workout = await client.get_workout(workout_id)

            return ResponseBuilder.build_response(
                data=_workout_to_dict(workout),
                query_type="get_workout",
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )


async def create_workout(
    folder_id: Annotated[int, "Folder ID to create the workout in"],
    name: Annotated[str, "Workout name"],
    workout_doc: Annotated[
        str | None,
        "JSON string of structured workout document with intervals and targets",
    ] = None,
    description: Annotated[str | None, "Workout description"] = None,
    event_type: Annotated[str | None, "Activity type (e.g., Ride, Run, Swim)"] = None,
    duration_seconds: Annotated[int | None, "Planned duration in seconds"] = None,
    distance_meters: Annotated[float | None, "Planned distance in meters"] = None,
    target: Annotated[str | None, "Target metric: AUTO, POWER, HR, or PACE"] = None,
    tags: Annotated[str | None, "Comma-separated tags (e.g., 'intervals,threshold')"] = None,
    indoor: Annotated[bool | None, "Whether this is an indoor workout"] = None,
    sub_type: Annotated[str | None, "Sub-type: NONE, COMMUTE, WARMUP, COOLDOWN, or RACE"] = None,
    day: Annotated[int | None, "Day number for placement in a training plan"] = None,
    color: Annotated[str | None, "Workout color hex code (e.g., '#FF5733')"] = None,
    ctx: Context | None = None,
) -> str:
    """Create a new workout in a folder or training plan.

    Use workout_doc to define structured intervals with power/HR/pace targets.
    The workout will appear in the folder and can be scheduled to the calendar.

    Returns:
        JSON string with created workout data
    """
    assert ctx is not None
    config: ICUConfig = ctx.get_state("config")

    try:
        workout_data: dict[str, Any] = {
            "folder_id": folder_id,
            "name": name,
        }

        if description is not None:
            workout_data["description"] = description
        if event_type is not None:
            workout_data["type"] = event_type
        if duration_seconds is not None:
            workout_data["moving_time"] = duration_seconds
        if distance_meters is not None:
            workout_data["distance"] = distance_meters
        if target is not None:
            workout_data["target"] = target.upper()
        if indoor is not None:
            workout_data["indoor"] = indoor
        if sub_type is not None:
            workout_data["sub_type"] = sub_type.upper()
        if day is not None:
            workout_data["day"] = day
        if color is not None:
            workout_data["color"] = color
        if tags is not None:
            workout_data["tags"] = [t.strip() for t in tags.split(",") if t.strip()]
        if workout_doc is not None:
            try:
                workout_data["workout_doc"] = json.loads(workout_doc)
            except json.JSONDecodeError as e:
                return ResponseBuilder.build_error_response(
                    f"Invalid workout_doc JSON: {str(e)}", error_type="validation_error"
                )

        async with ICUClient(config) as client:
            workout = await client.create_workout(workout_data)

            return ResponseBuilder.build_response(
                data=_workout_to_dict(workout),
                query_type="create_workout",
                metadata={"message": f"Successfully created workout: {name}"},
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )


async def update_workout(
    workout_id: Annotated[int, "Workout ID to update"],
    name: Annotated[str | None, "Updated workout name"] = None,
    workout_doc: Annotated[str | None, "JSON string of updated structured workout document"] = None,
    description: Annotated[str | None, "Updated description"] = None,
    event_type: Annotated[str | None, "Updated activity type"] = None,
    duration_seconds: Annotated[int | None, "Updated duration in seconds"] = None,
    distance_meters: Annotated[float | None, "Updated distance in meters"] = None,
    target: Annotated[str | None, "Updated target metric: AUTO, POWER, HR, or PACE"] = None,
    tags: Annotated[str | None, "Updated comma-separated tags"] = None,
    indoor: Annotated[bool | None, "Updated indoor flag"] = None,
    sub_type: Annotated[str | None, "Updated sub-type"] = None,
    color: Annotated[str | None, "Updated color hex code"] = None,
    hide_from_athlete: Annotated[bool | None, "Hide this workout from the athlete"] = None,
    ctx: Context | None = None,
) -> str:
    """Update an existing workout.

    Only provide the fields you want to change — others remain unchanged.

    Returns:
        JSON string with updated workout data
    """
    assert ctx is not None
    config: ICUConfig = ctx.get_state("config")

    try:
        workout_data: dict[str, Any] = {}

        if name is not None:
            workout_data["name"] = name
        if description is not None:
            workout_data["description"] = description
        if event_type is not None:
            workout_data["type"] = event_type
        if duration_seconds is not None:
            workout_data["moving_time"] = duration_seconds
        if distance_meters is not None:
            workout_data["distance"] = distance_meters
        if target is not None:
            workout_data["target"] = target.upper()
        if indoor is not None:
            workout_data["indoor"] = indoor
        if sub_type is not None:
            workout_data["sub_type"] = sub_type.upper()
        if color is not None:
            workout_data["color"] = color
        if hide_from_athlete is not None:
            workout_data["hide_from_athlete"] = hide_from_athlete
        if tags is not None:
            workout_data["tags"] = [t.strip() for t in tags.split(",") if t.strip()]
        if workout_doc is not None:
            try:
                workout_data["workout_doc"] = json.loads(workout_doc)
            except json.JSONDecodeError as e:
                return ResponseBuilder.build_error_response(
                    f"Invalid workout_doc JSON: {str(e)}", error_type="validation_error"
                )

        if not workout_data:
            return ResponseBuilder.build_error_response(
                "No fields provided to update.", error_type="validation_error"
            )

        async with ICUClient(config) as client:
            workout = await client.update_workout(workout_id, workout_data)

            return ResponseBuilder.build_response(
                data=_workout_to_dict(workout),
                query_type="update_workout",
                metadata={"message": f"Successfully updated workout {workout_id}"},
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )


async def delete_workout(
    workout_id: Annotated[int, "Workout ID to delete"],
    delete_related: Annotated[
        bool, "Also delete workouts added at the same time on a training plan"
    ] = False,
    ctx: Context | None = None,
) -> str:
    """Delete a workout from the library.

    Permanently removes a workout. Cannot be undone.

    Returns:
        JSON string with deletion confirmation
    """
    assert ctx is not None
    config: ICUConfig = ctx.get_state("config")

    try:
        async with ICUClient(config) as client:
            await client.delete_workout(workout_id, delete_related=delete_related)

            return ResponseBuilder.build_response(
                data={"workout_id": workout_id, "deleted": True},
                query_type="delete_workout",
                metadata={"message": f"Successfully deleted workout {workout_id}"},
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )


async def bulk_create_workouts(
    workouts: Annotated[
        str,
        "JSON array of workout objects. Each must have: folder_id, name. "
        "Optional: workout_doc, description, type, moving_time, distance, target, tags, indoor, day",
    ],
    ctx: Context | None = None,
) -> str:
    """Create multiple workouts in a single operation.

    More efficient than creating workouts one at a time.

    Returns:
        JSON string with created workouts and count
    """
    assert ctx is not None
    config: ICUConfig = ctx.get_state("config")

    try:
        try:
            parsed_data = json.loads(workouts)
        except json.JSONDecodeError as e:
            return ResponseBuilder.build_error_response(
                f"Invalid JSON format: {str(e)}", error_type="validation_error"
            )

        if not isinstance(parsed_data, list):
            return ResponseBuilder.build_error_response(
                "Workouts must be a JSON array", error_type="validation_error"
            )

        workouts_data: list[dict[str, Any]] = parsed_data  # type: ignore[assignment]

        for i, workout_data in enumerate(workouts_data):
            if "folder_id" not in workout_data:
                return ResponseBuilder.build_error_response(
                    f"Workout {i}: Missing required field 'folder_id'",
                    error_type="validation_error",
                )
            if "name" not in workout_data:
                return ResponseBuilder.build_error_response(
                    f"Workout {i}: Missing required field 'name'",
                    error_type="validation_error",
                )

        async with ICUClient(config) as client:
            created = await client.bulk_create_workouts(workouts_data)

            return ResponseBuilder.build_response(
                data={"workouts": [_workout_to_dict(w) for w in created]},
                query_type="bulk_create_workouts",
                metadata={
                    "message": f"Successfully created {len(created)} workouts",
                    "count": len(created),
                },
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )


async def get_workout_tags(
    ctx: Context | None = None,
) -> str:
    """List all workout tags used in the athlete's library.

    Returns:
        JSON string with list of tag strings
    """
    assert ctx is not None
    config: ICUConfig = ctx.get_state("config")

    try:
        async with ICUClient(config) as client:
            tags = await client.get_workout_tags()

            return ResponseBuilder.build_response(
                data={"tags": tags, "count": len(tags)},
                query_type="workout_tags",
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )


async def duplicate_workouts(
    workout_ids: Annotated[str, "JSON array of workout IDs to duplicate (e.g., '[101, 102]')"],
    num_copies: Annotated[int, "Number of copies to create"] = 1,
    weeks_between: Annotated[int, "Number of weeks between each copy"] = 1,
    ctx: Context | None = None,
) -> str:
    """Duplicate workouts on a training plan.

    Creates copies of the specified workouts, spaced the given number of weeks apart.
    Useful for repeating blocks in a training plan.

    Returns:
        JSON string with created workout copies
    """
    assert ctx is not None
    config: ICUConfig = ctx.get_state("config")

    try:
        try:
            ids_parsed = json.loads(workout_ids)
        except json.JSONDecodeError as e:
            return ResponseBuilder.build_error_response(
                f"Invalid JSON format: {str(e)}", error_type="validation_error"
            )

        if not isinstance(ids_parsed, list):
            return ResponseBuilder.build_error_response(
                "workout_ids must be a JSON array", error_type="validation_error"
            )

        ids_list: list[int] = ids_parsed  # type: ignore[assignment]

        async with ICUClient(config) as client:
            created = await client.duplicate_workouts(ids_list, num_copies, weeks_between)

            return ResponseBuilder.build_response(
                data={"workouts": [_workout_to_dict(w) for w in created]},
                query_type="duplicate_workouts",
                metadata={
                    "message": f"Successfully duplicated {len(ids_list)} workouts x{num_copies} copies",
                    "count": len(created),
                },
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )


async def import_workout(
    folder_id: Annotated[int, "Folder ID to import the workout into"],
    file_contents_base64: Annotated[str, "Base64-encoded file content (.zwo, .mrc, .erg, or .fit)"],
    filename: Annotated[str, "Original filename with extension (e.g., 'threshold.zwo')"],
    activity_type: Annotated[str | None, "Activity type (e.g., Ride, Run, Swim)"] = None,
    ctx: Context | None = None,
) -> str:
    """Import a workout file into a folder.

    Supports .zwo (Zwift), .mrc, .erg (ERG/MRC format), and .fit file formats.
    Provide the file contents as a base64-encoded string.

    Returns:
        JSON string with imported workout data
    """
    assert ctx is not None
    config: ICUConfig = ctx.get_state("config")

    try:
        file_bytes = base64.b64decode(file_contents_base64)
    except Exception:
        return ResponseBuilder.build_error_response(
            "Invalid base64 encoding in file_contents_base64", error_type="validation_error"
        )

    try:
        async with ICUClient(config) as client:
            workout = await client.import_workout(
                folder_id, file_bytes, filename, activity_type=activity_type
            )

            return ResponseBuilder.build_response(
                data=_workout_to_dict(workout),
                query_type="import_workout",
                metadata={"message": f"Successfully imported workout from {filename}"},
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )


async def export_workout(
    workout_id: Annotated[int, "Workout ID to export"],
    format: Annotated[str, "Export format: zwo, mrc, erg, or fit"],
    ctx: Context | None = None,
) -> str:
    """Export a workout to a file format.

    Converts a workout to .zwo (Zwift), .mrc, .erg, or .fit format.
    Returns the file content as a base64-encoded string.

    Returns:
        JSON string with filename and base64-encoded file content
    """
    assert ctx is not None
    config: ICUConfig = ctx.get_state("config")

    valid_formats = ["zwo", "mrc", "erg", "fit"]
    fmt = format.lower().lstrip(".")
    if fmt not in valid_formats:
        return ResponseBuilder.build_error_response(
            f"Invalid format. Must be one of: {', '.join(valid_formats)}",
            error_type="validation_error",
        )

    try:
        async with ICUClient(config) as client:
            workout = await client.get_workout(workout_id)
            workout_dict = _workout_to_dict(workout)
            file_bytes = await client.download_workout(workout_dict, fmt)

            encoded = base64.b64encode(file_bytes).decode("utf-8")
            workout_name = (workout.name or str(workout_id)).replace(" ", "_")
            filename = f"{workout_name}.{fmt}"

            return ResponseBuilder.build_response(
                data={
                    "workout_id": workout_id,
                    "filename": filename,
                    "format": fmt,
                    "file_contents_base64": encoded,
                    "size_bytes": len(file_bytes),
                },
                query_type="export_workout",
                metadata={"message": f"Successfully exported workout {workout_id} as {filename}"},
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )


async def download_all_workouts(
    ctx: Context | None = None,
) -> str:
    """Download all workouts in the library as a ZIP archive.

    Returns the ZIP file as a base64-encoded string. Useful for backup
    or transferring workouts to another platform.

    Returns:
        JSON string with base64-encoded ZIP file
    """
    assert ctx is not None
    config: ICUConfig = ctx.get_state("config")

    try:
        async with ICUClient(config) as client:
            zip_bytes = await client.download_workouts_zip()

            encoded = base64.b64encode(zip_bytes).decode("utf-8")

            return ResponseBuilder.build_response(
                data={
                    "filename": "workouts.zip",
                    "file_contents_base64": encoded,
                    "size_bytes": len(zip_bytes),
                },
                query_type="download_all_workouts",
                metadata={"message": "Successfully downloaded all workouts as ZIP"},
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )
