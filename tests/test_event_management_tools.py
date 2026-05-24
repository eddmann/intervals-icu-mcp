"""Tests for event_management helpers.

Focused on the metric-detection + summary-line logic added after a run was
prescribed with power targets in Z1-Z2 (a bad fit for low-intensity running).
The summary line gives the user a one-line echo at push-time so they catch
prescription-type mistakes before lacing up.
"""

from intervals_icu_mcp.tools.event_management import (
    _build_summary_line,
    _detect_primary_metric,
)


class TestDetectPrimaryMetric:
    def test_power_only_description(self):
        desc = "Warmup\n- 10min Z2\n\nMain Set 3x\n- 5min 95%\n- 3min 50%"
        assert _detect_primary_metric(desc) == "power"

    def test_explicit_watts(self):
        assert _detect_primary_metric("- 20min 250w") == "power"

    def test_hr_dominant_description(self):
        desc = "Warmup\n- 10min < 140bpm\n\nMain Set\n- 30min 75% HR"
        assert _detect_primary_metric(desc) == "heart_rate"

    def test_pace_dominant_description(self):
        desc = "- 1km @ 4:30/km\n- 5km @ 5:00/km easy"
        assert _detect_primary_metric(desc) == "pace"

    def test_zone_only_returns_zone_only(self):
        """`Z3`, `Z4` etc. without explicit metric markers — the device uses sport default."""
        desc = "Warmup\n- 10min Z1\n\nMain Set\n- 20min Z3\n\nCooldown\n- 5min Z1"
        assert _detect_primary_metric(desc) == "zone_only"

    def test_empty_description_returns_unknown(self):
        assert _detect_primary_metric(None) == "unknown"
        assert _detect_primary_metric("") == "unknown"

    def test_pct_hr_not_misread_as_power(self):
        """`75% HR` must NOT be counted as a power marker even though `%` is in it."""
        assert _detect_primary_metric("- 30min 75% HR") == "heart_rate"


class TestBuildSummaryLine:
    def test_running_power_workout_flags_power(self):
        """Today's failure mode: easy run prescribed with power. Must echo POWER."""
        line = _build_summary_line(
            name="Easy 10k",
            event_type="Run",
            duration_seconds=3300,
            description="Warmup\n- 10min 55%\n\nMain Set\n- 40min 70%\n\nCooldown\n- 5min 50%",
        )
        assert "Easy 10k" in line
        assert "Run" in line
        assert "POWER-based" in line
        assert "55 min" in line

    def test_running_hr_workout_flags_hr(self):
        line = _build_summary_line(
            name="Easy 10k",
            event_type="Run",
            duration_seconds=3300,
            description="Warmup\n- 10min < 140bpm\n\nMain Set\n- 40min 70% HR",
        )
        assert "HR-based" in line

    def test_zone_only_workout_describes_zone_based(self):
        line = _build_summary_line(
            name="Endurance Ride",
            event_type="Ride",
            duration_seconds=7200,
            description="Warmup\n- 10min Z1\n\nMain Set\n- 90min Z2",
        )
        assert "zone-based" in line

    def test_missing_duration_handled_gracefully(self):
        line = _build_summary_line(
            name="Note",
            event_type=None,
            duration_seconds=None,
            description=None,
        )
        assert "no duration set" in line
        assert "no description" in line.lower()
