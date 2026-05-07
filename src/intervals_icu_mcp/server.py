"""Intervals.icu MCP Server - FastMCP entry point."""

from typing import Any

from dotenv import load_dotenv
from fastmcp import FastMCP

# Load environment variables
load_dotenv()

# Initialize FastMCP server
mcp = FastMCP("Intervals.icu")

# Register middleware
from .middleware import ConfigMiddleware

mcp.add_middleware(ConfigMiddleware())

# Import and register tools
from .tools.activities import (
    delete_activity,
    download_activity_file,
    download_fit_file,
    download_gpx_file,
    get_activities_around,
    get_activity_details,
    get_recent_activities,
    search_activities,
    search_activities_full,
    update_activity,
)
from .tools.activity_analysis import (
    get_activity_intervals,
    get_activity_streams,
    get_best_efforts,
    get_gap_histogram,
    get_hr_histogram,
    get_pace_histogram,
    get_power_histogram,
    search_intervals,
)
from .tools.athlete import get_athlete_profile, get_fitness_summary
from .tools.curves import get_hr_curves, get_pace_curves
from .tools.event_management import (
    bulk_create_events,
    bulk_delete_events,
    create_event,
    delete_event,
    duplicate_event,
    update_event,
)
from .tools.events import get_calendar_events, get_event, get_upcoming_workouts
from .tools.folder_management import (
    create_folder,
    delete_folder,
    get_folder_sharing,
    update_folder,
    update_folder_sharing,
    update_plan_workouts,
)
from .tools.gear import (
    create_gear,
    create_gear_reminder,
    delete_gear,
    get_gear_list,
    update_gear,
    update_gear_reminder,
)
from .tools.performance import get_power_curves
from .tools.sport_settings import (
    apply_sport_settings,
    create_sport_settings,
    delete_sport_settings,
    get_sport_settings,
    update_sport_settings,
)
from .tools.training_plan import apply_plan_changes, get_training_plan, set_training_plan
from .tools.wellness import get_wellness_data, get_wellness_for_date, update_wellness
from .tools.workout_library import (
    bulk_create_workouts,
    create_workout,
    delete_workout,
    download_all_workouts,
    duplicate_workouts,
    export_workout,
    get_workout,
    get_workout_library,
    get_workout_tags,
    get_workouts_in_folder,
    import_workout,
    update_workout,
)

# Register activity tools
mcp.tool()(get_recent_activities)
mcp.tool()(get_activity_details)
mcp.tool()(search_activities)
mcp.tool()(search_activities_full)
mcp.tool()(get_activities_around)
mcp.tool()(update_activity)
mcp.tool()(delete_activity)
mcp.tool()(download_activity_file)
mcp.tool()(download_fit_file)
mcp.tool()(download_gpx_file)

# Register activity analysis tools
mcp.tool()(get_activity_streams)
mcp.tool()(get_activity_intervals)
mcp.tool()(get_best_efforts)
mcp.tool()(search_intervals)
mcp.tool()(get_power_histogram)
mcp.tool()(get_hr_histogram)
mcp.tool()(get_pace_histogram)
mcp.tool()(get_gap_histogram)

# Register athlete tools
mcp.tool()(get_athlete_profile)
mcp.tool()(get_fitness_summary)

# Register wellness tools
mcp.tool()(get_wellness_data)
mcp.tool()(get_wellness_for_date)
mcp.tool()(update_wellness)

# Register event/calendar tools
mcp.tool()(get_calendar_events)
mcp.tool()(get_upcoming_workouts)
mcp.tool()(get_event)
mcp.tool()(create_event)
mcp.tool()(update_event)
mcp.tool()(delete_event)
mcp.tool()(bulk_create_events)
mcp.tool()(bulk_delete_events)
mcp.tool()(duplicate_event)

# Register performance/curve tools
mcp.tool()(get_power_curves)
mcp.tool()(get_hr_curves)
mcp.tool()(get_pace_curves)

# Register workout library tools
mcp.tool()(get_workout_library)
mcp.tool()(get_workouts_in_folder)
mcp.tool()(get_workout)
mcp.tool()(create_workout)
mcp.tool()(update_workout)
mcp.tool()(delete_workout)
mcp.tool()(bulk_create_workouts)
mcp.tool()(get_workout_tags)
mcp.tool()(duplicate_workouts)
mcp.tool()(import_workout)
mcp.tool()(export_workout)
mcp.tool()(download_all_workouts)

# Register folder management tools
mcp.tool()(create_folder)
mcp.tool()(update_folder)
mcp.tool()(delete_folder)
mcp.tool()(update_plan_workouts)
mcp.tool()(get_folder_sharing)
mcp.tool()(update_folder_sharing)

# Register training plan tools
mcp.tool()(get_training_plan)
mcp.tool()(set_training_plan)
mcp.tool()(apply_plan_changes)

# Register gear management tools
mcp.tool()(get_gear_list)
mcp.tool()(create_gear)
mcp.tool()(update_gear)
mcp.tool()(delete_gear)
mcp.tool()(create_gear_reminder)
mcp.tool()(update_gear_reminder)

# Register sport settings tools
mcp.tool()(get_sport_settings)
mcp.tool()(update_sport_settings)
mcp.tool()(apply_sport_settings)
mcp.tool()(create_sport_settings)
mcp.tool()(delete_sport_settings)


# MCP Resources - Provide ongoing context
@mcp.resource("intervals-icu://athlete/profile")
async def athlete_profile_resource() -> str:
    """Complete athlete profile with fitness metrics and sport settings for context."""
    from .auth import load_config
    from .client import ICUAPIError, ICUClient
    from .response_builder import ResponseBuilder

    # Load config directly since resources don't go through middleware
    config = load_config()

    try:
        async with ICUClient(config) as client:
            # Get athlete profile
            athlete = await client.get_athlete()

            # Build minimal profile data
            data: dict[str, Any] = {
                "profile": {
                    "id": athlete.id,
                    "name": athlete.name,
                    "weight": athlete.weight,
                },
                "fitness": {
                    "ctl": athlete.ctl,
                    "atl": athlete.atl,
                    "tsb": athlete.tsb,
                    "ramp_rate": athlete.ramp_rate,
                },
            }

            # Add sport settings if available
            if athlete.sport_settings:
                sport_data: list[dict[str, str | int | float | None]] = []
                for sport in athlete.sport_settings:
                    sport_info: dict[str, str | int | float | None] = {
                        "type": sport.type,
                    }
                    if sport.ftp:
                        sport_info["ftp"] = sport.ftp
                    if sport.fthr:
                        sport_info["fthr"] = sport.fthr
                    if sport.pace_threshold:
                        sport_info["threshold_pace"] = sport.pace_threshold
                    sport_data.append(sport_info)
                data["sports"] = sport_data

            return ResponseBuilder.build_response(data, metadata={"type": "athlete_profile"})
    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")


# MCP Prompts - Templates for common queries
@mcp.prompt()
async def analyze_recent_training(days: str = "30") -> str:
    """Analyze my Intervals.icu training over a time period.

    Args:
        days: Number of days to analyze (e.g., "7", "30", "90")
    """
    return f"""Analyze my Intervals.icu training over the past {days} days.

Focus on:
1. Training volume (distance, time, elevation, training load)
2. Training distribution by activity type
3. Fitness trends (CTL/ATL/TSB)
4. Recovery metrics (HRV, sleep, wellness)
5. Key insights and recommendations

Use get_recent_activities with days_back={days}, get_fitness_summary for CTL/ATL/TSB analysis,
and get_wellness_data to assess recovery. Present findings in a clear, actionable format."""


@mcp.prompt()
async def performance_analysis(metric: str = "power") -> str:
    """Analyze my performance across different durations.

    Args:
        metric: Performance metric to analyze ("power", "hr", or "pace")
    """
    if metric == "power":
        return """Analyze my power performance across all durations.

Include:
1. Power curve with best efforts (5s, 1m, 5m, 20m, 1h)
2. Estimated FTP from 20-minute power
3. Power zones and training recommendations
4. Trends and recent improvements

Use get_power_curves to get the data, then provide detailed analysis with training suggestions."""
    elif metric == "hr":
        return """Analyze my heart rate performance.

Include:
1. HR curve with best efforts across durations
2. Max HR and FTHR estimation
3. HR zones based on max HR
4. Cardiac fitness trends

Use get_hr_curves to get HR curve data, then provide detailed analysis with zone recommendations."""
    else:
        return """Analyze my pace performance.

Include:
1. Best pace efforts across distances
2. Threshold pace estimation from curve
3. Pace zones for different training intensities
4. Recent running trends

Use get_pace_curves to get pace curve data (optionally with GAP for trail running),
then provide detailed analysis with training recommendations."""


@mcp.prompt()
async def activity_deep_dive(activity_id: str) -> str:
    """Get comprehensive analysis of a specific activity.

    Args:
        activity_id: The ID of the activity to analyze
    """
    return f"""Provide a comprehensive analysis of activity {activity_id}.

Include:
1. Basic metrics (distance, time, pace/speed, elevation)
2. Power and heart rate data (if available)
3. Training load and intensity
4. Interval structure and workout compliance (if structured)
5. Best efforts found in this activity
6. Subjective metrics (feel, RPE)
7. Performance insights and comparison to recent activities

Use get_activity_details for basic info, get_activity_intervals for workout structure,
get_best_efforts for peak performances, and optionally get_activity_streams for
time-series visualization. Compare with similar recent activities to provide context."""


@mcp.prompt()
async def recovery_check() -> str:
    """Assess my current recovery and readiness to train."""
    return """Assess my current recovery status and readiness for training.

Include:
1. Recent wellness metrics (HRV, resting HR, sleep quality)
2. Training stress balance (TSB, CTL/ATL)
3. Subjective metrics (fatigue, soreness, mood)
4. Recovery trends over past week
5. Training recommendations

Use get_wellness_data for recent wellness, get_fitness_summary for TSB analysis,
then provide clear guidance on training intensity."""


@mcp.prompt()
async def training_plan_review() -> str:
    """Review my upcoming training plan."""
    return """Review my upcoming training plan and provide feedback.

Include:
1. Upcoming workouts from calendar
2. Planned training load vs current fitness
3. Recovery days and intensity distribution
4. Workout library structure (if using a training plan)
5. Recommendations for adjustments

Use get_upcoming_workouts to see the plan, get_fitness_summary for current form,
and optionally get_workout_library to see available training plans, then evaluate
if the plan is appropriate and suggest any modifications."""


@mcp.prompt()
async def plan_training_week(goal: str = "balanced") -> str:
    """Help plan my training week based on current form and goals.

    Args:
        goal: Training goal ("balanced", "build", "recover", "peak")
    """
    return f"""Help me plan my training week with a "{goal}" focus.

Steps:
1. Check current fitness status (CTL/ATL/TSB) using get_fitness_summary
2. Review recent training load and patterns with get_recent_activities
3. Check recovery markers with get_wellness_data
4. Review workout library for appropriate sessions with get_workout_library
5. Create planned workouts for the week using create_event

Provide a structured weekly plan with:
- Workout types and intensities for each day
- Recovery days placement
- Expected weekly training load
- Reasoning for the schedule based on current form

Then offer to create the events in my calendar if I approve the plan."""


def main():
    """Main entry point for the Intervals.icu MCP server."""
    import os

    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    mcp.run(transport=transport)


if __name__ == "__main__":
    main()
