"""Route analysis tools: parse GPX files and detect climbs for terrain-aware workouts.

The analyze_route_climbs tool reads a local GPX file, detects climbs at the configured
thresholds, and returns structured climb data plus a workout-planning hint in the
analysis section. Claude then composes a distance-locked workout description (using
the Intervals.icu workout DSL) and pushes it with the existing create_event tool.

Distance-locked rather than GPS-locked: Intervals.icu's workout language supports
distance steps (e.g. "- 1.6km 95%") but not coordinate triggers, and Garmin head units
run a workout and a course side-by-side without coupling. If the rider starts the
workout at the route start, the distance-based intervals line up with the climbs.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Literal

import gpxpy
from fastmcp import Context
from gpxpy.geo import haversine_distance

from ..response_builder import ResponseBuilder


@dataclass(frozen=True)
class SportProfile:
    """Climb-detection thresholds for a given sport."""

    min_gradient_pct: float
    min_length_m: float
    recovery_tolerance_m: float


_PROFILES: dict[str, SportProfile] = {
    "cycling": SportProfile(min_gradient_pct=3.0, min_length_m=200.0, recovery_tolerance_m=80.0),
    "running": SportProfile(min_gradient_pct=4.0, min_length_m=50.0, recovery_tolerance_m=20.0),
}


@dataclass
class _Point:
    lat: float
    lon: float
    ele: float
    cum_dist_m: float


@dataclass
class _Climb:
    start_idx: int
    end_idx: int
    start_km: float
    end_km: float
    length_m: float
    elevation_gain_m: float
    avg_gradient_pct: float
    max_gradient_pct: float


def _smooth_by_distance(
    elevations: list[float],
    cum_distances: list[float],
    half_window_m: float,
) -> list[float]:
    """Centered rolling mean over a fixed *distance* window.

    Distance-based (rather than point-count based) smoothing keeps behaviour
    consistent across GPX files with very different point densities — a dense
    Garmin recording (1 pt / 5 m) and a sparse Komoot export (1 pt / 25 m) both
    end up smoothed over roughly the same span of terrain.
    """
    n = len(elevations)
    out: list[float] = []
    left = 0
    right = 0
    for i in range(n):
        target_lo = cum_distances[i] - half_window_m
        target_hi = cum_distances[i] + half_window_m
        while left < n and cum_distances[left] < target_lo:
            left += 1
        while right < n and cum_distances[right] <= target_hi:
            right += 1
        # Window is [left, right); include at least the current point.
        lo = min(left, i)
        hi = max(right, i + 1)
        out.append(sum(elevations[lo:hi]) / (hi - lo))
    return out


def _build_points_from_gpx(
    gpx: Any, half_window_m: float
) -> tuple[list[_Point], str | None]:
    """Turn a parsed GPX object into smoothed trackpoints plus a route name.

    Raises ValueError if the GPX has no points or is missing elevation data.
    """
    raw: list[tuple[float, float, float | None]] = []
    for track in gpx.tracks:
        for seg in track.segments:
            for pt in seg.points:
                raw.append((pt.latitude, pt.longitude, pt.elevation))

    if not raw:
        raise ValueError("GPX contains no track points.")

    if any(ele is None for _, _, ele in raw):
        raise ValueError(
            "GPX is missing elevation data on one or more points. "
            "Climb detection requires elevation; re-export the route from your source "
            "(Komoot/Strava/Garmin Connect/RideWithGPS) with elevation enabled."
        )

    elevations: list[float] = [float(ele) for _, _, ele in raw if ele is not None]

    cum_distances: list[float] = [0.0]
    for i in range(1, len(raw)):
        d = haversine_distance(raw[i - 1][0], raw[i - 1][1], raw[i][0], raw[i][1])
        cum_distances.append(cum_distances[-1] + d)

    smoothed = _smooth_by_distance(elevations, cum_distances, half_window_m=half_window_m)

    points = [
        _Point(lat=raw[i][0], lon=raw[i][1], ele=smoothed[i], cum_dist_m=cum_distances[i])
        for i in range(len(raw))
    ]

    name: str | None = None
    if gpx.tracks and gpx.tracks[0].name:
        name = gpx.tracks[0].name
    elif gpx.name:
        name = gpx.name

    return points, name


def _parse_from_path(path: Path, half_window_m: float) -> tuple[list[_Point], str | None]:
    """Parse a GPX file from disk. Raises FileNotFoundError if missing, ValueError on bad content."""
    if not path.exists():
        raise FileNotFoundError(f"GPX file not found: {path}")
    with path.open() as fh:
        gpx = gpxpy.parse(fh)
    return _build_points_from_gpx(gpx, half_window_m)


def _parse_from_content(content: str, half_window_m: float) -> tuple[list[_Point], str | None]:
    """Parse a GPX XML string. Raises ValueError if the XML is unparseable or has no elevation."""
    try:
        gpx = gpxpy.parse(content)
    except Exception as e:  # gpxpy raises GPXXMLSyntaxException and friends — wrap them.
        raise ValueError(f"Could not parse GPX content: {e}") from e
    return _build_points_from_gpx(gpx, half_window_m)


def _build_climb(points: list[_Point], start_idx: int, end_idx: int) -> _Climb:
    """Materialise a climb summary from a closed [start_idx, end_idx] index range."""
    length_m = points[end_idx].cum_dist_m - points[start_idx].cum_dist_m
    elevation_gain = points[end_idx].ele - points[start_idx].ele
    avg_gradient_pct = (elevation_gain / length_m * 100.0) if length_m > 0 else 0.0

    max_grad = 0.0
    for j in range(start_idx, end_idx):
        seg_dist = points[j + 1].cum_dist_m - points[j].cum_dist_m
        if seg_dist > 0:
            seg_grad = (points[j + 1].ele - points[j].ele) / seg_dist * 100.0
            max_grad = max(max_grad, seg_grad)

    return _Climb(
        start_idx=start_idx,
        end_idx=end_idx,
        start_km=points[start_idx].cum_dist_m / 1000.0,
        end_km=points[end_idx].cum_dist_m / 1000.0,
        length_m=length_m,
        elevation_gain_m=elevation_gain,
        avg_gradient_pct=avg_gradient_pct,
        max_gradient_pct=max_grad,
    )


def _detect_climbs(points: list[_Point], profile: SportProfile) -> list[_Climb]:
    """Walk segments and group consecutive uphill segments into climbs.

    Up to `recovery_tolerance_m` of below-threshold distance is allowed inside a
    climb so undulating ascents don't get fragmented. Climbs shorter than
    `min_length_m` after detection are filtered out.
    """
    if len(points) < 2:
        return []

    climbs: list[_Climb] = []
    current_start: int | None = None
    recovery_distance = 0.0
    last_above_idx: int | None = None

    for i in range(len(points) - 1):
        seg_dist = points[i + 1].cum_dist_m - points[i].cum_dist_m
        if seg_dist <= 0:
            continue
        seg_grad_pct = (points[i + 1].ele - points[i].ele) / seg_dist * 100.0

        if seg_grad_pct >= profile.min_gradient_pct:
            if current_start is None:
                current_start = i
            recovery_distance = 0.0
            last_above_idx = i + 1
        elif current_start is not None:
            recovery_distance += seg_dist
            if recovery_distance > profile.recovery_tolerance_m:
                if last_above_idx is not None:
                    climbs.append(_build_climb(points, current_start, last_above_idx))
                current_start = None
                recovery_distance = 0.0
                last_above_idx = None

    if current_start is not None and last_above_idx is not None:
        climbs.append(_build_climb(points, current_start, last_above_idx))

    return [c for c in climbs if c.length_m >= profile.min_length_m]


def _categorise_climb_cycling(climb: _Climb) -> str:
    """Tour de France-style category from score = length_km * avg_gradient_pct."""
    score = (climb.length_m / 1000.0) * climb.avg_gradient_pct
    if score >= 80:
        return "HC"
    if score >= 32:
        return "Cat 1"
    if score >= 16:
        return "Cat 2"
    if score >= 8:
        return "Cat 3"
    if score >= 1.5:
        return "Cat 4"
    return "uncategorised"


def _categorise_climb_running(climb: _Climb) -> str:
    """Running climbs bucketed by length."""
    if climb.length_m >= 1000:
        return "long sustained"
    if climb.length_m >= 300:
        return "medium"
    return "short steep"


def _estimate_climb_duration_s(climb: _Climb, sport: str) -> int:
    """Rough sanity estimate of how long this climb takes at threshold effort.

    These are not prescribed targets — they're hints for choosing an appropriate
    training zone. Real time-to-completion depends on the rider's FTP, conditions, etc.
    """
    if sport == "running":
        adj_pace_s_per_km = 300.0 * (1.0 + 0.033 * climb.avg_gradient_pct)
        return int((climb.length_m / 1000.0) * adj_pace_s_per_km)
    duration_from_vam_s = (climb.elevation_gain_m / 800.0) * 3600.0
    duration_from_distance_s = (climb.length_m / 1000.0) / 25.0 * 3600.0
    return int(max(duration_from_vam_s, duration_from_distance_s))


def _suggested_zone(duration_s: int) -> str:
    if duration_s >= 1200:
        return "Z3 sweet spot"
    if duration_s >= 600:
        return "Z4 threshold"
    if duration_s >= 180:
        return "Z5 VO2max"
    return "Z6 anaerobic"


def _format_distance_dsl(length_m: float) -> str:
    """Format a segment length as an Intervals.icu DSL distance literal — always km.

    The DSL overloads the suffix `m`: in a distance context it means metres, but
    in a time context (where most workout steps live) it means minutes. Pasting
    a `- 90m Z6` step into a workout description silently becomes "90 minutes at
    Z6" instead of "90 metres at Z6", producing absurd durations and TSS. So we
    always emit `km`:

      >=1000 m: 1 decimal (e.g. "1.6km")
      <1000 m: 2 decimals, trailing zeros trimmed (e.g. "0.43km", "0.5km", "0.09km")
    """
    km = length_m / 1000.0
    if km >= 1.0:
        return f"{km:.1f}km"
    formatted = f"{km:.2f}".rstrip("0").rstrip(".")
    return f"{formatted}km"


def _bare_zone(suggested_zone: str) -> str:
    """Extract the bare zone tag from a 'Z4 threshold' / 'Z6 anaerobic' label.

    The Intervals.icu DSL accepts 'Z3', 'Z4', etc. — not the human-readable suffix.
    """
    return suggested_zone.split(" ", 1)[0]


def _climb_suggested_step(climb_dict: dict[str, Any]) -> str:
    """Build a distance-locked DSL line for a climb (ready to paste into create_event)."""
    distance = _format_distance_dsl(float(climb_dict["length_m"]))
    zone = _bare_zone(str(climb_dict["suggested_zone"]))
    return f"- {distance} {zone}"


def _recovery_suggested_step(segment: dict[str, Any]) -> str:
    """Build a distance-locked DSL line for a recovery segment.

    The recovery zone is chosen by character — descents and shallow descents are
    pure Z1 spin-out; flats are Z2 endurance; shallow rises default to Z2 but
    Claude can promote to Z3 if it needs to extend a hard effort there (the
    hard_effort_recommended flag on the segment is the cue).
    """
    distance = _format_distance_dsl(float(segment["length_m"]))
    char = str(segment["character"])
    zone = "Z1" if char in ("descent", "shallow_descent") else "Z2"
    return f"- {distance} {zone}"


def _characterise_segment(avg_grad_pct: float, climb_threshold_pct: float) -> tuple[str, bool]:
    """Classify a non-climb segment by average gradient and flag whether hard
    intervals are appropriate to place (or extend) into it.

    Buckets, in order of avg_grad_pct:
      - descent          (avg <= -1.5%)            — never place hard efforts (downhill)
      - shallow_descent  (-1.5% < avg <= -0.5%)    — also avoid for hard efforts
      - flat             (-0.5% < avg <  0.5%)     — neutral; OK for steady, not ideal for V02
      - shallow_rise     (0.5% <= avg < threshold) — *good for extending a hard interval that
                                                     needs more time than the steep climb allows*
    """
    if avg_grad_pct <= -1.5:
        return "descent", False
    if avg_grad_pct <= -0.5:
        return "shallow_descent", False
    if avg_grad_pct < 0.5:
        return "flat", False
    if avg_grad_pct < climb_threshold_pct:
        return "shallow_rise", True
    # Anything >= climb_threshold would have been picked up by climb detection.
    # Treat as a shallow_rise edge case if it somehow slipped through.
    return "shallow_rise", True


def _build_recovery_segments(
    climbs: list[_Climb],
    points: list[_Point],
    climb_threshold_pct: float,
) -> list[dict[str, Any]]:
    """Produce the segments between climbs (plus head/tail) with character + flag.

    Each segment indicates whether hard intervals are appropriate to place there,
    so a hard effort that needs more time than the adjacent steep climb can offer
    can be extended into a `shallow_rise` but never into a `descent`.
    """
    boundaries: list[tuple[int, int]] = []
    prev_end = 0
    for climb in climbs:
        if climb.start_idx > prev_end:
            boundaries.append((prev_end, climb.start_idx))
        prev_end = climb.end_idx
    if prev_end < len(points) - 1:
        boundaries.append((prev_end, len(points) - 1))

    segments: list[dict[str, Any]] = []
    for start_idx, end_idx in boundaries:
        length_m = points[end_idx].cum_dist_m - points[start_idx].cum_dist_m
        if length_m <= 0:
            continue
        ele_delta = points[end_idx].ele - points[start_idx].ele
        avg_grad = ele_delta / length_m * 100.0
        character, hard_ok = _characterise_segment(avg_grad, climb_threshold_pct)
        seg: dict[str, Any] = {
            "start_km": round(points[start_idx].cum_dist_m / 1000.0, 3),
            "end_km": round(points[end_idx].cum_dist_m / 1000.0, 3),
            "length_m": round(length_m, 1),
            "avg_gradient_percent": round(avg_grad, 2),
            "character": character,
            "hard_effort_recommended": hard_ok,
        }
        seg["suggested_step"] = _recovery_suggested_step(seg)
        segments.append(seg)
    return segments


def _downsample_profile(points: list[_Point], target: int = 80) -> list[dict[str, float]]:
    """Sample roughly `target` points evenly by distance."""
    if len(points) <= target:
        return [
            {"km": round(p.cum_dist_m / 1000.0, 3), "ele_m": round(p.ele, 1)} for p in points
        ]
    total_dist = points[-1].cum_dist_m
    step = total_dist / (target - 1)
    out: list[dict[str, float]] = []
    target_dist = 0.0
    j = 0
    for _ in range(target):
        while j < len(points) - 1 and points[j + 1].cum_dist_m < target_dist:
            j += 1
        out.append(
            {"km": round(points[j].cum_dist_m / 1000.0, 3), "ele_m": round(points[j].ele, 1)}
        )
        target_dist += step
    return out


def _warmup_recommendation(climbs_data: list[dict[str, Any]], sport: str) -> dict[str, Any]:
    """Return guidance Claude can use to ensure the workout has a real warm-up.

    The rider must never start a hard effort cold. If the route's first climb is
    very early (i.e. there isn't enough natural low-intensity riding/running to
    serve as a warm-up), Claude must prepend explicit Z1/Z2 warm-up steps.
    """
    min_warmup_min = 15 if sport == "cycling" else 10
    first_climb_km = climbs_data[0]["start_km"] if climbs_data else None
    if first_climb_km is None:
        note = (
            f"Begin with at least {min_warmup_min} min Z1–Z2 before any moderate-intensity work."
        )
    else:
        note = (
            f"First hard interval is at km {first_climb_km}. Ensure at least "
            f"{min_warmup_min} min of Z1–Z2 precedes it. If the natural pre-climb "
            f"terrain provides less than that, prepend explicit warm-up steps."
        )
    return {
        "min_duration_minutes": min_warmup_min,
        "first_climb_km": first_climb_km,
        "note": note,
    }


def _composition_tips() -> list[str]:
    """Hints for how Claude should turn the structured data into a workout description."""
    return [
        "CRITICAL: Workout steps MUST be distance-based, never time-based. Every climb "
        "and every recovery segment in this response carries a `suggested_step` field "
        "with a ready-to-paste DSL line (e.g. '- 1.6km Z4'). Use these literally — "
        "do not convert lengths to durations. Time-based steps drift relative to the "
        "terrain and put hard efforts on descents or intersections.",
        "Units in workout DSL: Xkm/Xm = distance, Xmin/Xs = time. The token 'm' is "
        "metres, never minutes. If you ever need a time-based step (e.g. a warm-up), "
        "write '10min', never '10m'.",
        "Prepend a 10s Z1 prep step before each hard interval — the Garmin shows this "
        "as a distinct step with a countdown, giving the rider a clear 'about to start' cue.",
        "Never place a hard interval on a segment with character 'descent' or "
        "'shallow_descent'. Hard intervals require terrain that loads the legs.",
        "If a desired hard interval is longer than the steep climb allows, extend it "
        "into an adjacent 'shallow_rise' segment (immediately before or after the climb). "
        "Never extend a hard interval into descending terrain.",
    ]


def _build_analysis(
    climbs_data: list[dict[str, Any]],
    total_distance_km: float,
    sport: str,
) -> dict[str, Any]:
    warmup = _warmup_recommendation(climbs_data, sport)

    if not climbs_data:
        return {
            "summary": (
                "No climbs detected on this route at the configured thresholds. "
                "Consider lowering min_gradient_percent or min_length_m, or use this "
                "route for a steady endurance ride."
            ),
            "eligible_climb_count": 0,
            "total_climbing_time_s": 0,
            "warmup_recommendation": warmup,
            "composition_tips": _composition_tips(),
        }

    eligible = [d for d in climbs_data if d["eligible_for_hard_effort"]]
    total_time = sum(d["est_duration_s"] for d in eligible)

    zone_breakdown: dict[str, int] = {}
    for d in eligible:
        zone_breakdown[d["suggested_zone"]] = zone_breakdown.get(d["suggested_zone"], 0) + 1

    summary = (
        f"{len(eligible)} climb(s) eligible for hard intervals on this "
        f"{total_distance_km:.1f} km route, ~{total_time // 60} min of total climbing time "
        f"if ridden/run at threshold. Place hard efforts on the eligible climbs (and "
        f"optionally extend into adjacent shallow_rise segments). Recover on flats and "
        f"descents. Always include a warm-up before the first hard effort — see "
        f"warmup_recommendation."
    )

    return {
        "summary": summary,
        "eligible_climb_count": len(eligible),
        "total_climbing_time_s": total_time,
        "suggested_zone_breakdown": zone_breakdown,
        "warmup_recommendation": warmup,
        "composition_tips": _composition_tips(),
    }


async def analyze_route_climbs(
    gpx_path: Annotated[
        str | None,
        "Path to a GPX file on the MCP server's filesystem. Use this when the GPX "
        "is already on the server (e.g. uploaded to a shared NAS folder).",
    ] = None,
    gpx_content: Annotated[
        str | None,
        "Raw GPX XML content as a string. Use this when the user attaches a GPX "
        "file to the conversation — read its contents and pass them here. "
        "Mutually exclusive with gpx_path: exactly one must be provided.",
    ] = None,
    sport: Annotated[
        Literal["cycling", "running"],
        "Climb-detection profile. cycling: 3% / 200 m; running: 4% / 50 m.",
    ] = "cycling",
    min_gradient_percent: Annotated[
        float | None,
        "Override the default min gradient threshold (percent).",
    ] = None,
    min_length_m: Annotated[
        float | None,
        "Override the default min climb length (meters).",
    ] = None,
    ctx: Context | None = None,
) -> str:
    """Detect climbs on a GPX route for terrain-aware workout planning.

    Parses a GPX route, smooths the elevation profile, and segments the route into
    climbs and recovery sections. Each climb is annotated with category, an estimated
    duration at threshold effort, and a suggested training zone. Use this when
    composing a distance-locked workout that should line up with the route's
    geography — hard efforts on climbs, recovery on flats and descents.

    Two ways to supply the route, pick exactly one:
    - gpx_path: a path on the MCP server's filesystem (e.g. a folder on the NAS
      that is mounted into the Docker container).
    - gpx_content: the raw GPX XML as a string. Use this when the user attaches a
      GPX file to the Claude conversation — read the file's contents and pass them
      here. The MCP server never sees the user's local files, so for remote MCP
      deployments this is usually the right path.

    Output is consumed by Claude to compose a workout description and push it via
    the existing create_event tool.

    Args:
        gpx_path: Path to a GPX file on the server's filesystem.
        gpx_content: Raw GPX XML content as a string.
        sport: "cycling" (3% / 200 m defaults) or "running" (4% / 50 m).
        min_gradient_percent: Optional override for min gradient (percent).
        min_length_m: Optional override for min climb length (meters).

    Returns:
        JSON string with route_summary, climbs, recovery_segments, elevation_profile,
        and an analysis section with workout-planning hints.
    """
    # Middleware still validates credentials, but this tool reads only local data.
    _ = ctx

    if (gpx_path is None) == (gpx_content is None):
        return ResponseBuilder.build_error_response(
            "Provide exactly one of gpx_path or gpx_content (not both, not neither).",
            error_type="validation_error",
        )

    try:
        base = _PROFILES[sport]
        profile = SportProfile(
            min_gradient_pct=(
                min_gradient_percent if min_gradient_percent is not None else base.min_gradient_pct
            ),
            min_length_m=min_length_m if min_length_m is not None else base.min_length_m,
            recovery_tolerance_m=base.recovery_tolerance_m,
        )

        # Smooth over ~min_length / 4 of distance so short climbs aren't blurred
        # away while real-world GPS noise still gets filtered. With cycling's
        # 200 m min length this is ±50 m; with running's 50 m it's ±12.5 m.
        half_window_m = max(5.0, profile.min_length_m / 4.0)

        source_label: str
        try:
            if gpx_path is not None:
                resolved_path = Path(gpx_path).expanduser()
                points, name = _parse_from_path(resolved_path, half_window_m=half_window_m)
                source_label = str(resolved_path)
            else:
                assert gpx_content is not None  # narrowed by the exclusivity check above
                points, name = _parse_from_content(gpx_content, half_window_m=half_window_m)
                source_label = "inline_content"
        except FileNotFoundError as e:
            return ResponseBuilder.build_error_response(
                str(e),
                error_type="route_parse_error",
                suggestions=[
                    "Verify the path is correct and accessible to the MCP server process.",
                    "On the NAS deployment, place GPX files in a folder mounted into the Docker container.",
                    "If the user uploaded the GPX to the Claude conversation, pass its contents via gpx_content instead.",
                ],
            )
        except ValueError as e:
            return ResponseBuilder.build_error_response(str(e), error_type="route_parse_error")

        climbs = _detect_climbs(points, profile)

        climbs_data: list[dict[str, Any]] = []
        for i, c in enumerate(climbs):
            duration_s = _estimate_climb_duration_s(c, sport)
            category = (
                _categorise_climb_cycling(c) if sport == "cycling" else _categorise_climb_running(c)
            )
            climb_dict: dict[str, Any] = {
                "climb_index": i,
                "start_km": round(c.start_km, 3),
                "end_km": round(c.end_km, 3),
                "length_m": round(c.length_m, 1),
                "elevation_gain_m": round(c.elevation_gain_m, 1),
                "avg_gradient_percent": round(c.avg_gradient_pct, 2),
                "max_gradient_percent": round(c.max_gradient_pct, 2),
                "category": category,
                "est_duration_s": duration_s,
                "eligible_for_hard_effort": c.avg_gradient_pct >= profile.min_gradient_pct,
                "suggested_zone": _suggested_zone(duration_s),
            }
            climb_dict["suggested_step"] = _climb_suggested_step(climb_dict)
            climbs_data.append(climb_dict)

        total_distance_m = points[-1].cum_dist_m
        elevation_gain = sum(
            max(0.0, points[i + 1].ele - points[i].ele) for i in range(len(points) - 1)
        )
        elevation_loss = sum(
            max(0.0, points[i].ele - points[i + 1].ele) for i in range(len(points) - 1)
        )

        route_summary: dict[str, Any] = {
            "name": name,
            "total_distance_km": round(total_distance_m / 1000.0, 3),
            "total_elevation_gain_m": round(elevation_gain, 1),
            "total_elevation_loss_m": round(elevation_loss, 1),
            "point_count": len(points),
        }

        recovery_segments = _build_recovery_segments(
            climbs, points, climb_threshold_pct=profile.min_gradient_pct
        )
        elevation_profile = _downsample_profile(points)
        analysis = _build_analysis(climbs_data, total_distance_m / 1000.0, sport)

        return ResponseBuilder.build_response(
            data={
                "route_summary": route_summary,
                "climbs": climbs_data,
                "recovery_segments": recovery_segments,
                "elevation_profile": elevation_profile,
            },
            analysis=analysis,
            metadata={
                "source": source_label,
                "sport_profile": sport,
                "thresholds": {
                    "min_gradient_percent": profile.min_gradient_pct,
                    "min_length_m": profile.min_length_m,
                    "recovery_tolerance_m": profile.recovery_tolerance_m,
                },
            },
            query_type="route_climbs",
        )
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error analyzing route: {e}", error_type="internal_error"
        )
