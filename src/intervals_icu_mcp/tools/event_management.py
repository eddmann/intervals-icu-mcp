"""Event/calendar management tools for Intervals.icu MCP server."""

import re
from datetime import datetime
from typing import Annotated, Any

from fastmcp import Context

from ..auth import ICUConfig
from ..client import ICUAPIError, ICUClient
from ..response_builder import ResponseBuilder


def _detect_primary_metric(description: str | None) -> str:
    """Identify which target metric dominates a workout description.

    Returns one of: "power", "heart_rate", "pace", "zone_only" (when only Z1-Z6
    appear with no explicit metric markers — the device uses the sport default),
    or "unknown" (no description).

    The detection is intentionally simple — it looks for unambiguous markers and
    falls back to "zone_only". A workout with mixed metrics returns the highest-
    count explicit category; that's not a bug, just an honest summary of what
    the description contains.
    """
    if not description:
        return "unknown"

    hr_markers = re.findall(r"\bHR\b|\bbpm\b|%\s*HR\b", description, flags=re.IGNORECASE)
    pace_markers = re.findall(r"/km\b|/mi\b|min/km", description, flags=re.IGNORECASE)
    # Power: bare watts (e.g. "250w") or % NOT followed by " HR".
    power_markers = re.findall(
        r"\b\d+\s*w\b|\b\d+%(?!\s*HR)|FTP", description, flags=re.IGNORECASE
    )

    counts = {
        "power": len(power_markers),
        "heart_rate": len(hr_markers),
        "pace": len(pace_markers),
    }
    if sum(counts.values()) == 0:
        return "zone_only"
    return max(counts, key=lambda k: counts[k])


def _build_summary_line(
    name: str,
    event_type: str | None,
    duration_seconds: int | None,
    description: str | None,
) -> str:
    """Single-line human-readable echo of what was just created.

    Purpose: surface the prescription type (power / HR / pace / zone) at the
    moment of creation so the user notices a wrong metric at "push to calendar"
    rather than at "lace up at km 0". Today's case: a run scheduled with power
    targets for Z1-Z2 steps would have shown "POWER-based" here and got fixed
    before the run started.
    """
    sport_label = event_type or "workout"
    if duration_seconds and duration_seconds > 0:
        minutes = duration_seconds // 60
        duration_label = f"~{minutes} min"
    else:
        duration_label = "no duration set"

    metric = _detect_primary_metric(description)
    metric_label = {
        "power": "POWER-based",
        "heart_rate": "HR-based",
        "pace": "PACE-based",
        "zone_only": "zone-based (uses sport's default metric)",
        "unknown": "no description provided",
    }[metric]

    return f"Created '{name}' — {sport_label}, {duration_label}, primarily {metric_label}."


async def create_event(
    start_date: Annotated[str, "Start date in YYYY-MM-DD format"],
    name: Annotated[str, "Event name"],
    category: Annotated[str, "Event category: WORKOUT, NOTE, RACE, or GOAL"],
    description: Annotated[str | None, "Event description. For WORKOUT events, use intervals.icu workout text syntax to create structured workouts with colored zone blocks. Format: section headers (Warmup/Main Set/Cooldown) on own lines, steps start with '- '. Power: N% (of FTP), Nw (watts), ZN (zone). HR: N% HR, ZN HR. Duration: Nm, Ns, Nh. Repeats: 'Main Set 3x'. Ramps: 'ramp 50-75%'. Cadence: Nrpm. Example: 'Warmup\\n- 10m 55%\\n\\nMain Set 3x\\n- 5m 95-105%\\n- 3m 50%\\n\\nCooldown\\n- 10m 45%'"] = None,
    event_type: Annotated[str | None, "Activity type (e.g., Ride, Run, Swim)"] = None,
    duration_seconds: Annotated[int | None, "Planned duration in seconds"] = None,
    distance_meters: Annotated[float | None, "Planned distance in meters"] = None,
    training_load: Annotated[int | None, "Planned training load"] = None,
    ctx: Context | None = None,
) -> str:
    """Create a new calendar event (planned workout, note, race, or goal).

    Adds an event to your Intervals.icu calendar. Events can be workouts with
    planned metrics, notes for tracking information, races, or training goals.

    For structured workouts with colored zone blocks, put workout steps in the
    description field using intervals.icu text syntax. The server will parse it
    and generate the visual workout structure automatically.

    Args:
        start_date: Date in ISO-8601 format (YYYY-MM-DD)
        name: Name of the event
        category: Type of event - WORKOUT, NOTE, RACE, or GOAL
        description: For workouts, use intervals.icu text syntax for structured steps
        event_type: Activity type (e.g., "Ride", "Run", "Swim") for workouts
        duration_seconds: Planned duration for workouts
        distance_meters: Planned distance for workouts
        training_load: Planned training load for workouts

    Returns:
        JSON string with created event data
    """
    assert ctx is not None
    config: ICUConfig = ctx.get_state("config")

    # Validate category
    valid_categories = ["WORKOUT", "NOTE", "RACE", "GOAL"]
    if category.upper() not in valid_categories:
        return ResponseBuilder.build_error_response(
            f"Invalid category. Must be one of: {', '.join(valid_categories)}",
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

    try:
        # Build event data
        event_data: dict[str, Any] = {
            "start_date_local": f"{start_date}T00:00:00",
            "name": name,
            "category": category.upper(),
        }

        if description:
            event_data["description"] = description
        if event_type:
            event_data["type"] = event_type
        if duration_seconds:
            event_data["moving_time"] = duration_seconds
        if distance_meters:
            event_data["distance"] = distance_meters
        if training_load:
            event_data["icu_training_load"] = training_load

        async with ICUClient(config) as client:
            event = await client.create_event(event_data)

            event_result: dict[str, Any] = {
                "id": event.id,
                "start_date": event.start_date_local,
                "name": event.name,
                "category": event.category,
            }

            if event.description:
                event_result["description"] = event.description
            if event.type:
                event_result["type"] = event.type
            if event.moving_time:
                event_result["duration_seconds"] = event.moving_time
            if event.distance:
                event_result["distance_meters"] = event.distance
            if event.icu_training_load:
                event_result["training_load"] = event.icu_training_load

            summary_line = _build_summary_line(
                name=name,
                event_type=event_type,
                duration_seconds=duration_seconds,
                description=description,
            )
            return ResponseBuilder.build_response(
                data=event_result,
                query_type="create_event",
                metadata={
                    "message": f"Successfully created {category.lower()}: {name}",
                    "summary_line": summary_line,
                },
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
    description: Annotated[str | None, "Updated description"] = None,
    start_date: Annotated[str | None, "Updated start date (YYYY-MM-DD)"] = None,
    event_type: Annotated[str | None, "Updated activity type"] = None,
    duration_seconds: Annotated[int | None, "Updated duration in seconds"] = None,
    distance_meters: Annotated[float | None, "Updated distance in meters"] = None,
    training_load: Annotated[int | None, "Updated training load"] = None,
    ctx: Context | None = None,
) -> str:
    """Update an existing calendar event.

    Modifies one or more fields of an existing event. Only provide the fields
    you want to change - other fields will remain unchanged.

    Args:
        event_id: ID of the event to update
        name: New name for the event
        description: New description
        start_date: New start date in YYYY-MM-DD format
        event_type: New activity type
        duration_seconds: New planned duration
        distance_meters: New planned distance
        training_load: New planned training load

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

    try:
        # Build update data (only include provided fields)
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

        if not event_data:
            return ResponseBuilder.build_error_response(
                "No fields provided to update. Please specify at least one field to change.",
                error_type="validation_error",
            )

        async with ICUClient(config) as client:
            event = await client.update_event(event_id, event_data)

            event_result: dict[str, Any] = {
                "id": event.id,
                "start_date": event.start_date_local,
                "name": event.name,
                "category": event.category,
            }

            if event.description:
                event_result["description"] = event.description
            if event.type:
                event_result["type"] = event.type
            if event.moving_time:
                event_result["duration_seconds"] = event.moving_time
            if event.distance:
                event_result["distance_meters"] = event.distance
            if event.icu_training_load:
                event_result["training_load"] = event.icu_training_load

            return ResponseBuilder.build_response(
                data=event_result,
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

    Args:
        event_id: ID of the event to delete

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
        "JSON string containing array of events. Each event should have: start_date_local, name, category, and optional fields like description, type, moving_time, distance, icu_training_load",
    ],
    ctx: Context | None = None,
) -> str:
    """Create multiple calendar events in a single operation.

    This is more efficient than creating events one at a time. Provide a JSON array
    of event objects, each with the same structure as create_event.

    Args:
        events: JSON array of event objects to create

    Returns:
        JSON string with created events
    """
    assert ctx is not None
    config: ICUConfig = ctx.get_state("config")

    try:
        import json

        # Parse the JSON string
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

        # Type cast after validation
        events_data: list[dict[str, Any]] = parsed_data  # type: ignore[assignment]

        # Validate each event
        valid_categories = ["WORKOUT", "NOTE", "RACE", "GOAL"]
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
            if event_data["category"].upper() not in valid_categories:
                return ResponseBuilder.build_error_response(
                    f"Event {i}: Invalid category. Must be one of: {', '.join(valid_categories)}",
                    error_type="validation_error",
                )

            # Normalize category to uppercase
            event_data["category"] = event_data["category"].upper()

            # Validate date format and convert to full datetime
            try:
                datetime.strptime(event_data["start_date_local"], "%Y-%m-%d")
                event_data["start_date_local"] = f"{event_data['start_date_local']}T00:00:00"
            except ValueError:
                return ResponseBuilder.build_error_response(
                    f"Event {i}: Invalid date format. Please use YYYY-MM-DD format.",
                    error_type="validation_error",
                )

        async with ICUClient(config) as client:
            created_events = await client.bulk_create_events(events_data)

            events_result: list[dict[str, Any]] = []
            for event in created_events:
                event_info: dict[str, Any] = {
                    "id": event.id,
                    "start_date": event.start_date_local,
                    "name": event.name,
                    "category": event.category,
                }

                if event.description:
                    event_info["description"] = event.description
                if event.type:
                    event_info["type"] = event.type
                if event.moving_time:
                    event_info["duration_seconds"] = event.moving_time
                if event.distance:
                    event_info["distance_meters"] = event.distance
                if event.icu_training_load:
                    event_info["training_load"] = event.icu_training_load

                events_result.append(event_info)

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

    This is more efficient than deleting events one at a time. Provide a JSON array
    of event IDs to delete.

    Args:
        event_ids: JSON array of event IDs (integers)

    Returns:
        JSON string with deletion confirmation
    """
    assert ctx is not None
    config: ICUConfig = ctx.get_state("config")

    try:
        import json

        # Parse the JSON string
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

        # Type cast after validation
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

    Creates a copy of an event with all its properties (name, type, duration, etc.)
    but with a new date. Useful for repeating workouts or events.

    Args:
        event_id: ID of the event to duplicate
        new_date: New date in YYYY-MM-DD format

    Returns:
        JSON string with the duplicated event
    """
    assert ctx is not None
    config: ICUConfig = ctx.get_state("config")

    # Validate date format
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

            event_result: dict[str, Any] = {
                "id": duplicated_event.id,
                "start_date": duplicated_event.start_date_local,
                "name": duplicated_event.name,
                "category": duplicated_event.category,
                "original_event_id": event_id,
            }

            if duplicated_event.description:
                event_result["description"] = duplicated_event.description
            if duplicated_event.type:
                event_result["type"] = duplicated_event.type
            if duplicated_event.moving_time:
                event_result["duration_seconds"] = duplicated_event.moving_time
            if duplicated_event.distance:
                event_result["distance_meters"] = duplicated_event.distance
            if duplicated_event.icu_training_load:
                event_result["training_load"] = duplicated_event.icu_training_load

            return ResponseBuilder.build_response(
                data=event_result,
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
