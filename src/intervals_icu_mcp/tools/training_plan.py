"""Training plan management tools for Intervals.icu MCP server."""

from datetime import datetime
from typing import Annotated, Any

from fastmcp import Context

from ..auth import ICUConfig
from ..client import ICUAPIError, ICUClient
from ..models import AthleteTrainingPlan
from ..response_builder import ResponseBuilder


def _plan_to_dict(plan: AthleteTrainingPlan) -> dict[str, Any]:
    """Build a response dict from an AthleteTrainingPlan model."""
    result: dict[str, Any] = {}
    if plan.id:
        result["athlete_id"] = plan.id
    if plan.training_plan_id is not None:
        result["training_plan_id"] = plan.training_plan_id
    if plan.training_plan_alias:
        result["alias"] = plan.training_plan_alias
    if plan.training_plan_start_date:
        result["start_date"] = plan.training_plan_start_date
    if plan.training_plan_last_applied:
        result["last_applied"] = plan.training_plan_last_applied
    if plan.timezone:
        result["timezone"] = plan.timezone
    if plan.training_plan:
        result["plan"] = {
            "id": plan.training_plan.id,
            "name": plan.training_plan.name,
            "description": plan.training_plan.description,
            "duration_weeks": plan.training_plan.duration_weeks,
            "hours_per_week": {
                "min": plan.training_plan.hours_per_week_min,
                "max": plan.training_plan.hours_per_week_max,
            },
            "num_workouts": plan.training_plan.num_workouts,
        }
    return result


async def get_training_plan(
    ctx: Context | None = None,
) -> str:
    """Get the athlete's current training plan assignment.

    Returns the active training plan including plan details, start date,
    and last time plan changes were applied to the calendar.

    Returns:
        JSON string with current training plan details
    """
    assert ctx is not None
    config: ICUConfig = ctx.get_state("config")

    try:
        async with ICUClient(config) as client:
            plan = await client.get_training_plan()

            if not plan.training_plan_id:
                return ResponseBuilder.build_response(
                    data={"training_plan": None},
                    metadata={"message": "No training plan currently assigned"},
                )

            return ResponseBuilder.build_response(
                data={"training_plan": _plan_to_dict(plan)},
                query_type="get_training_plan",
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )


async def set_training_plan(
    training_plan_id: Annotated[
        int, "Folder ID of the training plan to assign (use get_workout_library to find IDs)"
    ],
    start_date: Annotated[str, "Plan start date in YYYY-MM-DD format"],
    alias: Annotated[str | None, "Optional custom name for this plan instance"] = None,
    ctx: Context | None = None,
) -> str:
    """Set or change the athlete's training plan.

    Assigns a training plan folder to the athlete starting on the given date.
    Use apply_plan_changes after setting to push the plan workouts to the calendar.

    Returns:
        JSON string with updated training plan assignment
    """
    assert ctx is not None
    config: ICUConfig = ctx.get_state("config")

    try:
        datetime.strptime(start_date, "%Y-%m-%d")
    except ValueError:
        return ResponseBuilder.build_error_response(
            "Invalid date format. Please use YYYY-MM-DD format.",
            error_type="validation_error",
        )

    try:
        plan_data: dict[str, Any] = {
            "training_plan_id": training_plan_id,
            "training_plan_start_date": start_date,
        }
        if alias is not None:
            plan_data["training_plan_alias"] = alias

        async with ICUClient(config) as client:
            plan = await client.set_training_plan(plan_data)

            return ResponseBuilder.build_response(
                data={"training_plan": _plan_to_dict(plan)},
                query_type="set_training_plan",
                metadata={
                    "message": f"Successfully assigned training plan {training_plan_id} starting {start_date}. "
                    "Run apply_plan_changes to push workouts to your calendar."
                },
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )


async def apply_plan_changes(
    ctx: Context | None = None,
) -> str:
    """Apply pending training plan changes to the calendar.

    Syncs the current training plan to the athlete's calendar, adding or updating
    planned workouts. Run this after set_training_plan or after modifying plan workouts.

    Returns:
        JSON string with result of applying the plan
    """
    assert ctx is not None
    config: ICUConfig = ctx.get_state("config")

    try:
        async with ICUClient(config) as client:
            result = await client.apply_plan_changes()

            return ResponseBuilder.build_response(
                data=result,
                query_type="apply_plan_changes",
                metadata={"message": "Successfully applied training plan changes to calendar"},
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )
