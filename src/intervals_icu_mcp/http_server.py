"""HTTP/ASGI server for Intervals.icu MCP - Uvicorn deployment."""

from starlette.requests import Request
from starlette.responses import JSONResponse

from .mcp import mcp

# Create ASGI application for HTTP deployment
# This enables running the MCP server with uvicorn over HTTP
app = mcp.http_app()


# Add health check endpoint for monitoring
@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    """Health check endpoint for monitoring and load balancers."""
    return JSONResponse(
        {
            "status": "healthy",
            "service": "intervals-icu-mcp",
            "version": "1.0.0",
        }
    )
