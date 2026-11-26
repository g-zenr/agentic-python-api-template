"""MCP tests: importing the app registers feature tools."""

from app.core.mcp import registered_tools


def test_get_current_time_tool_registered():
    # Importing app.main runs create_app(), which imports every feature's tools module.
    import app.main  # noqa: F401

    assert "get_current_time" in registered_tools()
