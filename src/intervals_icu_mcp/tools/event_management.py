"""Event/calendar management tools for Intervals.icu MCP server."""

import json
from datetime import datetime
from typing import Annotated, Any

from fastmcp import Context

from ..auth import ICUConfig
from ..client import ICUAPIError, ICUClient
from ..models import Event
from ..response_builder import ResponseBuilder

VALID_CATEGORIES = [
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

VALID_TARGETS = ["AUTO", "POWER", "HR", "PACE"]
VALID_SUB_TYPES = ["NONE", "COMMUTE", "WARMUP", "COOLDOWN", "RACE"]


def _event_to_dict(event: Event) -> dict[str, Any]:
    """Build a response dict from an Event model, including all populated fields."""
    result: dict[str, Any] = {
        "id": event.id,
        "start_date": event.start_date_local,
        "name": event.name,
        "category": event.category,
    }
    if event.description:
        result["description"] = event.description
    if event.type:
        result["type"] = event.type
    if event.moving_time:
        result["duration_seconds"] = event.moving_time
    if event.distance:
        result["distance_meters"] = event.distance
    if event.icu_training_load:
        result["training_load"] = event.icu_training_load
    if event.color:
        result["color"] = event.color
    if event.indoor is not None:
        result["indoor"] = event.indoor
    if event.target:
        result["target"] = event.target
    if event.tags:
        result["tags"] = event.tags
    if event.sub_type:
        result["sub_type"] = event.sub_type
    if event.load_target:
        result["load_target"] = event.load_target
    if event.time_target:
        result["time_target"] = event.time_target
    if event.workout_doc:
        result["workout_doc"] = event.workout_doc
    return result


async def create_event(
    start_date: Annotated[str, "Start date in YYYY-MM-DD format"],
    name: Annotated[str, "Event name"],
    category: Annotated[
        str,
        "Event category: WORKOUT, RACE_A, RACE_B, RACE_C, NOTE, PLAN, HOLIDAY, SICK, INJURED, "
        "SET_EFTP, FITNESS_DAYS, SEASON_START, TARGET, or SET_FITNESS",
    ],
    description: Annotated[
        str | None,
        "Event description OR Intervals.icu workout text syntax for structured workouts. "
        "To create a structured workout with power targets and visual bars, use the text syntax: "
        "group headers as plain text lines, steps starting with '- <duration> <zone/power>'. "
        "Duration formats: '10m', '30s', '1h30m'. Power: 'Z1'-'Z7' (zones), '80%' (FTP%), '200w', '179-243w' (range). "
        "Repeats: '3x' before a group. "
        "Example: 'Warmup\\n- 10m Z1\\n\\nMain Set\\n- 20m Z4\\n\\nCooldown\\n- 10m Z1'. "
        "The API parses this into a full structured workout_doc automatically.",
    ] = None,
    event_type: Annotated[str | None, "Activity type (e.g., Ride, Run, Swim)"] = None,
    duration_seconds: Annotated[int | None, "Planned duration in seconds"] = None,
    distance_meters: Annotated[float | None, "Planned distance in meters"] = None,
    training_load: Annotated[int | None, "Planned training load"] = None,
    workout_doc: Annotated[
        str | None,
        "JSON string of structured workout document. NOTE: Direct workout_doc JSON has limited "
        "API support and does not render in the UI. Use the description field with Intervals.icu "
        "text syntax instead to create structured workouts.",
    ] = None,
    tags: Annotated[
        str | None,
        "Comma-separated tags (e.g., 'intervals,threshold'). "
        "NOTE: Do NOT add tags unless the user explicitly requests them. "
        "Tags render as visible hashtags on the event name in the UI, which is distracting.",
    ] = None,
    indoor: Annotated[bool | None, "Whether this is an indoor workout"] = None,
    target: Annotated[str | None, "Target metric: AUTO, POWER, HR, or PACE"] = None,
    sub_type: Annotated[str | None, "Sub-type: NONE, COMMUTE, WARMUP, COOLDOWN, or RACE"] = None,
    load_target: Annotated[int | None, "Target training load"] = None,
    time_target: Annotated[int | None, "Target time in seconds"] = None,
    color: Annotated[str | None, "Event color hex code (e.g., '#FF5733')"] = None,
    ctx: Context | None = None,
) -> str:
    """Create a new calendar event (planned workout, note, race, goal, etc.).

    Adds an event to your Intervals.icu calendar. Supports the full range of event
    categories and optional structured workout definitions via workout_doc.

    Returns:
        JSON string with created event data
    """
    assert ctx is not None
    config: ICUConfig = ctx.get_state("config")

    # Validate category
    if category.upper() not in VALID_CATEGORIES:
        return ResponseBuilder.build_error_response(
            f"Invalid category. Must be one of: {', '.join(VALID_CATEGORIES)}",
            error_type="validation_error",
        )

    # Validate date format
    try:
        datetime.strptime(start_date, "%Y-%m-%d")
    except ValueError:
        return ResponseBuilder.build_error_response(
            "Invalid date format. Please use YYYY-MM-DD format.",
            error_type="validation_error",
        )

    # Validate target if provided
    if target and target.upper() not in VALID_TARGETS:
        return ResponseBuilder.build_error_response(
            f"Invalid target. Must be one of: {', '.join(VALID_TARGETS)}",
            error_type="validation_error",
        )

    # Validate sub_type if provided
    if sub_type and sub_type.upper() not in VALID_SUB_TYPES:
        return ResponseBuilder.build_error_response(
            f"Invalid sub_type. Must be one of: {', '.join(VALID_SUB_TYPES)}",
            error_type="validation_error",
        )

    try:
        event_data: dict[str, Any] = {
            "start_date_local": start_date + "T00:00:00",
            "name": name,
            "category": category.upper(),
        }

        if description is not None:
            event_data["description"] = description
        if event_type is not None:
            event_data["type"] = event_type
        if duration_seconds is not None:
            event_data["moving_time"] = duration_seconds
        if distance_meters is not None:
            event_data["distance"] = distance_meters
        if training_load is not None:
            event_data["icu_training_load"] = training_load
        if color is not None:
            event_data["color"] = color
        if indoor is not None:
            event_data["indoor"] = indoor
        if target is not None:
            event_data["target"] = target.upper()
        if sub_type is not None:
            event_data["sub_type"] = sub_type.upper()
        if load_target is not None:
            event_data["load_target"] = load_target
        if time_target is not None:
            event_data["time_target"] = time_target
        if tags is not None:
            event_data["tags"] = [t.strip() for t in tags.split(",") if t.strip()]
        if workout_doc is not None:
            try:
                event_data["workout_doc"] = json.loads(workout_doc)
            except json.JSONDecodeError as e:
                return ResponseBuilder.build_error_response(
                    f"Invalid workout_doc JSON: {str(e)}", error_type="validation_error"
                )

        async with ICUClient(config) as client:
            event = await client.create_event(event_data)

            return ResponseBuilder.build_response(
                data=_event_to_dict(event),
                query_type="create_event",
                metadata={"message": f"Successfully created {category.lower()}: {name}"},
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )


async def update_event(
    event_id: Annotated[int, "Event ID to update"],
    name: Annotated[str | None, "Updated event name"] = None,
    description: Annotated[
        str | None,
        "Updated description OR Intervals.icu workout text syntax for structured workouts. "
        "To create a structured workout with power targets and visual bars, use the text syntax: "
        "group headers as plain text lines, steps starting with '- <duration> <zone/power>'. "
        "Duration formats: '10m', '30s', '1h30m'. Power: 'Z1'-'Z7' (zones), '80%' (FTP%), '200w', '179-243w' (range). "
        "Repeats: '3x' before a group. "
        "Example: 'Warmup\\n- 10m Z1\\n\\nMain Set\\n- 20m Z4\\n\\nCooldown\\n- 10m Z1'. "
        "The API parses this into a full structured workout_doc automatically.",
    ] = None,
    start_date: Annotated[str | None, "Updated start date (YYYY-MM-DD)"] = None,
    event_type: Annotated[str | None, "Updated activity type"] = None,
    duration_seconds: Annotated[int | None, "Updated duration in seconds"] = None,
    distance_meters: Annotated[float | None, "Updated distance in meters"] = None,
    training_load: Annotated[int | None, "Updated training load"] = None,
    workout_doc: Annotated[
        str | None,
        "JSON string of updated structured workout document. NOTE: Direct workout_doc JSON has "
        "limited API support and does not render in the UI. Use the description field with "
        "Intervals.icu text syntax instead to create structured workouts.",
    ] = None,
    tags: Annotated[str | None, "Updated comma-separated tags"] = None,
    indoor: Annotated[bool | None, "Whether this is an indoor workout"] = None,
    target: Annotated[str | None, "Updated target metric: AUTO, POWER, HR, or PACE"] = None,
    sub_type: Annotated[
        str | None, "Updated sub-type: NONE, COMMUTE, WARMUP, COOLDOWN, or RACE"
    ] = None,
    load_target: Annotated[int | None, "Updated target training load"] = None,
    time_target: Annotated[int | None, "Updated target time in seconds"] = None,
    color: Annotated[str | None, "Updated event color hex code"] = None,
    ctx: Context | None = None,
) -> str:
    """Update an existing calendar event.

    Modifies one or more fields of an existing event. Only provide the fields
    you want to change — other fields will remain unchanged.

    Returns:
        JSON string with updated event data
    """
    assert ctx is not None
    config: ICUConfig = ctx.get_state("config")

    # Validate date format if provided
    if start_date:
        try:
            datetime.strptime(start_date, "%Y-%m-%d")
        except ValueError:
            return ResponseBuilder.build_error_response(
                "Invalid date format. Please use YYYY-MM-DD format.",
                error_type="validation_error",
            )

    # Validate target if provided
    if target and target.upper() not in VALID_TARGETS:
        return ResponseBuilder.build_error_response(
            f"Invalid target. Must be one of: {', '.join(VALID_TARGETS)}",
            error_type="validation_error",
        )

    # Validate sub_type if provided
    if sub_type and sub_type.upper() not in VALID_SUB_TYPES:
        return ResponseBuilder.build_error_response(
            f"Invalid sub_type. Must be one of: {', '.join(VALID_SUB_TYPES)}",
            error_type="validation_error",
        )

    try:
        event_data: dict[str, Any] = {}

        if name is not None:
            event_data["name"] = name
        if description is not None:
            event_data["description"] = description
        if start_date is not None:
            event_data["start_date_local"] = f"{start_date}T00:00:00"
        if event_type is not None:
            event_data["type"] = event_type
        if duration_seconds is not None:
            event_data["moving_time"] = duration_seconds
        if distance_meters is not None:
            event_data["distance"] = distance_meters
        if training_load is not None:
            event_data["icu_training_load"] = training_load
        if color is not None:
            event_data["color"] = color
        if indoor is not None:
            event_data["indoor"] = indoor
        if target is not None:
            event_data["target"] = target.upper()
        if sub_type is not None:
            event_data["sub_type"] = sub_type.upper()
        if load_target is not None:
            event_data["load_target"] = load_target
        if time_target is not None:
            event_data["time_target"] = time_target
        if tags is not None:
            event_data["tags"] = [t.strip() for t in tags.split(",") if t.strip()]
        if workout_doc is not None:
            try:
                event_data["workout_doc"] = json.loads(workout_doc)
            except json.JSONDecodeError as e:
                return ResponseBuilder.build_error_response(
                    f"Invalid workout_doc JSON: {str(e)}", error_type="validation_error"
                )

        if not event_data:
            return ResponseBuilder.build_error_response(
                "No fields provided to update. Please specify at least one field to change.",
                error_type="validation_error",
            )

        async with ICUClient(config) as client:
            event = await client.update_event(event_id, event_data)

            return ResponseBuilder.build_response(
                data=_event_to_dict(event),
                query_type="update_event",
                metadata={"message": f"Successfully updated event {event_id}"},
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )


async def delete_event(
    event_id: Annotated[int, "Event ID to delete"],
    ctx: Context | None = None,
) -> str:
    """Delete a calendar event.

    Permanently removes an event from your calendar. This action cannot be undone.

    Returns:
        JSON string with deletion confirmation
    """
    assert ctx is not None
    config: ICUConfig = ctx.get_state("config")

    try:
        async with ICUClient(config) as client:
            success = await client.delete_event(event_id)

            if success:
                return ResponseBuilder.build_response(
                    data={"event_id": event_id, "deleted": True},
                    query_type="delete_event",
                    metadata={"message": f"Successfully deleted event {event_id}"},
                )
            else:
                return ResponseBuilder.build_error_response(
                    f"Failed to delete event {event_id}",
                    error_type="api_error",
                )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )


async def bulk_create_events(
    events: Annotated[
        str,
        "JSON array of event objects. Each must have: start_date_local, name, category. "
        "Optional: description, type, moving_time, distance, icu_training_load, workout_doc, tags, indoor",
    ],
    ctx: Context | None = None,
) -> str:
    """Create multiple calendar events in a single operation.

    More efficient than creating events one at a time. Provide a JSON array of event objects.

    Returns:
        JSON string with created events and count
    """
    assert ctx is not None
    config: ICUConfig = ctx.get_state("config")

    try:
        try:
            parsed_data = json.loads(events)
        except json.JSONDecodeError as e:
            return ResponseBuilder.build_error_response(
                f"Invalid JSON format: {str(e)}", error_type="validation_error"
            )

        if not isinstance(parsed_data, list):
            return ResponseBuilder.build_error_response(
                "Events must be a JSON array", error_type="validation_error"
            )

        events_data: list[dict[str, Any]] = parsed_data  # type: ignore[assignment]

        # Validate each event
        for i, event_data in enumerate(events_data):
            if "start_date_local" not in event_data:
                return ResponseBuilder.build_error_response(
                    f"Event {i}: Missing required field 'start_date_local'",
                    error_type="validation_error",
                )
            if "name" not in event_data:
                return ResponseBuilder.build_error_response(
                    f"Event {i}: Missing required field 'name'", error_type="validation_error"
                )
            if "category" not in event_data:
                return ResponseBuilder.build_error_response(
                    f"Event {i}: Missing required field 'category'",
                    error_type="validation_error",
                )
            if event_data["category"].upper() not in VALID_CATEGORIES:
                return ResponseBuilder.build_error_response(
                    f"Event {i}: Invalid category. Must be one of: {', '.join(VALID_CATEGORIES)}",
                    error_type="validation_error",
                )

            event_data["category"] = event_data["category"].upper()

            try:
                datetime.strptime(event_data["start_date_local"], "%Y-%m-%d")
                event_data["start_date_local"] = f"{event_data['start_date_local']}T00:00:00"
            except ValueError:
                return ResponseBuilder.build_error_response(
                    f"Event {i}: Invalid date format. Please use YYYY-MM-DD format.",
                    error_type="validation_error",
                )

            # API requires full datetime format
            event_data["start_date_local"] = event_data["start_date_local"] + "T00:00:00"

        async with ICUClient(config) as client:
            created_events = await client.bulk_create_events(events_data)

            events_result = [_event_to_dict(event) for event in created_events]

            return ResponseBuilder.build_response(
                data={"events": events_result},
                query_type="bulk_create_events",
                metadata={
                    "message": f"Successfully created {len(created_events)} events",
                    "count": len(created_events),
                },
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )


