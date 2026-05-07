"""Performance analysis tools for Intervals.icu MCP server."""

from datetime import datetime, timedelta
from typing import Annotated, Any

from fastmcp import Context

from ..auth import ICUConfig
from ..client import ICUAPIError, ICUClient
from ..response_builder import ResponseBuilder


async def get_power_curves(
    days_back: Annotated[int | None, "Number of days to analyze (optional)"] = None,
    time_period: Annotated[
        str | None,
        "Time period shorthand: 'week', 'month', 'year', 'all' (optional)",
    ] = None,
    sport_type: Annotated[
        str,
        "Sport type to get curves for: 'Ride', 'Run', 'Swim', 'VirtualRide', etc. Default is 'Ride'",
    ] = "Ride",
    ctx: Context | None = None,
) -> str:
    """Get power curve data showing best efforts for various durations.

    Analyzes power data across activities to find peak power outputs for
    different time durations (e.g., 5 seconds, 1 minute, 5 minutes, 20 minutes).

    Useful for tracking performance improvements and identifying strengths/weaknesses
    across different power duration profiles.

    Args:
        days_back: Number of days to analyze (overrides time_period)
        time_period: Time period shorthand - 'week' (7 days), 'month' (30 days),
                     'year' (365 days), 'all' (all time). Default is 90 days.
        sport_type: Sport type (e.g. 'Ride', 'Run', 'Swim', 'VirtualRide'). Default is 'Ride'.

    Returns:
        JSON string with power curve data
    """
    assert ctx is not None
    config: ICUConfig = ctx.get_state("config")

    try:
        # Determine date range
        oldest = None

        if days_back is not None:
            oldest_date = datetime.now() - timedelta(days=days_back)
            oldest = oldest_date.strftime("%Y-%m-%d")
            period_label = f"{days_back}_days"
        elif time_period:
            period_map = {
                "week": 7,
                "month": 30,
                "year": 365,
            }
            if time_period.lower() in period_map:
                days = period_map[time_period.lower()]
                oldest_date = datetime.now() - timedelta(days=days)
                oldest = oldest_date.strftime("%Y-%m-%d")
                period_label = time_period.lower()
            elif time_period.lower() == "all":
                oldest = None
                period_label = "all_time"
            else:
                return ResponseBuilder.build_error_response(
                    "Invalid time_period. Use 'week', 'month', 'year', or 'all'",
                    error_type="validation_error",
                )
        else:
            # Default to 90 days
            oldest_date = datetime.now() - timedelta(days=90)
            oldest = oldest_date.strftime("%Y-%m-%d")
            period_label = "90_days"

        async with ICUClient(config) as client:
            power_curve = await client.get_power_curves(oldest=oldest, sport_type=sport_type)

            if not power_curve.secs or not power_curve.values:
                return ResponseBuilder.build_response(
                    data={"power_curve": [], "period": period_label},
                    metadata={
                        "message": f"No power curve data available for {period_label}. "
                        "Complete some rides with power to build your power curve."
                    },
                )

            # Build list of (secs, watts, activity_id) tuples for easy lookup
            act_ids = power_curve.activity_id or []
            points = [
                (s, w, act_ids[i] if i < len(act_ids) else None)
                for i, (s, w) in enumerate(zip(power_curve.secs, power_curve.values, strict=True))
            ]

            # Key durations to highlight (in seconds)
            key_durations = {
                5: "5_sec",
                15: "15_sec",
                30: "30_sec",
                60: "1_min",
                120: "2_min",
                300: "5_min",
                600: "10_min",
                1200: "20_min",
                3600: "1_hour",
            }

            # Find data points for key durations
            peak_efforts: dict[str, dict[str, Any]] = {}
            for seconds, label in key_durations.items():
                closest = min(points, key=lambda p: abs(p[0] - seconds), default=None)
                if closest and abs(closest[0] - seconds) <= seconds * 0.1:
                    effort: dict[str, Any] = {
                        "watts": closest[1],
                        "duration_seconds": closest[0],
                    }
                    if closest[2]:
                        effort["activity_id"] = closest[2]
                    peak_efforts[label] = effort

            # Calculate summary statistics
            max_watts = max(power_curve.values)
            max_idx = power_curve.values.index(max_watts)

            summary: dict[str, Any] = {
                "total_data_points": len(power_curve.secs),
                "max_power_watts": max_watts,
                "max_power_duration_seconds": power_curve.secs[max_idx],
                "duration_range": {
                    "min_seconds": power_curve.secs[0],
                    "max_seconds": power_curve.secs[-1],
                },
            }

            if power_curve.start_date_local and power_curve.end_date_local:
                summary["effort_date_range"] = {
                    "oldest": power_curve.start_date_local,
                    "newest": power_curve.end_date_local,
                }

            # Calculate FTP estimate and power zones (based on 20-min power)
            closest_20min = min(points, key=lambda p: abs(p[0] - 1200), default=None)

            ftp_analysis = None
            if closest_20min and abs(closest_20min[0] - 1200) <= 120:
                estimated_ftp = int((closest_20min[1] or 0) * 0.95)

                if estimated_ftp > 0:
                    zones = {
                        "recovery": (0, 0.55),
                        "endurance": (0.56, 0.75),
                        "tempo": (0.76, 0.90),
                        "threshold": (0.91, 1.05),
                        "vo2max": (1.06, 1.20),
                        "anaerobic": (1.21, 1.50),
                    }

                    power_zones: dict[str, dict[str, int]] = {}
                    for zone_name, (low, high) in zones.items():
                        power_zones[zone_name] = {
                            "min_watts": int(estimated_ftp * low),
                            "max_watts": int(estimated_ftp * high),
                            "min_percent_ftp": int(low * 100),
                            "max_percent_ftp": int(high * 100),
                        }

                    ftp_analysis = {
                        "twenty_min_power": closest_20min[1],
                        "estimated_ftp": estimated_ftp,
                        "power_zones": power_zones,
                    }

            result_data: dict[str, Any] = {
                "period": period_label,
                "peak_efforts": peak_efforts,
                "summary": summary,
            }

            if ftp_analysis:
                result_data["ftp_analysis"] = ftp_analysis

            return ResponseBuilder.build_response(
                data=result_data,
                query_type="power_curves",
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )
