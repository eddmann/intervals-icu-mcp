"""Async HTTP client for Intervals.icu API."""

from typing import Any

import httpx
from pydantic import TypeAdapter

from .auth import ICUConfig
from .models import (
    Activity,
    ActivitySearchResult,
    ActivityStreams,
    ActivitySummary,
    Athlete,
    AthleteTrainingPlan,
    BestEffort,
    Event,
    Folder,
    Gear,
    GearReminder,
    Histogram,
    HRCurve,
    Interval,
    PaceCurve,
    PowerCurve,
    SharedWith,
    SportSettings,
    Wellness,
    Workout,
)


class ICUAPIError(Exception):
    """Custom exception for Intervals.icu API errors."""

    def __init__(self, message: str, status_code: int | None = None):
        """Initialize API error.

        Args:
            message: Error message
            status_code: HTTP status code if available
        """
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class ICUClient:
    """Async HTTP client for Intervals.icu API with automatic error handling."""

    BASE_URL = "https://intervals.icu/api/v1"

    def __init__(self, config: ICUConfig):
        """Initialize the Intervals.icu API client.

        Args:
            config: ICUConfig with API credentials
        """
        self.config = config
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "ICUClient":
        """Async context manager entry."""
        # Use Basic Auth with username "API_KEY" and password as the actual API key
        auth = httpx.BasicAuth(username="API_KEY", password=self.config.intervals_icu_api_key)

        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            timeout=30.0,
            auth=auth,
        )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        """Async context manager exit."""
        if self._client:
            await self._client.aclose()

    async def _request(
        self,
        method: str,
        endpoint: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """Make an authenticated request to the API.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint path
            **kwargs: Additional arguments for httpx.request

        Returns:
            httpx.Response object

        Raises:
            ICUAPIError: If the request fails
        """
        if not self._client:
            raise RuntimeError("Client not initialized. Use async context manager.")

        try:
            response = await self._client.request(method, endpoint, **kwargs)

            # Handle specific error codes
            if response.status_code == 401:
                raise ICUAPIError("Unauthorized. Check your API key and athlete ID.", 401)

            if response.status_code == 404:
                raise ICUAPIError("Resource not found.", 404)

            if response.status_code == 429:
                raise ICUAPIError("Rate limit exceeded. Please try again later.", 429)

            response.raise_for_status()
            return response

        except httpx.HTTPStatusError as e:
            raise ICUAPIError(
                f"HTTP {e.response.status_code}: {e.response.text}",
                e.response.status_code,
            ) from e
        except httpx.RequestError as e:
            raise ICUAPIError(f"Request failed: {str(e)}") from e

    # ==================== Athlete Endpoints ====================

    async def get_athlete(self, athlete_id: str | None = None) -> Athlete:
        """Get athlete profile with sport settings.

        Args:
            athlete_id: Athlete ID (uses config default if not provided)

        Returns:
            Athlete model with full profile information
        """
        athlete_id = athlete_id or self.config.intervals_icu_athlete_id
        response = await self._request("GET", f"/athlete/{athlete_id}")
        return Athlete(**response.json())

    # ==================== Activity Endpoints ====================

    async def get_activities(
        self,
        athlete_id: str | None = None,
        oldest: str | None = None,
        newest: str | None = None,
        limit: int = 30,
    ) -> list[ActivitySummary]:
        """List activities for a date range.

        Args:
            athlete_id: Athlete ID (uses config default if not provided)
            oldest: Oldest date to fetch (ISO-8601 format)
            newest: Newest date to fetch (ISO-8601 format)
            limit: Maximum number of activities to return

        Returns:
            List of ActivitySummary objects
        """
        athlete_id = athlete_id or self.config.intervals_icu_athlete_id
        params = {}

        if oldest:
            params["oldest"] = oldest
        if newest:
            params["newest"] = newest

        response = await self._request("GET", f"/athlete/{athlete_id}/activities", params=params)
        adapter = TypeAdapter(list[ActivitySummary])
        activities = adapter.validate_python(response.json())

        # Limit results
        return activities[:limit]

    async def get_activity(self, athlete_id: str | None = None, activity_id: str = "") -> Activity:
        """Get detailed activity information.

        Args:
            athlete_id: Athlete ID (uses config default if not provided)
            activity_id: Activity ID to fetch

        Returns:
            Activity model with full details
        """
        athlete_id = athlete_id or self.config.intervals_icu_athlete_id
        response = await self._request("GET", f"/activity/{activity_id}")
        return Activity(**response.json())

    async def search_activities(
        self,
        athlete_id: str | None = None,
        query: str = "",
        limit: int = 30,
    ) -> list[ActivitySearchResult]:
        """Search for activities by name or tag.

        Args:
            athlete_id: Athlete ID (uses config default if not provided)
            query: Search query (name or tag)
            limit: Maximum number of results to return

        Returns:
            List of ActivitySearchResult objects
        """
        athlete_id = athlete_id or self.config.intervals_icu_athlete_id
        params = {"q": query}

        response = await self._request(
            "GET", f"/athlete/{athlete_id}/activities/search", params=params
        )
        adapter = TypeAdapter(list[ActivitySearchResult])
        results = adapter.validate_python(response.json())

        return results[:limit]

    async def search_activities_full(
        self,
        athlete_id: str | None = None,
        query: str = "",
        limit: int = 30,
    ) -> list[Activity]:
        """Search for activities by name or tag, returning full Activity objects.

        Args:
            athlete_id: Athlete ID (uses config default if not provided)
            query: Search query (name or tag)
            limit: Maximum number of results to return

        Returns:
            List of full Activity objects
        """
        athlete_id = athlete_id or self.config.intervals_icu_athlete_id
        params = {"q": query}

        response = await self._request(
            "GET", f"/athlete/{athlete_id}/activities/search-full", params=params
        )
        adapter = TypeAdapter(list[Activity])
        results = adapter.validate_python(response.json())

        return results[:limit]

    async def get_activities_around(
        self,
        activity_id: str,
        athlete_id: str | None = None,
        count: int = 5,
    ) -> list[Activity]:
        """Get activities before and after a specific activity.

        Args:
            activity_id: The reference activity ID
            athlete_id: Athlete ID (uses config default if not provided)
            count: Number of activities to return before and after (default 5)

        Returns:
            List of Activity objects around the reference activity
        """
        athlete_id = athlete_id or self.config.intervals_icu_athlete_id
        params = {"id": activity_id, "count": count}

        response = await self._request(
            "GET", f"/athlete/{athlete_id}/activities-around", params=params
        )
        adapter = TypeAdapter(list[Activity])
        return adapter.validate_python(response.json())

    async def update_activity(
        self,
        activity_id: str,
        activity_data: dict[str, Any],
    ) -> Activity:
        """Update an existing activity.

        Args:
            activity_id: Activity ID
            activity_data: Activity data dictionary with fields to update

        Returns:
            Updated Activity object
        """
        response = await self._request("PUT", f"/activity/{activity_id}", json=activity_data)
        return Activity(**response.json())

    async def delete_activity(
        self,
        activity_id: str,
    ) -> bool:
        """Delete an activity.

        Args:
            activity_id: Activity ID

        Returns:
            True if deletion was successful
        """
        await self._request("DELETE", f"/activity/{activity_id}")
        return True

    async def download_activity_file(
        self,
        activity_id: str,
    ) -> bytes:
        """Download the original activity file.

        Args:
            activity_id: Activity ID

        Returns:
            File content as bytes
        """
        response = await self._request("GET", f"/activity/{activity_id}/file")
        return response.content

    async def download_fit_file(
        self,
        activity_id: str,
    ) -> bytes:
        """Download activity as FIT file.

        Args:
            activity_id: Activity ID

        Returns:
            FIT file content as bytes
        """
        response = await self._request("GET", f"/activity/{activity_id}/fit-file")
        return response.content

    async def download_gpx_file(
        self,
        activity_id: str,
    ) -> bytes:
        """Download activity as GPX file.

        Args:
            activity_id: Activity ID

        Returns:
            GPX file content as bytes
        """
        response = await self._request("GET", f"/activity/{activity_id}/gpx-file")
        return response.content

    async def get_power_histogram(
        self,
        activity_id: str,
    ) -> Histogram:
        """Get power distribution histogram for an activity.

        Args:
            activity_id: Activity ID

        Returns:
            Histogram with power distribution bins
        """
        response = await self._request("GET", f"/activity/{activity_id}/power-histogram")
        return Histogram(**response.json())

    async def get_hr_histogram(
        self,
        activity_id: str,
    ) -> Histogram:
        """Get heart rate distribution histogram for an activity.

        Args:
            activity_id: Activity ID

        Returns:
            Histogram with HR distribution bins
        """
        response = await self._request("GET", f"/activity/{activity_id}/hr-histogram")
        return Histogram(**response.json())

    async def get_pace_histogram(
        self,
        activity_id: str,
    ) -> Histogram:
        """Get pace distribution histogram for an activity.

        Args:
            activity_id: Activity ID

        Returns:
            Histogram with pace distribution bins
        """
        response = await self._request("GET", f"/activity/{activity_id}/pace-histogram")
        return Histogram(**response.json())

    async def get_gap_histogram(
        self,
        activity_id: str,
    ) -> Histogram:
        """Get grade-adjusted pace (GAP) histogram for an activity.

        Args:
            activity_id: Activity ID

        Returns:
            Histogram with GAP distribution bins
        """
        response = await self._request("GET", f"/activity/{activity_id}/gap-histogram")
        return Histogram(**response.json())

    # ==================== Wellness Endpoints ====================

    async def get_wellness(
        self,
        athlete_id: str | None = None,
        oldest: str | None = None,
        newest: str | None = None,
    ) -> list[Wellness]:
        """Get wellness records for a date range.

        Args:
            athlete_id: Athlete ID (uses config default if not provided)
            oldest: Oldest date to fetch (ISO-8601 format)
            newest: Newest date to fetch (ISO-8601 format)

        Returns:
            List of Wellness records
        """
        athlete_id = athlete_id or self.config.intervals_icu_athlete_id
        params = {}

        if oldest:
            params["oldest"] = oldest
        if newest:
            params["newest"] = newest

        response = await self._request("GET", f"/athlete/{athlete_id}/wellness", params=params)
        adapter = TypeAdapter(list[Wellness])
        return adapter.validate_python(response.json())

    async def get_wellness_for_date(
        self,
        date: str,
        athlete_id: str | None = None,
    ) -> Wellness:
        """Get wellness record for a specific date.

        Args:
            date: Date in ISO-8601 format (YYYY-MM-DD)
            athlete_id: Athlete ID (uses config default if not provided)

        Returns:
            Wellness record for the specified date
        """
        athlete_id = athlete_id or self.config.intervals_icu_athlete_id
        response = await self._request("GET", f"/athlete/{athlete_id}/wellness/{date}")
        return Wellness(**response.json())

    async def update_wellness(
        self,
        wellness_data: dict[str, Any],
        athlete_id: str | None = None,
    ) -> Wellness:
        """Update wellness record (creates if doesn't exist).

        Args:
            wellness_data: Wellness data dictionary (must include 'id' as date)
            athlete_id: Athlete ID (uses config default if not provided)

        Returns:
            Updated Wellness record
        """
        athlete_id = athlete_id or self.config.intervals_icu_athlete_id
        response = await self._request("PUT", f"/athlete/{athlete_id}/wellness", json=wellness_data)
        return Wellness(**response.json())

    async def update_wellness_by_date(
        self,
        date: str,
        wellness_data: dict[str, Any],
        athlete_id: str | None = None,
    ) -> Wellness:
        """Update wellness record for a specific date.

        Args:
            date: Date in ISO-8601 format (YYYY-MM-DD)
            wellness_data: Wellness data dictionary
            athlete_id: Athlete ID (uses config default if not provided)

        Returns:
            Updated Wellness record
        """
        athlete_id = athlete_id or self.config.intervals_icu_athlete_id
        response = await self._request(
            "PUT", f"/athlete/{athlete_id}/wellness/{date}", json=wellness_data
        )
        return Wellness(**response.json())

    async def update_wellness_bulk(
        self,
        wellness_records: list[dict[str, Any]],
        athlete_id: str | None = None,
    ) -> list[Wellness]:
        """Bulk update wellness records.

        Args:
            wellness_records: List of wellness data dictionaries (each must include 'id' as date)
            athlete_id: Athlete ID (uses config default if not provided)

        Returns:
            List of updated Wellness records
        """
        athlete_id = athlete_id or self.config.intervals_icu_athlete_id
        response = await self._request(
            "PUT", f"/athlete/{athlete_id}/wellness-bulk", json=wellness_records
        )
        adapter = TypeAdapter(list[Wellness])
        return adapter.validate_python(response.json())

    # ==================== Event/Calendar Endpoints ====================

    async def get_events(
        self,
        athlete_id: str | None = None,
        oldest: str | None = None,
        newest: str | None = None,
    ) -> list[Event]:
        """Get calendar events (planned workouts, notes, races).

        Args:
            athlete_id: Athlete ID (uses config default if not provided)
            oldest: Oldest date to fetch (ISO-8601 format)
            newest: Newest date to fetch (ISO-8601 format)

        Returns:
            List of Event objects
        """
        athlete_id = athlete_id or self.config.intervals_icu_athlete_id
        params = {}

        if oldest:
            params["oldest"] = oldest
        if newest:
            params["newest"] = newest

        response = await self._request("GET", f"/athlete/{athlete_id}/events", params=params)
        adapter = TypeAdapter(list[Event])
        return adapter.validate_python(response.json())

    async def get_event(
        self,
        event_id: int,
        athlete_id: str | None = None,
    ) -> Event:
        """Get a specific event.

        Args:
            event_id: Event ID
            athlete_id: Athlete ID (uses config default if not provided)

        Returns:
            Event object
        """
        athlete_id = athlete_id or self.config.intervals_icu_athlete_id
        response = await self._request("GET", f"/athlete/{athlete_id}/events/{event_id}")
        return Event(**response.json())

    # ==================== Performance Curve Endpoints ====================

    async def get_power_curves(
        self,
        athlete_id: str | None = None,
        oldest: str | None = None,
        newest: str | None = None,
        sport_type: str = "Ride",
    ) -> PowerCurve:
        """Get power curve data (best efforts for various durations).

        Args:
            athlete_id: Athlete ID (uses config default if not provided)
            oldest: Oldest date to include (ISO-8601 format)
            newest: Newest date to include (ISO-8601 format)
            sport_type: Sport type (e.g. "Ride", "Run", "Swim"). Required by API.

        Returns:
            PowerCurve with best efforts data
        """
        from datetime import date as _date

        athlete_id = athlete_id or self.config.intervals_icu_athlete_id

        # API uses a 'curves' param: e.g. "1y", "42d", "r.2025-01-01.2025-12-31"
        if oldest:
            end = newest or _date.today().isoformat()
            curves = f"r.{oldest}.{end}"
        else:
            curves = "1y"

        params: dict[str, str] = {"type": sport_type, "curves": curves}

        # Endpoint requires .json extension; returns DataCurveSetPowerCurve
        response = await self._request(
            "GET", f"/athlete/{athlete_id}/power-curves.json", params=params
        )
        data = response.json()
        curves_list = data.get("list", [])
        if not curves_list:
            return PowerCurve()
        return PowerCurve(**curves_list[0])

    async def get_hr_curves(
        self,
        athlete_id: str | None = None,
        oldest: str | None = None,
        newest: str | None = None,
    ) -> HRCurve:
        """Get heart rate curve data (best efforts for various durations).

        Args:
            athlete_id: Athlete ID (uses config default if not provided)
            oldest: Oldest date to include (ISO-8601 format)
            newest: Newest date to include (ISO-8601 format)

        Returns:
            HRCurve with best efforts data
        """
        athlete_id = athlete_id or self.config.intervals_icu_athlete_id
        params = {}

        if oldest:
            params["oldest"] = oldest
        if newest:
            params["newest"] = newest

        response = await self._request("GET", f"/athlete/{athlete_id}/hr-curves", params=params)
        return HRCurve(**response.json())

    async def get_pace_curves(
        self,
        athlete_id: str | None = None,
        oldest: str | None = None,
        newest: str | None = None,
        use_gap: bool = False,
    ) -> PaceCurve:
        """Get pace curve data (best efforts for various durations).

        Args:
            athlete_id: Athlete ID (uses config default if not provided)
            oldest: Oldest date to include (ISO-8601 format)
            newest: Newest date to include (ISO-8601 format)
            use_gap: Use Grade Adjusted Pace for running (default False)

        Returns:
            PaceCurve with best efforts data
        """
        athlete_id = athlete_id or self.config.intervals_icu_athlete_id
        params = {}

        if oldest:
            params["oldest"] = oldest
        if newest:
            params["newest"] = newest
        if use_gap:
            params["gap"] = "true"

        response = await self._request("GET", f"/athlete/{athlete_id}/pace-curves", params=params)
        return PaceCurve(**response.json())

    # ==================== Workout Library Endpoints ====================

    async def get_workout_folders(
        self,
        athlete_id: str | None = None,
    ) -> list[Folder]:
        """Get workout folders and training plans.

        Args:
            athlete_id: Athlete ID (uses config default if not provided)

        Returns:
            List of folders/plans with workouts
        """
        athlete_id = athlete_id or self.config.intervals_icu_athlete_id
        response = await self._request("GET", f"/athlete/{athlete_id}/folders")
        adapter = TypeAdapter(list[Folder])
        return adapter.validate_python(response.json())

    # ==================== Activity Analysis Endpoints ====================

    async def get_activity_intervals(
        self,
        activity_id: str,
    ) -> list[Interval]:
        """Get intervals for a specific activity.

        Args:
            activity_id: Activity ID

        Returns:
            List of Interval objects
        """
        response = await self._request("GET", f"/activity/{activity_id}/intervals")
        adapter = TypeAdapter(list[Interval])
        return adapter.validate_python(response.json())

    async def get_activity_streams(
        self,
        activity_id: str,
        streams: list[str] | None = None,
    ) -> ActivityStreams:
        """Get time-series data streams for an activity.

        Args:
            activity_id: Activity ID
            streams: List of stream types to fetch (e.g., ["watts", "heartrate"])
                    If None, fetches all available streams

        Returns:
            ActivityStreams object with time-series data
        """
        params = {}
        if streams:
            params["types"] = ",".join(streams)

        response = await self._request("GET", f"/activity/{activity_id}/streams", params=params)
        # API returns a list of stream objects: [{type, name, data, ...}, ...]
        # Convert to a dict keyed by stream type for the ActivityStreams model
        streams_dict: dict[str, Any] = {}
        for stream_obj in response.json():
            stream_type = stream_obj.get("type")
            stream_data = stream_obj.get("data")
            if stream_type and stream_data is not None:
                streams_dict[stream_type] = stream_data
        return ActivityStreams(**streams_dict)

    async def get_best_efforts(
        self,
        activity_id: str,
    ) -> list[BestEffort]:
        """Get best efforts for an activity.

        Args:
            activity_id: Activity ID

        Returns:
            List of BestEffort objects
        """
        response = await self._request("GET", f"/activity/{activity_id}/best-efforts")
        adapter = TypeAdapter(list[BestEffort])
        return adapter.validate_python(response.json())

    async def search_intervals(
        self,
        athlete_id: str | None = None,
        interval_type: str | None = None,
        min_duration: int | None = None,
        max_duration: int | None = None,
        limit: int = 30,
    ) -> list[dict[str, Any]]:
        """Search for intervals across activities.

        Args:
            athlete_id: Athlete ID (uses config default if not provided)
            interval_type: Type of interval to search for
            min_duration: Minimum duration in seconds
            max_duration: Maximum duration in seconds
            limit: Maximum number of results to return

        Returns:
            List of matching intervals with activity context
        """
        athlete_id = athlete_id or self.config.intervals_icu_athlete_id
        params = {}

        if interval_type:
            params["type"] = interval_type
        if min_duration:
            params["minDuration"] = min_duration
        if max_duration:
            params["maxDuration"] = max_duration

        response = await self._request(
            "GET", f"/athlete/{athlete_id}/activities/interval-search", params=params
        )
        results = response.json()
        return results[:limit]

    # ==================== Workout Library Endpoints ====================

    async def get_workouts_in_folder(
        self,
        folder_id: int,
        athlete_id: str | None = None,
    ) -> list[Workout]:
        """Get workouts in a specific folder.

        Args:
            folder_id: Folder ID
            athlete_id: Athlete ID (uses config default if not provided)

        Returns:
            List of Workout objects
        """
        athlete_id = athlete_id or self.config.intervals_icu_athlete_id
        response = await self._request("GET", f"/athlete/{athlete_id}/folders/{folder_id}/workouts")
        adapter = TypeAdapter(list[Workout])
        return adapter.validate_python(response.json())

    # ==================== Event Write Operations ====================

    async def create_event(
        self,
        event_data: dict[str, Any],
        athlete_id: str | None = None,
    ) -> Event:
        """Create a new calendar event.

        Args:
            event_data: Event data dictionary
            athlete_id: Athlete ID (uses config default if not provided)

        Returns:
            Created Event object
        """
        athlete_id = athlete_id or self.config.intervals_icu_athlete_id
        response = await self._request("POST", f"/athlete/{athlete_id}/events", json=event_data)
        return Event(**response.json())

    async def update_event(
        self,
        event_id: int,
        event_data: dict[str, Any],
        athlete_id: str | None = None,
    ) -> Event:
        """Update an existing calendar event.

        Args:
            event_id: Event ID
            event_data: Updated event data dictionary
            athlete_id: Athlete ID (uses config default if not provided)

        Returns:
            Updated Event object
        """
        athlete_id = athlete_id or self.config.intervals_icu_athlete_id
        response = await self._request(
            "PUT", f"/athlete/{athlete_id}/events/{event_id}", json=event_data
        )
        return Event(**response.json())

    async def delete_event(
        self,
        event_id: int,
        athlete_id: str | None = None,
    ) -> bool:
        """Delete a calendar event.

        Args:
            event_id: Event ID
            athlete_id: Athlete ID (uses config default if not provided)

        Returns:
            True if deletion was successful
        """
        athlete_id = athlete_id or self.config.intervals_icu_athlete_id
        await self._request("DELETE", f"/athlete/{athlete_id}/events/{event_id}")
        return True

    # ==================== Gear Endpoints ====================

    async def get_gear(
        self,
        athlete_id: str | None = None,
    ) -> list[Gear]:
        """Get all gear items for an athlete.

        Args:
            athlete_id: Athlete ID (uses config default if not provided)

        Returns:
            List of Gear objects
        """
        athlete_id = athlete_id or self.config.intervals_icu_athlete_id
        response = await self._request("GET", f"/athlete/{athlete_id}/gear")
        adapter = TypeAdapter(list[Gear])
        return adapter.validate_python(response.json())

    async def create_gear(
        self,
        gear_data: dict[str, Any],
        athlete_id: str | None = None,
    ) -> Gear:
        """Create a new gear item.

        Args:
            gear_data: Gear data dictionary
            athlete_id: Athlete ID (uses config default if not provided)

        Returns:
            Created Gear object
        """
        athlete_id = athlete_id or self.config.intervals_icu_athlete_id
        response = await self._request("POST", f"/athlete/{athlete_id}/gear", json=gear_data)
        return Gear(**response.json())

    async def update_gear(
        self,
        gear_id: str,
        gear_data: dict[str, Any],
        athlete_id: str | None = None,
    ) -> Gear:
        """Update an existing gear item.

        Args:
            gear_id: Gear ID
            gear_data: Updated gear data dictionary
            athlete_id: Athlete ID (uses config default if not provided)

        Returns:
            Updated Gear object
        """
        athlete_id = athlete_id or self.config.intervals_icu_athlete_id
        response = await self._request(
            "PUT", f"/athlete/{athlete_id}/gear/{gear_id}", json=gear_data
        )
        return Gear(**response.json())

    async def delete_gear(
        self,
        gear_id: str,
        athlete_id: str | None = None,
    ) -> bool:
        """Delete a gear item.

        Args:
            gear_id: Gear ID
            athlete_id: Athlete ID (uses config default if not provided)

        Returns:
            True if deletion was successful
        """
        athlete_id = athlete_id or self.config.intervals_icu_athlete_id
        await self._request("DELETE", f"/athlete/{athlete_id}/gear/{gear_id}")
        return True

    async def create_gear_reminder(
        self,
        gear_id: str,
        reminder_data: dict[str, Any],
        athlete_id: str | None = None,
    ) -> GearReminder:
        """Create a new reminder for a gear item.

        Args:
            gear_id: Gear ID
            reminder_data: Reminder data dictionary
            athlete_id: Athlete ID (uses config default if not provided)

        Returns:
            Created GearReminder object
        """
        athlete_id = athlete_id or self.config.intervals_icu_athlete_id
        response = await self._request(
            "POST", f"/athlete/{athlete_id}/gear/{gear_id}/reminders", json=reminder_data
        )
        return GearReminder(**response.json())

    async def update_gear_reminder(
        self,
        gear_id: str,
        reminder_id: int,
        reminder_data: dict[str, Any],
        athlete_id: str | None = None,
    ) -> GearReminder:
        """Update an existing gear reminder.

        Args:
            gear_id: Gear ID
            reminder_id: Reminder ID
            reminder_data: Updated reminder data dictionary
            athlete_id: Athlete ID (uses config default if not provided)

        Returns:
            Updated GearReminder object
        """
        athlete_id = athlete_id or self.config.intervals_icu_athlete_id
        response = await self._request(
            "PUT",
            f"/athlete/{athlete_id}/gear/{gear_id}/reminders/{reminder_id}",
            json=reminder_data,
        )
        return GearReminder(**response.json())

    # ==================== Sport Settings Endpoints ====================

    async def get_sport_settings(
        self,
        athlete_id: str | None = None,
    ) -> list[SportSettings]:
        """Get sport settings for an athlete.

        Args:
            athlete_id: Athlete ID (uses config default if not provided)

        Returns:
            List of SportSettings objects
        """
        athlete_id = athlete_id or self.config.intervals_icu_athlete_id
        response = await self._request("GET", f"/athlete/{athlete_id}/sport-settings")
        adapter = TypeAdapter(list[SportSettings])
        return adapter.validate_python(response.json())

    async def update_sport_settings(
        self,
        sport_id: int,
        settings_data: dict[str, Any],
        athlete_id: str | None = None,
    ) -> SportSettings:
        """Update sport-specific settings (FTP, FTHR, pace threshold, etc.).

        Args:
            sport_id: Sport settings ID
            settings_data: Updated settings data dictionary
            athlete_id: Athlete ID (uses config default if not provided)

        Returns:
            Updated SportSettings object
        """
        athlete_id = athlete_id or self.config.intervals_icu_athlete_id
        response = await self._request(
            "PUT", f"/athlete/{athlete_id}/sport-settings/{sport_id}", json=settings_data
        )
        return SportSettings(**response.json())

    async def apply_sport_settings(
        self,
        sport_id: int,
        oldest: str | None = None,
        athlete_id: str | None = None,
    ) -> dict[str, Any]:
        """Apply sport settings (zones, thresholds) to historical activities.

        Args:
            sport_id: Sport settings ID
            oldest: Oldest date to apply settings to (ISO-8601 format)
            athlete_id: Athlete ID (uses config default if not provided)

        Returns:
            Result of applying settings
        """
        athlete_id = athlete_id or self.config.intervals_icu_athlete_id
        params = {}
        if oldest:
            params["oldest"] = oldest

        response = await self._request(
            "POST", f"/athlete/{athlete_id}/sport-settings/{sport_id}/apply", params=params
        )
        return response.json()

    async def create_sport_settings(
        self,
        settings_data: dict[str, Any],
        athlete_id: str | None = None,
    ) -> SportSettings:
        """Create new sport settings.

        Args:
            settings_data: Sport settings data dictionary
            athlete_id: Athlete ID (uses config default if not provided)

        Returns:
            Created SportSettings object
        """
        athlete_id = athlete_id or self.config.intervals_icu_athlete_id
        response = await self._request(
            "POST", f"/athlete/{athlete_id}/sport-settings", json=settings_data
        )
        return SportSettings(**response.json())

    async def delete_sport_settings(
        self,
        sport_id: int,
        athlete_id: str | None = None,
    ) -> bool:
        """Delete sport settings.

        Args:
            sport_id: Sport settings ID
            athlete_id: Athlete ID (uses config default if not provided)

        Returns:
            True if deletion was successful
        """
        athlete_id = athlete_id or self.config.intervals_icu_athlete_id
        await self._request("DELETE", f"/athlete/{athlete_id}/sport-settings/{sport_id}")
        return True

    # ==================== Bulk Event Operations ====================

    async def bulk_create_events(
        self,
        events_data: list[dict[str, Any]],
        athlete_id: str | None = None,
    ) -> list[Event]:
        """Create multiple calendar events in a single request.

        Args:
            events_data: List of event data dictionaries
            athlete_id: Athlete ID (uses config default if not provided)

        Returns:
            List of created Event objects
        """
        athlete_id = athlete_id or self.config.intervals_icu_athlete_id
        response = await self._request(
            "POST", f"/athlete/{athlete_id}/events/bulk", json=events_data
        )
        adapter = TypeAdapter(list[Event])
        return adapter.validate_python(response.json())

    async def bulk_delete_events(
        self,
        event_ids: list[int],
        athlete_id: str | None = None,
    ) -> dict[str, Any]:
        """Delete multiple calendar events in a single request.

        Args:
            event_ids: List of event IDs to delete
            athlete_id: Athlete ID (uses config default if not provided)

        Returns:
            Result of bulk deletion
        """
        athlete_id = athlete_id or self.config.intervals_icu_athlete_id
        response = await self._request(
            "DELETE", f"/athlete/{athlete_id}/events/bulk", json={"ids": event_ids}
        )
        return response.json()

    async def duplicate_event(
        self,
        event_id: int,
        new_date: str,
        athlete_id: str | None = None,
    ) -> Event:
        """Duplicate an existing event to a new date.

        Args:
            event_id: Event ID to duplicate
            new_date: New date for the duplicated event (ISO-8601 format)
            athlete_id: Athlete ID (uses config default if not provided)

        Returns:
            Created Event object
        """
        athlete_id = athlete_id or self.config.intervals_icu_athlete_id
        response = await self._request(
            "POST",
            f"/athlete/{athlete_id}/events/{event_id}/duplicate",
            json={"start_date_local": new_date},
        )
        return Event(**response.json())

    # ==================== Workout CRUD Endpoints ====================

    async def get_workouts(
        self,
        athlete_id: str | None = None,
    ) -> list[Workout]:
        """List all workouts in the athlete's library.

        Args:
            athlete_id: Athlete ID (uses config default if not provided)

        Returns:
            List of Workout objects
        """
        athlete_id = athlete_id or self.config.intervals_icu_athlete_id
        response = await self._request("GET", f"/athlete/{athlete_id}/workouts")
        adapter = TypeAdapter(list[Workout])
        return adapter.validate_python(response.json())

    async def get_workout(
        self,
        workout_id: int,
        athlete_id: str | None = None,
    ) -> Workout:
        """Get a single workout by ID.

        Args:
            workout_id: Workout ID
            athlete_id: Athlete ID (uses config default if not provided)

        Returns:
            Workout object
        """
        athlete_id = athlete_id or self.config.intervals_icu_athlete_id
        response = await self._request("GET", f"/athlete/{athlete_id}/workouts/{workout_id}")
        return Workout(**response.json())

    async def create_workout(
        self,
        workout_data: dict[str, Any],
        athlete_id: str | None = None,
    ) -> Workout:
        """Create a new workout in a folder.

        Args:
            workout_data: Workout data dictionary (must include folder_id)
            athlete_id: Athlete ID (uses config default if not provided)

        Returns:
            Created Workout object
        """
        athlete_id = athlete_id or self.config.intervals_icu_athlete_id
        response = await self._request("POST", f"/athlete/{athlete_id}/workouts", json=workout_data)
        return Workout(**response.json())

    async def update_workout(
        self,
        workout_id: int,
        workout_data: dict[str, Any],
        athlete_id: str | None = None,
    ) -> Workout:
        """Update an existing workout.

        Args:
            workout_id: Workout ID
            workout_data: Updated workout data dictionary
            athlete_id: Athlete ID (uses config default if not provided)

        Returns:
            Updated Workout object
        """
        athlete_id = athlete_id or self.config.intervals_icu_athlete_id
        response = await self._request(
            "PUT", f"/athlete/{athlete_id}/workouts/{workout_id}", json=workout_data
        )
        return Workout(**response.json())

    async def delete_workout(
        self,
        workout_id: int,
        delete_related: bool = False,
        athlete_id: str | None = None,
    ) -> bool:
        """Delete a workout.

        Args:
            workout_id: Workout ID
            delete_related: Also delete workouts added at the same time on a plan
            athlete_id: Athlete ID (uses config default if not provided)

        Returns:
            True if deletion was successful
        """
        athlete_id = athlete_id or self.config.intervals_icu_athlete_id
        params: dict[str, Any] = {}
        if delete_related:
            params["others"] = "true"
        await self._request("DELETE", f"/athlete/{athlete_id}/workouts/{workout_id}", params=params)
        return True

    async def bulk_create_workouts(
        self,
        workouts_data: list[dict[str, Any]],
        athlete_id: str | None = None,
    ) -> list[Workout]:
        """Create multiple workouts in a single request.

        Args:
            workouts_data: List of workout data dictionaries
            athlete_id: Athlete ID (uses config default if not provided)

        Returns:
            List of created Workout objects
        """
        athlete_id = athlete_id or self.config.intervals_icu_athlete_id
        response = await self._request(
            "POST", f"/athlete/{athlete_id}/workouts/bulk", json=workouts_data
        )
        adapter = TypeAdapter(list[Workout])
        return adapter.validate_python(response.json())

    async def get_workout_tags(
        self,
        athlete_id: str | None = None,
    ) -> list[str]:
        """List all workout tags for an athlete.

        Args:
            athlete_id: Athlete ID (uses config default if not provided)

        Returns:
            List of tag strings
        """
        athlete_id = athlete_id or self.config.intervals_icu_athlete_id
        response = await self._request("GET", f"/athlete/{athlete_id}/workout-tags")
        return response.json()

    async def duplicate_workouts(
        self,
        workout_ids: list[int],
        num_copies: int = 1,
        weeks_between: int = 1,
        athlete_id: str | None = None,
    ) -> list[Workout]:
        """Duplicate workouts on a plan.

        Args:
            workout_ids: List of workout IDs to duplicate
            num_copies: Number of copies to create
            weeks_between: Weeks between each copy
            athlete_id: Athlete ID (uses config default if not provided)

        Returns:
            List of created Workout objects
        """
        athlete_id = athlete_id or self.config.intervals_icu_athlete_id
        payload = {
            "workoutIds": workout_ids,
            "numCopies": num_copies,
            "weeksBetween": weeks_between,
        }
        response = await self._request(
            "POST", f"/athlete/{athlete_id}/duplicate-workouts", json=payload
        )
        adapter = TypeAdapter(list[Workout])
        return adapter.validate_python(response.json())

    # ==================== Folder CRUD Endpoints ====================

    async def create_folder(
        self,
        folder_data: dict[str, Any],
        athlete_id: str | None = None,
    ) -> Folder:
        """Create a new workout folder or training plan.

        Args:
            folder_data: Folder data dictionary (must include name)
            athlete_id: Athlete ID (uses config default if not provided)

        Returns:
            Created Folder object
        """
        athlete_id = athlete_id or self.config.intervals_icu_athlete_id
        response = await self._request("POST", f"/athlete/{athlete_id}/folders", json=folder_data)
        return Folder(**response.json())

    async def update_folder(
        self,
        folder_id: int,
        folder_data: dict[str, Any],
        athlete_id: str | None = None,
    ) -> Folder:
        """Update an existing folder or training plan.

        Args:
            folder_id: Folder ID
            folder_data: Updated folder data dictionary
            athlete_id: Athlete ID (uses config default if not provided)

        Returns:
            Updated Folder object
        """
        athlete_id = athlete_id or self.config.intervals_icu_athlete_id
        response = await self._request(
            "PUT", f"/athlete/{athlete_id}/folders/{folder_id}", json=folder_data
        )
        return Folder(**response.json())

    async def delete_folder(
        self,
        folder_id: int,
        athlete_id: str | None = None,
    ) -> bool:
        """Delete a folder and all its workouts.

        Args:
            folder_id: Folder ID
            athlete_id: Athlete ID (uses config default if not provided)

        Returns:
            True if deletion was successful
        """
        athlete_id = athlete_id or self.config.intervals_icu_athlete_id
        await self._request("DELETE", f"/athlete/{athlete_id}/folders/{folder_id}")
        return True

    async def update_plan_workouts(
        self,
        folder_id: int,
        workout_data: dict[str, Any],
        oldest: str | None = None,
        newest: str | None = None,
        athlete_id: str | None = None,
    ) -> list[Workout]:
        """Batch update workouts on a plan.

        Args:
            folder_id: Folder/plan ID
            workout_data: Fields to update on matching workouts
            oldest: Oldest date in range (ISO-8601)
            newest: Newest date in range (ISO-8601)
            athlete_id: Athlete ID (uses config default if not provided)

        Returns:
            List of updated Workout objects
        """
        athlete_id = athlete_id or self.config.intervals_icu_athlete_id
        params: dict[str, Any] = {}
        if oldest:
            params["oldest"] = oldest
        if newest:
            params["newest"] = newest
        response = await self._request(
            "PUT",
            f"/athlete/{athlete_id}/folders/{folder_id}/workouts",
            json=workout_data,
            params=params,
        )
        adapter = TypeAdapter(list[Workout])
        return adapter.validate_python(response.json())

    async def get_folder_shared_with(
        self,
        folder_id: int,
        athlete_id: str | None = None,
    ) -> list[SharedWith]:
        """List athletes a folder is shared with.

        Args:
            folder_id: Folder ID
            athlete_id: Athlete ID (uses config default if not provided)

        Returns:
            List of SharedWith objects
        """
        athlete_id = athlete_id or self.config.intervals_icu_athlete_id
        response = await self._request(
            "GET", f"/athlete/{athlete_id}/folders/{folder_id}/shared-with"
        )
        adapter = TypeAdapter(list[SharedWith])
        return adapter.validate_python(response.json())

    async def update_folder_shared_with(
        self,
        folder_id: int,
        shared_with: list[dict[str, Any]],
        athlete_id: str | None = None,
    ) -> list[SharedWith]:
        """Add or remove athletes from a folder's share list.

        Args:
            folder_id: Folder ID
            shared_with: List of dicts with athlete id and canEdit flag
            athlete_id: Athlete ID (uses config default if not provided)

        Returns:
            Updated list of SharedWith objects
        """
        athlete_id = athlete_id or self.config.intervals_icu_athlete_id
        response = await self._request(
            "PUT",
            f"/athlete/{athlete_id}/folders/{folder_id}/shared-with",
            json=shared_with,
        )
        adapter = TypeAdapter(list[SharedWith])
        return adapter.validate_python(response.json())

    # ==================== Training Plan Endpoints ====================

    async def get_training_plan(
        self,
        athlete_id: str | None = None,
    ) -> AthleteTrainingPlan:
        """Get the athlete's current training plan.

        Args:
            athlete_id: Athlete ID (uses config default if not provided)

        Returns:
            AthleteTrainingPlan object
        """
        athlete_id = athlete_id or self.config.intervals_icu_athlete_id
        response = await self._request("GET", f"/athlete/{athlete_id}/training-plan")
        return AthleteTrainingPlan(**response.json())

    async def set_training_plan(
        self,
        plan_data: dict[str, Any],
        athlete_id: str | None = None,
    ) -> AthleteTrainingPlan:
        """Set or change the athlete's training plan.

        Args:
            plan_data: Plan data (training_plan_id, training_plan_start_date, optional alias)
            athlete_id: Athlete ID (uses config default if not provided)

        Returns:
            Updated AthleteTrainingPlan object
        """
        athlete_id = athlete_id or self.config.intervals_icu_athlete_id
        response = await self._request(
            "PUT", f"/athlete/{athlete_id}/training-plan", json=plan_data
        )
        return AthleteTrainingPlan(**response.json())

    async def apply_plan_changes(
        self,
        athlete_id: str | None = None,
    ) -> dict[str, Any]:
        """Apply pending training plan changes to the calendar.

        Args:
            athlete_id: Athlete ID (uses config default if not provided)

        Returns:
            Result of applying plan changes
        """
        athlete_id = athlete_id or self.config.intervals_icu_athlete_id
        response = await self._request("PUT", f"/athlete/{athlete_id}/apply-plan-changes")
        return response.json()

    # ==================== Workout File Import/Export Endpoints ====================

    async def import_workout(
        self,
        folder_id: int,
        file_content: bytes,
        filename: str,
        activity_type: str | None = None,
        athlete_id: str | None = None,
    ) -> Workout:
        """Import a workout file (.zwo, .mrc, .erg, or .fit) into a folder.

        Args:
            folder_id: Folder ID to import into
            file_content: Raw file bytes
            filename: Original filename with extension
            activity_type: Activity type (e.g., Ride, Run)
            athlete_id: Athlete ID (uses config default if not provided)

        Returns:
            Imported Workout object
        """
        athlete_id = athlete_id or self.config.intervals_icu_athlete_id
        params: dict[str, Any] = {}
        if activity_type:
            params["type"] = activity_type
        files = {"file": (filename, file_content)}
        response = await self._request(
            "POST",
            f"/athlete/{athlete_id}/folders/{folder_id}/import-workout",
            files=files,
            params=params,
        )
        return Workout(**response.json())

    async def download_workout(
        self,
        workout_data: dict[str, Any],
        ext: str,
        athlete_id: str | None = None,
    ) -> bytes:
        """Convert a workout to a file format (.zwo, .mrc, .erg, or .fit).

        Args:
            workout_data: Workout data to convert
            ext: File extension (zwo, mrc, erg, or fit)
            athlete_id: Athlete ID (uses config default if not provided)

        Returns:
            File content as bytes
        """
        athlete_id = athlete_id or self.config.intervals_icu_athlete_id
        ext_with_dot = f".{ext.lstrip('.')}"
        response = await self._request(
            "POST",
            f"/athlete/{athlete_id}/download-workout{ext_with_dot}",
            json=workout_data,
        )
        return response.content

    async def download_workouts_zip(
        self,
        athlete_id: str | None = None,
    ) -> bytes:
        """Download all workouts as a ZIP archive.

        Args:
            athlete_id: Athlete ID (uses config default if not provided)

        Returns:
            ZIP file content as bytes
        """
        athlete_id = athlete_id or self.config.intervals_icu_athlete_id
        response = await self._request("GET", f"/athlete/{athlete_id}/workouts.zip")
        return response.content