async def bulk_delete_events(
    event_ids: Annotated[str, "JSON array of event IDs to delete (e.g., '[123, 456, 789]')"],
    ctx: Context | None = None,
) -> str:
    """Delete multiple calendar events in a single operation.

    More efficient than deleting events one at a time.

    Returns:
        JSON string with deletion confirmation
    """
    assert ctx is not None
    config: ICUConfig = ctx.get_state("config")

    try:
        try:
            parsed_data = json.loads(event_ids)
        except json.JSONDecodeError as e:
            return ResponseBuilder.build_error_response(
                f"Invalid JSON format: {str(e)}", error_type="validation_error"
            )

        if not isinstance(parsed_data, list):
            return ResponseBuilder.build_error_response(
                "Event IDs must be a JSON array", error_type="validation_error"
            )

        if not parsed_data:
            return ResponseBuilder.build_error_response(
                "Must provide at least one event ID to delete", error_type="validation_error"
            )

        ids_list: list[int] = parsed_data  # type: ignore[assignment]

        async with ICUClient(config) as client:
            result = await client.bulk_delete_events(ids_list)

            return ResponseBuilder.build_response(
                data={"deleted_count": len(ids_list), "event_ids": ids_list, "result": result},
                query_type="bulk_delete_events",
                metadata={"message": f"Successfully deleted {len(ids_list)} events"},
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )


async def duplicate_event(
    event_id: Annotated[int, "Event ID to duplicate"],
    new_date: Annotated[str, "New date for the duplicated event (YYYY-MM-DD format)"],
    ctx: Context | None = None,
) -> str:
    """Duplicate an existing event to a new date.

    Creates a copy of an event with all its properties (name, type, duration, workout_doc, etc.)
    but on a new date. Useful for repeating workouts.

    Returns:
        JSON string with the duplicated event
    """
    assert ctx is not None
    config: ICUConfig = ctx.get_state("config")

    try:
        datetime.strptime(new_date, "%Y-%m-%d")
    except ValueError:
        return ResponseBuilder.build_error_response(
            "Invalid date format. Please use YYYY-MM-DD format.",
            error_type="validation_error",
        )

    try:
        async with ICUClient(config) as client:
            duplicated_event = await client.duplicate_event(event_id, f"{new_date}T00:00:00")

            result = _event_to_dict(duplicated_event)
            result["original_event_id"] = event_id

            return ResponseBuilder.build_response(
                data=result,
                query_type="duplicate_event",
                metadata={
                    "message": f"Successfully duplicated event {event_id} to {new_date}",
                    "original_event_id": event_id,
                },
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )
