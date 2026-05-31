"""Performance analysis tools for Intervals.icu MCP server."""

from typing import Annotated, Any

from fastmcp import Context

from ..auth import ICUConfig
from ..client import ICUAPIError, ICUClient
from ..models import DataCurve
from ..response_builder import ResponseBuilder


def curves_param(days_back: int | None, time_period: str | None) -> tuple[str, str]:
    """Translate user-facing time selectors into the API's `curves` query value.

    Returns (curves_param, human_label). Shared between power and HR/pace tools.
    """
    if days_back is not None and days_back > 0:
        return f"{days_back}d", f"{days_back}_days"
    if time_period:
        m = {"week": ("7d", "week"), "month": ("30d", "month"), "year": ("1y", "year")}
        key = time_period.lower()
        if key in m:
            return m[key]
        if key == "all":
            return "all", "all_time"
    # Preserve the prior default of 90 days.
    return "90d", "90_days"


def curve_points(curve: DataCurve) -> list[dict[str, Any]]:
    """Flatten a power/HR curve's parallel secs / values / activity_id arrays.

    Each point has secs (duration), value (watts or bpm), and optionally activity_id.
    Shared between power and HR tools.
    """
    points: list[dict[str, Any]] = []
    n = min(len(curve.secs), len(curve.values))
    for i in range(n):
        pt: dict[str, Any] = {"secs": curve.secs[i], "value": curve.values[i]}
        if i < len(curve.activity_id):
            pt["activity_id"] = curve.activity_id[i]
        points.append(pt)
    return points


async def get_power_curves(
    days_back: Annotated[int | None, "Number of days to analyze (optional)"] = None,
    time_period: Annotated[
        str | None,
        "Time period shorthand: 'week', 'month', 'year', 'all' (optional)",
    ] = None,
    sport_type: Annotated[
        str | None,
        "Activity type: 'Ride', 'Run', 'Swim', etc. (defaults to 'Ride')",
    ] = None,
    ctx: Context | None = None,
) -> str:
    """Get power mean-max curve and an FTP estimate from 20-min power.

    Returns peak power outputs at standard durations (5s, 15s, 30s, 1m, 2m, 5m,
    10m, 20m, 1h) plus a Coggan-style FTP estimate (95% of 20-min power) and
    derived power zones when 20-min data is present.

    Args:
        days_back: Number of days to analyze (overrides time_period).
        time_period: 'week' (7d), 'month' (30d), 'year' (1y), 'all'. Default 90 days.
        sport_type: Activity type. Defaults to 'Ride'.

    Returns:
        JSON string with power curve data and FTP analysis.
    """
    assert ctx is not None
    config: ICUConfig = ctx.get_state("config")

    curves_value, period_label = curves_param(days_back, time_period)
    sport = sport_type or "Ride"

    try:
        async with ICUClient(config) as client:
            curve_set = await client.get_power_curves(sport_type=sport, curves=curves_value)

            if not curve_set.curves or not curve_set.curves[0].secs:
                return ResponseBuilder.build_response(
                    data={"power_curve": [], "period": period_label, "sport_type": sport},
                    metadata={
                        "message": (
                            f"No power curve data available for {sport} over {period_label}. "
                            "Complete some activities with power for this sport to build the curve."
                        )
                    },
                )

            curve = curve_set.curves[0]
            points = curve_points(curve)

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
            peak_efforts: dict[str, dict[str, Any]] = {}
            for seconds, label in key_durations.items():
                closest = min(points, key=lambda p: abs(p["secs"] - seconds), default=None)
                if closest and abs(closest["secs"] - seconds) <= max(1, seconds * 0.1):
                    effort: dict[str, Any] = {
                        "watts": closest["value"],
                        "duration_seconds": closest["secs"],
                    }
                    if "activity_id" in closest:
                        effort["activity_id"] = closest["activity_id"]
                    peak_efforts[label] = effort

            max_pt = max(points, key=lambda p: p["value"])
            summary: dict[str, Any] = {
                "total_data_points": len(points),
                "max_power_watts": max_pt["value"],
                "max_power_duration_seconds": max_pt["secs"],
                "duration_range": {
                    "min_seconds": points[0]["secs"],
                    "max_seconds": points[-1]["secs"],
                },
                "curve_label": curve.label,
                "curve_start_date": curve.start_date_local,
                "curve_end_date": curve.end_date_local,
                "athlete_weight_kg": curve.weight,
            }

            ftp_analysis: dict[str, Any] | None = None
            twenty_min = next((p for p in points if p["secs"] == 1200), None)
            if twenty_min is None:
                candidate = min(points, key=lambda p: abs(p["secs"] - 1200), default=None)
                if candidate is not None and abs(candidate["secs"] - 1200) <= 120:
                    twenty_min = candidate
            if twenty_min is not None and twenty_min["value"] > 0:
                estimated_ftp = int(twenty_min["value"] * 0.95)
                zones = {
                    "recovery": (0.0, 0.55),
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
                    "twenty_min_power": twenty_min["value"],
                    "estimated_ftp": estimated_ftp,
                    "method": "Coggan 95% of 20-min power",
                    "power_zones": power_zones,
                }

            result_data: dict[str, Any] = {
                "period": period_label,
                "sport_type": sport,
                "peak_efforts": peak_efforts,
                "summary": summary,
            }
            if ftp_analysis:
                result_data["ftp_analysis"] = ftp_analysis

            return ResponseBuilder.build_response(data=result_data, query_type="power_curves")

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )
