# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an MCP (Model Context Protocol) server for Intervals.icu that provides 67 tools, 1 resource, and 6 prompts for accessing training data, wellness metrics, and performance analysis through Claude and other LLMs.

## Development Commands

### Setup & Dependencies

```bash
# Install dependencies
make install

# Update dependencies
make update

# Setup authentication
make auth
```

### Testing & Linting

```bash
# Run all pre-release checks (same as CI)
make can-release

# Run tests
make test

# Run specific test filter
make test/athlete         # runs tests matching "athlete"

# Run tests with verbose output
make test/verbose

# Lint with ruff and pyright
make lint

# Format code
make format
```

### Running Locally

```bash
# Run the MCP server
make run
```

### Docker

```bash
# Build Docker image
make docker/build

# Run Docker container
make docker/run
```

## Architecture

### Core Components

**FastMCP Server** (`server.py`)

- Entry point that initializes the FastMCP server
- Registers all tools, resources, and prompts
- Tools are imported from `tools/` modules but registered in server.py
- Middleware is added before tools are registered

**Middleware** (`middleware.py`)

- `ConfigMiddleware` runs before every tool call
- Loads and validates Intervals.icu configuration from environment
- Injects `ICUConfig` into context state via `ctx.set_state("config", config)`
- Tools access config via `ctx.get_state("config")`

**API Client** (`client.py`)

- `ICUClient` is an async HTTP client using httpx
- Uses Basic Auth with username "API_KEY" and the API key as password
- All API methods are async and must be used with async context manager
- Handles error responses with `ICUAPIError` exceptions
- Default timeout is 30 seconds

**Authentication** (`auth.py`)

- `ICUConfig` loads credentials from `.env` file using pydantic-settings
- `load_config()` loads configuration from environment
- `validate_credentials()` checks if credentials are properly set
- Interactive setup script at `scripts/setup_auth.py`

**Response Builder** (`response_builder.py`)

- All tools return JSON with consistent structure:
  ```json
  {
    "data": {...},           // Main data payload
    "analysis": {...},       // Optional insights and computed metrics
    "metadata": {...}        // Query metadata, timestamps
  }
  ```
- `ResponseBuilder.build_response()` creates success responses
- `ResponseBuilder.build_error_response()` creates error responses
- Automatically converts datetime objects to ISO strings

**Models** (`models.py`)

- Pydantic models for all API responses
- Models include: Activity, Athlete, Wellness, Event, PowerCurve, etc.

### Tool Organization

Tools are organized into 13 modules in `tools/`:

1. **activities.py** - Query and manage activities
2. **activity_analysis.py** - Streams, intervals, best efforts
3. **athlete.py** - Profile and fitness metrics (CTL/ATL/TSB)
4. **wellness.py** - HRV, sleep, recovery metrics
5. **events.py** - Calendar queries
6. **event_management.py** - Create/update/delete events; supports `workout_doc`, tags, indoor, target, all 14 event categories
7. **performance.py** - Power/HR/pace curves
8. **curves.py** - HR and pace curve analysis
9. **workout_library.py** - Full workout CRUD, file import/export (.zwo/.mrc/.erg/.fit), tags, duplication
10. **folder_management.py** - Create/update/delete folders and training plans, folder sharing
11. **training_plan.py** - Assign training plans to athletes, apply plan changes to calendar
12. **gear.py** - Manage gear and reminders
13. **sport_settings.py** - FTP, FTHR, pace thresholds

### Tool Pattern

All tools follow the same async pattern:

```python
async def tool_name(
    param: str,
    ctx: Context | None = None,
) -> str:
    """Tool description."""
    assert ctx is not None
    config: ICUConfig = ctx.get_state("config")

    try:
        async with ICUClient(config) as client:
            # Make API calls
            result = await client.method()

            # Build response
            return ResponseBuilder.build_response(
                data={"key": "value"},
                analysis={"insights": "..."},
                query_type="tool_type"
            )
    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
```

## Important Implementation Details

### Authentication Flow

1. User runs `uv run intervals-icu-mcp-auth` to set up credentials
2. Credentials stored in `.env` file (API key + athlete ID)
3. `ConfigMiddleware` loads and validates on every tool call
4. `ICUClient` uses Basic Auth with username "API_KEY"

### Error Handling

- `ICUAPIError` for API errors (401, 404, 429, etc.)
- Middleware raises `ToolError` if credentials not configured
- All tools return error JSON instead of raising exceptions
- Include helpful error messages and suggestions

### Response Format

- Never return raw API responses
- Always use `ResponseBuilder.build_response()` for consistency
- Include `analysis` section for insights when relevant
- Use `metadata` for query context (date ranges, limits, etc.)

### Date Handling

- API uses ISO-8601 format (YYYY-MM-DD or full datetime)
- `ResponseBuilder.format_date_with_day()` adds day-of-week info
- All datetimes automatically converted to ISO strings in responses

### Testing

- Tests use `pytest` with `pytest-asyncio` for async tests
- `respx` is used to mock HTTP requests
- Test fixtures in `tests/fixtures/`
- Test stubs in `tests/stubs/`

## Type Checking

- Pyright is configured with basic type checking mode
- Strict mode only for `src/` directory
- Allow imports without type stubs
- Run `make lint/pyright` or `uv run pyright`

## Code Style

- Ruff for linting and formatting
- Line length: 100 characters
- Target Python 3.11+
- Ignore E501 (line length enforced by formatter)
- Allow unused imports in `__init__.py` files
- Run `make format` to auto-fix style issues

## Important Files

- `.env` - Local credentials (not in git)
- `.env.example` - Template for credentials
- `openapi-spec.json` - Intervals.icu API specification
- `uv.lock` - Locked dependencies (commit this)
- `.github/workflows/test.yml` - CI tests
- `.github/workflows/release.yml` - Docker release automation
