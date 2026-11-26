# Playbook: Add an MCP tool

> When to use, prerequisites, numbered steps, a verification checklist, and a worked example.

## When to use
Use this to expose a function to AI clients via the optional MCP server. (No MCP: see
[../09-mcp.md](../09-mcp.md) to remove it.)

## Prerequisites
- MCP is enabled (`MCP_ENABLED=true`).
- The owning feature exists.

## Steps
1. **Create/extend `tools.py`** in the feature folder.
2. **Declare the tool.** Write an async function with full type hints and a clear docstring (the
   docstring becomes the tool description), decorated with `@mcp_tool`.
3. **No side effects on import.** Keep tools pure; they are imported at startup.
4. **Docs.** Add the tool to the feature README (Endpoints/tools table) and a Change history row;
   add a CHANGELOG entry; bump the version.
5. **Verify.** Run `make test` (`test_mcp.py` checks registration) and
   `make lint && make feature-check`.

## Verification checklist
- [ ] `tools.py` exists in the feature.
- [ ] Function is `async`, fully typed, has a docstring, decorated `@mcp_tool`.
- [ ] README + CHANGELOG + version updated.
- [ ] `make test` and `make feature-check` pass.

## Worked example
`health/tools.py` declares `get_current_time(timezone: str = "UTC")` with `@mcp_tool`; it is
auto-registered at startup and appears in `registered_tools()`.