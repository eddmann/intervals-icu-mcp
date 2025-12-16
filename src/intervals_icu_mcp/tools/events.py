"""Calendar and event tools for Intervals.icu MCP server."""

from datetime import datetime, timedelta
from typing import Annotated, Any

from fastmcp import Context

from ..auth import ICUConfig
from ..client import ICUAPIError, ICUClient
from ..response_builder import ResponseBuilder


def _normalize_date_str(date_str: str) -> str:
    """Normalize various ISO date/datetime inputs to YYYY-MM-DD."""
    if not date_str:
        return date_str

    # Accept datetime/date objects as well
    if isinstance(date_str, datetime):
        return date_str.date().isoformat()

    # Normalize whitespace and ensure string
    s = str(date_str).strip()

    # Fast-path for already date-only strings
    if len(s) == 10 and s[4] == "-" and s[7] == "-":
        return s

    # Try ISO parsing with various fallbacks to be robust against formats
    try:
        # datetime.fromisoformat doesn't accept trailing 'Z', replace with +00:00
        if s.endswith("Z"):
            s2 = s[:-1] + "+00:00"
        else:
            s2 = s
        dt = datetime.fromisoformat(s2)
        return dt.date().isoformat()
    except Exception:
        # Handle common variations via strptime patterns
        fmts = [
            "%Y-%m-%d",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M%z",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M",
        ]
        for fmt in fmts:
            try:
                dt = datetime.strptime(s if "%z" not in fmt else (s.replace("Z", "+0000") if s.endswith("Z") else s), fmt)
                return dt.date().isoformat()
            except Exception:
                continue

    # If parsing fails, return original string (best-effort)
    return s


async def get_calendar_events(
    days_ahead: Annotated[int, "Number of days to look ahead"] = 7,
    days_back: Annotated[int, "Number of days to look back"] = 0,
    ctx: Context | None = None,
) -> str:
    """Get planned events and workouts from the calendar.

    Returns calendar events including planned workouts, notes, races, and goals
    for the specified time period.

    Args:
        days_ahead: Number of days to look ahead (default 7)
        days_back: Number of days to look back (default 0)

    Returns:
        JSON string with calendar events
    """
    assert ctx is not None
    config: ICUConfig = ctx.get_state("config")

    try:
        # Calculate date range
        oldest_date = datetime.now() - timedelta(days=days_back)
        newest_date = datetime.now() + timedelta(days=days_ahead)

        oldest = oldest_date.strftime("%Y-%m-%d")
        newest = newest_date.strftime("%Y-%m-%d")

        async with ICUClient(config) as client:
            events = await client.get_events(
                oldest=oldest,
                newest=newest,
            )

            if not events:
                return ResponseBuilder.build_response(
                    data={
                        "events": [],
                        "count": 0,
                        "date_range": {"oldest": oldest, "newest": newest},
                    },
                    metadata={
                        "message": "No events found on your calendar for the specified period"
                    },
                )

            # Normalize start dates and sort by date
            events.sort(key=lambda x: _normalize_date_str(x.start_date_local))

            # Group events by date
            events_by_date: dict[str, list[dict[str, Any]]] = {}
            for event in events:
                date = _normalize_date_str(event.start_date_local)
                if date not in events_by_date:
                    events_by_date[date] = []

                # Determine relative timing
                try:
                    date_obj = datetime.strptime(date, "%Y-%m-%d").date()
                except Exception:
                    # Fall back to parsing any ISO datetime-like string
                    if date.endswith("Z"):
                        date = date[:-1] + "+00:00"
                    date_obj = datetime.fromisoformat(date).date()
                today = datetime.now().date()

                if date_obj == today:
                    relative_timing = "today"
                elif date_obj < today:
                    days_ago = (today - date_obj).days
                    relative_timing = f"{days_ago}_days_ago"
                else:
                    days_until = (date_obj - today).days
                    relative_timing = f"in_{days_until}_days"

                event_item: dict[str, Any] = {
                    "date": date,
                    "relative_timing": relative_timing,
                    "name": event.name or event.category or "Event",
                    "category": event.category,
                }

                if event.type:
                    event_item["type"] = event.type

                # Workout details
                if event.category == "WORKOUT":
                    if event.distance or event.distance_target:
                        distance = event.distance or event.distance_target
                        if distance:
                            event_item["distance_meters"] = distance

                    if event.moving_time:
                        event_item["duration_seconds"] = event.moving_time

                    if event.icu_training_load:
                        event_item["training_load"] = event.icu_training_load

                    if event.icu_intensity:
                        event_item["intensity_factor"] = event.icu_intensity

                # Description
                if event.description:
                    event_item["description"] = event.description.strip()

                events_by_date[date].append(event_item)

            # Calculate summary
            workout_count = sum(1 for e in events if e.category == "WORKOUT")
            race_count = sum(1 for e in events if e.category == "RACE")
            note_count = sum(1 for e in events if e.category == "NOTE")
            goal_count = sum(1 for e in events if e.category == "GOAL")

            summary = {
                "total_events": len(events),
                "by_category": {
                    "workouts": workout_count,
                    "races": race_count,
                    "notes": note_count,
                    "goals": goal_count,
                },
            }

            return ResponseBuilder.build_response(
                data={
                    "events_by_date": events_by_date,
                    "date_range": {"oldest": oldest, "newest": newest},
                    "summary": summary,
                },
                query_type="calendar_events",
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )


async def get_upcoming_workouts(
    limit: Annotated[int, "Maximum number of workouts to return"] = 7,
    ctx: Context | None = None,
) -> str:
    """Get upcoming planned workouts from the calendar.

    Returns only workout events (filters out notes, races, goals) for the
    upcoming days. Useful for seeing what training is planned ahead.

    Args:
        limit: Maximum number of workouts to return (default 7)

    Returns:
        JSON string with upcoming workouts
    """
    assert ctx is not None
    config: ICUConfig = ctx.get_state("config")

    try:
        # Look ahead 30 days to find workouts
        oldest = datetime.now().strftime("%Y-%m-%d")
        newest_date = datetime.now() + timedelta(days=30)
        newest = newest_date.strftime("%Y-%m-%d")

        async with ICUClient(config) as client:
            events = await client.get_events(
                oldest=oldest,
                newest=newest,
            )

            # Filter for workouts only
            workouts = [e for e in events if e.category == "WORKOUT"]

            if not workouts:
                return ResponseBuilder.build_response(
                    data={"workouts": [], "count": 0},
                    metadata={"message": "No workouts planned on your calendar"},
                )

            # Sort by normalized date and limit
            workouts.sort(key=lambda x: _normalize_date_str(x.start_date_local))
            workouts = workouts[:limit]

            workouts_data: list[dict[str, Any]] = []
            for workout in workouts:
                date_str = _normalize_date_str(workout.start_date_local)
                date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
                today = datetime.now().date()

                if date_obj == today:
                    relative_timing = "today"
                elif date_obj == today + timedelta(days=1):
                    relative_timing = "tomorrow"
                else:
                    days_until = (date_obj - today).days
                    relative_timing = f"in_{days_until}_days"

                workout_item: dict[str, Any] = {
                    "date": date_str,
                    "relative_timing": relative_timing,
                    "name": workout.name or "Workout",
                }

                if workout.type:
                    workout_item["type"] = workout.type

                # Workout metrics
                if workout.distance or workout.distance_target:
                    distance = workout.distance or workout.distance_target
                    if distance:
                        workout_item["distance_meters"] = distance

                if workout.moving_time:
                    workout_item["duration_seconds"] = workout.moving_time

                if workout.icu_training_load:
                    workout_item["training_load"] = workout.icu_training_load

                if workout.icu_intensity:
                    workout_item["intensity_factor"] = workout.icu_intensity

                # Workout description
                if workout.description:
                    workout_item["description"] = workout.description.strip()

                workouts_data.append(workout_item)

            # Calculate total load
            total_load = sum(w.icu_training_load or 0 for w in workouts)

            return ResponseBuilder.build_response(
                data={
                    "workouts": workouts_data,
                    "count": len(workouts_data),
                    "total_planned_load": total_load if total_load > 0 else None,
                },
                query_type="upcoming_workouts",
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )


async def get_event(
    event_id: Annotated[int, "Event ID to retrieve"],
    ctx: Context | None = None,
) -> str:
    """Get detailed information for a specific calendar event.

    Returns complete details for a single event including all metrics, descriptions,
    and workout structure.

    Args:
        event_id: The unique ID of the event

    Returns:
        JSON string with event details
    """
    assert ctx is not None
    config: ICUConfig = ctx.get_state("config")

    try:
        async with ICUClient(config) as client:
            event = await client.get_event(event_id)

            # Normalize date to YYYY-MM-DD so output matches calendar/upcoming_workouts
            event_date = _normalize_date_str(event.start_date_local)

            event_data: dict[str, Any] = {
                "id": event.id,
                "date": event_date,
                "name": event.name or event.category or "Event",
                "category": event.category,
            }

            if event.description:
                event_data["description"] = event.description
            if event.type:
                event_data["type"] = event.type

            # Workout/Event metrics
            metrics: dict[str, Any] = {}
            if event.distance or event.distance_target:
                distance = event.distance or event.distance_target
                if distance:
                    metrics["distance_meters"] = distance
            if event.moving_time:
                metrics["duration_seconds"] = event.moving_time
            if event.icu_training_load:
                metrics["training_load"] = event.icu_training_load
            if event.icu_intensity:
                metrics["intensity_factor"] = event.icu_intensity
            if event.joules:
                metrics["joules"] = event.joules
            if event.joules_above_ftp:
                metrics["joules_above_ftp"] = event.joules_above_ftp

            if metrics:
                event_data["metrics"] = metrics

            # Fitness context
            fitness: dict[str, Any] = {}
            if event.icu_ctl is not None:
                fitness["ctl"] = round(event.icu_ctl, 1)
            if event.icu_atl is not None:
                fitness["atl"] = round(event.icu_atl, 1)
            if fitness:
                event_data["fitness_context"] = fitness

            # Metadata
            if event.color:
                event_data["color"] = event.color
            if event.external_id:
                event_data["external_id"] = event.external_id

            return ResponseBuilder.build_response(
                data=event_data,
                query_type="get_event",
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )
