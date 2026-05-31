"""Generate synthetic GPX fixtures for route climb-detection tests.

Run this once when fixtures need refreshing:

    uv run python tests/fixtures/routes/_generate.py

Produces deterministic GPX files in this directory. Points are spaced ~20 m apart
so a 200 m climb contains ~10 points (enough for a 5-point smoothing window).
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from pathlib import Path

# 1 degree longitude at the equator ≈ 111_320 m.
METERS_PER_DEGREE = 111_320.0
POINT_SPACING_M = 20.0
LON_STEP = POINT_SPACING_M / METERS_PER_DEGREE
# Synthetic routes are placed at the equator so 1 degree of longitude ≈ 111_320 m
# exactly (no cosine-of-latitude correction needed). Realistic coordinates would
# distort distances and therefore gradients.
START_LAT = 0.0
START_LON = 0.0
BASE_ELEVATION = 100.0


def _gpx(name: str, points: list[tuple[float, float, float | None]]) -> str:
    """Serialize points to a minimal GPX 1.1 XML string."""
    header = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<gpx version="1.1" creator="intervals-icu-mcp tests" '
        'xmlns="http://www.topografix.com/GPX/1/1">\n'
        f"  <name>{name}</name>\n"
        "  <trk>\n"
        f"    <name>{name}</name>\n"
        "    <trkseg>\n"
    )
    body_lines: list[str] = []
    for lat, lon, ele in points:
        if ele is None:
            body_lines.append(f'      <trkpt lat="{lat:.7f}" lon="{lon:.7f}"></trkpt>')
        else:
            body_lines.append(
                f'      <trkpt lat="{lat:.7f}" lon="{lon:.7f}">'
                f"<ele>{ele:.2f}</ele></trkpt>"
            )
    footer = "\n    </trkseg>\n  </trk>\n</gpx>\n"
    return header + "\n".join(body_lines) + footer


def _points_from_profile(
    gradients_by_length: Iterable[tuple[float, float]],
    *,
    include_elevation: bool = True,
) -> list[tuple[float, float, float | None]]:
    """Build trackpoints by walking east at POINT_SPACING_M with given gradient segments.

    gradients_by_length: iterable of (length_m, gradient_percent) pairs.
    """
    points: list[tuple[float, float, float | None]] = []
    lon = START_LON
    elevation = BASE_ELEVATION
    points.append((START_LAT, lon, elevation if include_elevation else None))
    for length_m, gradient_pct in gradients_by_length:
        n_points = max(1, int(round(length_m / POINT_SPACING_M)))
        rise_per_point = POINT_SPACING_M * (gradient_pct / 100.0)
        for _ in range(n_points):
            lon += LON_STEP
            elevation += rise_per_point
            points.append(
                (START_LAT, lon, elevation if include_elevation else None)
            )
    # Floor elevation at 0 so synthetic profiles don't go negative on long descents.
    floored: list[tuple[float, float, float | None]] = []
    for lat, plon, ele in points:
        if ele is not None:
            ele = max(0.0, ele)
        floored.append((lat, plon, ele))
    return floored


def _write(path: Path, name: str, points: list[tuple[float, float, float | None]]) -> None:
    path.write_text(_gpx(name, points))


def main() -> None:
    out_dir = Path(__file__).parent

    # 1) Flat: 10 km of near-flat terrain with tiny oscillation (well below threshold).
    flat = _points_from_profile([(10_000.0, 0.2)])  # 0.2% trend, far below any cycling/running threshold
    _write(out_dir / "flat_route.gpx", "flat_route", flat)

    # 2) Single climb: 2 km flat, 1.6 km @ 6%, 3 km descent.
    single = _points_from_profile(
        [
            (2_000.0, 0.0),
            (1_600.0, 6.0),
            (3_000.0, -3.5),
        ]
    )
    _write(out_dir / "single_climb.gpx", "single_climb", single)

    # 3) Multi-climb: three climbs of varying length / gradient.
    multi = _points_from_profile(
        [
            (1_000.0, 0.0),
            (400.0, 8.0),   # short steep "kicker" (~2 min effort)
            (800.0, -2.0),
            (2_500.0, 5.5),  # threshold-length climb (~7-10 min)
            (1_500.0, -4.0),
            (4_000.0, 4.0),  # long sweet-spot climb (~12-15 min)
            (2_000.0, -3.0),
        ]
    )
    _write(out_dir / "multi_climb.gpx", "multi_climb", multi)

    # 4) Undulating: one climb with a small flat in the middle. Tests recovery tolerance.
    undulating = _points_from_profile(
        [
            (500.0, 0.0),
            (600.0, 5.0),
            (60.0, 0.5),  # 60 m of near-flat inside the climb (below 80 m recovery tolerance)
            (700.0, 5.5),
            (1_000.0, -3.0),
        ]
    )
    _write(out_dir / "undulating.gpx", "undulating", undulating)

    # 5) No elevation: same shape as single_climb but trackpoints have no <ele>.
    no_ele = _points_from_profile(
        [(2_000.0, 0.0), (1_600.0, 6.0), (3_000.0, -3.5)],
        include_elevation=False,
    )
    _write(out_dir / "no_elevation.gpx", "no_elevation", no_ele)

    # 6) Running-scale: a shorter route with smaller climbs to exercise the running profile.
    running = _points_from_profile(
        [
            (300.0, 0.0),
            (80.0, 6.0),   # ~80 m climb @ 6% — meets running thresholds (50 m, 4%), below cycling (200 m).
            (200.0, -3.0),
            (120.0, 5.0),
            (400.0, -2.0),
        ]
    )
    _write(out_dir / "running_route.gpx", "running_route", running)

    print(f"Wrote 6 GPX fixtures to {out_dir}")


# Suppress unused-import warning for math; kept available for future profiles.
_ = math

if __name__ == "__main__":
    main()
