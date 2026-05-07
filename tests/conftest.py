"""Pytest configuration and shared fixtures."""

import pytest
import respx

from intervals_icu_mcp.auth import ICUConfig


@pytest.fixture
def mock_config():
    """Provide a mock ICU configuration for testing."""
    return ICUConfig(
        intervals_icu_api_key="test_api_key_12345",
        intervals_icu_athlete_id="i123456",
    )


@pytest.fixture
def respx_mock():
    """Provide a respx mock router for HTTP requests."""
    with respx.mock(
        base_url="https://intervals.icu/api/v1",
        assert_all_called=False,
    ) as respx_mock:
        yield respx_mock


@pytest.fixture
def mock_athlete_data():
    """Sample athlete data for testing."""
    return {
        "id": "i123456",
        "name": "Test Athlete",
        "email": "test@example.com",
        "weight": 70.0,
        "ctl": 50.0,
        "atl": 35.0,
        "tsb": 15.0,
        "ramp_rate": 3.5,
        "sport_settings": [
            {
                "id": 1,
                "type": "Ride",
                "ftp": 250,
                "fthr": 165,
            }
        ],
    }


@pytest.fixture
def mock_activity_data():
    """Sample activity data for testing."""
    return {
        "id": "12345",
        "start_date_local": "2025-10-13T08:00:00",
        "name": "Morning Ride",
        "type": "Ride",
        "distance": 50000.0,  # meters
        "moving_time": 7200,  # seconds
        "elapsed_time": 7500,
        "total_elevation_gain": 500.0,
        "average_speed": 6.94,  # m/s
        "average_watts": 200,
        "normalized_power": 210,
        "average_heartrate": 145,
        "icu_training_load": 120,
        "icu_intensity": 0.84,
    }


@pytest.fixture
def mock_wellness_data():
    """Sample wellness data for testing."""
    return {
        "id": "2025-10-13",
        "weight": 70.0,
        "restingHR": 48,
        "hrv": 65.5,
        "hrvSDNN": 75.2,
        "sleepSecs": 28800,  # 8 hours
        "sleepQuality": 8,
        "sleepScore": 85.0,
        "fatigue": 3,
        "soreness": 2,
        "stress": 2,
        "mood": 8,
        "motivation": 9,
        "ctl": 50.0,
        "atl": 35.0,
        "tsb": 15.0,
    }


@pytest.fixture
def mock_event_data():
    """Sample event data for testing."""
    return {
        "id": 1001,
        "start_date_local": "2025-10-14",
        "category": "WORKOUT",
        "name": "Threshold Intervals",
        "type": "Ride",
        "description": "5x5min @ FTP",
        "moving_time": 3600,
        "icu_training_load": 100,
        "icu_intensity": 0.90,
    }


@pytest.fixture
def mock_power_curve_data():
    """Sample power curve data matching DataCurveSetPowerCurve API response."""
    return {
        "list": [
            {
                "id": "1y",
                "label": "past year",
                "start_date_local": "2025-03-24",
                "end_date_local": "2026-03-24",
                "secs": [5, 60, 300, 1200, 3600],
                "values": [800, 400, 300, 250, 200],
                "activity_id": ["act1", "act2", "act3", "act4", "act5"],
            }
        ],
        "activities": {},
    }
