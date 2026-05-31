"""Heart-rate and pace mean-max curve tools for Intervals.icu MCP server."""

from typing import Annotated, Any

from fastmcp import Context

from ..auth import ICUConfig
from ..client import ICUAPIError, ICUClient
from ..models import DataCurve
from ..response_builder import ResponseBuilder
from .performance import curve_points, curves_param


async def get_hr_curves(
    days_back: Annotated[int | None, "Number of days to analyze (optional)"] = None,
    time_period: Annotated[
        str | None,
        "Time period shorthand: 'week', 'month', 'year', 'all' (optional)",
    ] = None,
    sport_type: Annotated[
        str | None,
        "Activity type: 'Ride', 'Run', etc. (defaults to 'Ride')",
    ] = None,
    ctx: Context | None = None,
) -> str:
    """Get heart-rate mean-max curve and zones derived from peak HR.

    Returns best HR efforts across standard durations and zone bands based on the
    observed max HR.

    Args:
        days_back: Number of days to analyze (overrides time_period).
        time_period: 'week', 'month', 'year', 'all'. Default 90 days.
        sport_type: Activity type. Defaults to 'Ride'.

    Returns:
        JSON string with HR curve data and zone analysis.
    """
    assert ctx is not None
    config: ICUConfig = ctx.get_state("config")

    curves_value, period_label = curves_param(days_back, time_period)
    sport = sport_type or "Ride"

    try:
        async with ICUClient(config) as client:
            curve_set = await client.get_hr_curves(sport_type=sport, curves=curves_value)

            if not curve_set.curves or not curve_set.curves[0].secs:
                return ResponseBuilder.build_response(
                    data={"hr_curve": [], "period": period_label, "sport_type": sport},
                    metadata={
                        "message": (
                            f"No HR curve data available for {sport} over {period_label}. "
                            "Complete some activities with heart-rate data for this sport."
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
                        "bpm": closest["value"],
                        "duration_seconds": closest["secs"],
                    }
                    if "activity_id" in closest:
                        effort["activity_id"] = closest["activity_id"]
                    peak_efforts[label] = effort

            max_pt = max(points, key=lambda p: p["value"])
            summary: dict[str, Any] = {
                "total_data_points": len(points),
                "max_hr_bpm": max_pt["value"],
                "max_hr_duration_seconds": max_pt["secs"],
                "duration_range": {
                    "min_seconds": points[0]["secs"],
                    "max_seconds": points[-1]["secs"],
                },
                "curve_label": curve.label,
                "curve_start_date": curve.start_date_local,
                "curve_end_date": curve.end_date_local,
            }

            hr_zones: dict[str, dict[str, int]] | None = None
            max_hr = max_pt["value"]
            if max_hr:
                zones = {
                    "zone_1_recovery": (0.50, 0.60),
                    "zone_2_endurance": (0.60, 0.70),
                    "zone_3_tempo": (0.70, 0.80),
                    "zone_4_threshold": (0.80, 0.90),
                    "zone_5_vo2max": (0.90, 1.00),
                }
                hr_zones = {}
                for zone_name, (low, high) in zones.items():
                    hr_zones[zone_name] = {
                        "min_bpm": int(max_hr * low),
                        "max_bpm": int(max_hr * high),
                        "min_percent_max": int(low * 100),
                        "max_percent_max": int(high * 100),
                    }

            result_data: dict[str, Any] = {
                "period": period_label,
                "sport_type": sport,
                "peak_efforts": peak_efforts,
                "summary": summary,
            }
            if hr_zones:
                result_data["hr_zones"] = hr_zones

            return ResponseBuilder.build_response(data=result_data, query_type="hr_curves")

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )


def _pace_points(curve: DataCurve) -> list[dict[str, Any]]:
    """Flatten a pace curve's parallel distance / values arrays.

    For pace curves the API returns x = distance (m), y = values (time-in-seconds
    to cover that distance). We surface both, plus the derived pace in min/km.
    """
    points: list[dict[str, Any]] = []
    n = min(len(curve.distance), len(curve.values))
    for i in range(n):
        distance_m = curve.distance[i]
        time_s = curve.values[i]
        if distance_m <= 0 or time_s <= 0:
            continue
        pace_min_per_km = (time_s / 60.0) / (distance_m / 1000.0)
        pt: dict[str, Any] = {
            "distance_m": distance_m,
            "secs": time_s,
            "pace_min_per_km": pace_min_per_km,
        }
        if i < len(curve.activity_id):
            pt["activity_id"] = curve.activity_id[i]
        points.append(pt)
    return points


def _format_pace(pace_min_per_km: float) -> str:
    minutes = int(pace_min_per_km)
    seconds = int(round((pace_min_per_km - minutes) * 60))
    if seconds == 60:
        minutes += 1
        seconds = 0
    return f"{minutes}:{seconds:02d} /km"


async def get_pace_curves(
    days_back: Annotated[int | None, "Number of days to analyze (optional)"] = None,
    time_period: Annotated[
        str | None,
        "Time period shorthand: 'week', 'month', 'year', 'all' (optional)",
    ] = None,
    sport_type: Annotated[
        str | None,
        "Activity type: 'Run', 'Walk', etc. (defaults to 'Run')",
    ] = None,
    use_gap: Annotated[bool, "Use Grade Adjusted Pace (GAP) for running"] = False,
    ctx: Context | None = None,
) -> str:
    """Get pace mean-max curve, indexed by standard race distances.

    Pace curves are indexed by distance (not duration): the API returns the best
    time achieved to cover each of a set of standard distances (400 m, 1 km, 5 km,
    10 km, half-marathon, etc.).

    Args:
        days_back: Number of days to analyze (overrides time_period).
        time_period: 'week', 'month', 'year', 'all'. Default 90 days.
        sport_type: Activity type. Defaults to 'Run'.
        use_gap: Use Grade-Adjusted Pace to normalize for hills.

    Returns:
        JSON string with pace curve data and best efforts at standard distances.
    """
    assert ctx is not None
    config: ICUConfig = ctx.get_state("config")

    curves_value, period_label = curves_param(days_back, time_period)
    sport = sport_type or "Run"

    try:
        async with ICUClient(config) as client:
            curve_set = await client.get_pace_curves(
                sport_type=sport, curves=curves_value, use_gap=use_gap
            )

            if not curve_set.curves or not curve_set.curves[0].distance:
                return ResponseBuilder.build_response(
                    data={
                        "pace_curve": [],
                        "period": period_label,
                        "sport_type": sport,
                        "gap_enabled": use_gap,
                    },
                    metadata={
                        "message": (
                            f"No pace curve data available for {sport} over {period_label}. "
                            "Complete some runs/walks to build the pace curve."
                        )
                    },
                )

            curve = curve_set.curves[0]
            points = _pace_points(curve)

            key_distances_m = {
                400: "400m",
                1000: "1km",
                1609: "1mi",
                5000: "5km",
                10_000: "10km",
                21_097: "half_marathon",
                42_195: "marathon",
            }
            best_efforts: dict[str, dict[str, Any]] = {}
            for target_m, label in key_distances_m.items():
                closest = min(
                    points, key=lambda p: abs(p["distance_m"] - target_m), default=None
                )
                # Accept within 10% of the target distance.
                if closest and abs(closest["distance_m"] - target_m) <= target_m * 0.10:
                    effort: dict[str, Any] = {
                        "distance_m": round(closest["distance_m"], 1),
                        "time_seconds": closest["secs"],
                        "pace_min_per_km": round(closest["pace_min_per_km"], 3),
                        "pace_formatted": _format_pace(closest["pace_min_per_km"]),
                    }
                    if "activity_id" in closest:
                        effort["activity_id"] = closest["activity_id"]
                    best_efforts[label] = effort

            best_pace_point = min(points, key=lambda p: p["pace_min_per_km"])
            summary: dict[str, Any] = {
                "total_data_points": len(points),
                "best_pace_min_per_km": round(best_pace_point["pace_min_per_km"], 3),
                "best_pace_formatted": _format_pace(best_pace_point["pace_min_per_km"]),
                "best_pace_distance_m": round(best_pace_point["distance_m"], 1),
                "distance_range_m": {
                    "min": round(points[0]["distance_m"], 1),
                    "max": round(points[-1]["distance_m"], 1),
                },
                "curve_label": curve.label,
                "curve_start_date": curve.start_date_local,
                "curve_end_date": curve.end_date_local,
                "gap_enabled": use_gap,
            }

            return ResponseBuilder.build_response(
                data={
                    "period": period_label,
                    "sport_type": sport,
                    "best_efforts": best_efforts,
                    "summary": summary,
                },
                query_type="pace_curves",
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )
