"""MCP tools for the health feature."""

from app.core.mcp import mcp_tool
from app.shared.utils.time import to_zone, utcnow


@mcp_tool
async def get_current_time(timezone: str = "UTC") -> str:
    """Get the current date and time in an IANA timezone, e.g. Asia/Manila."""
    return to_zone(utcnow(), timezone).isoformat()
