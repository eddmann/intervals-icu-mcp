"""Intervals.icu MCP Server - Entry point."""

from .mcp import mcp


def main():
    """Main entry point for the Intervals.icu MCP server."""
    # Run the server with stdio transport (default)
    mcp.run()


if __name__ == "__main__":
    main()
