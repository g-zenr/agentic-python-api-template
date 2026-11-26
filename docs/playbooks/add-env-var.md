# Playbook: Add an env var

> When to use, prerequisites, numbered steps, a verification checklist, and a worked example.

## When to use
Use this when you need a new **deployment/secret/toggle** value that comes from the environment.

## Prerequisites
- Confirm the value is genuinely environment-driven (not a static constant or user-facing text).

## Steps
1. **Add the field.** Add a typed field to `Settings` in `app/core/config.py` (with a safe default
   where possible; use `SecretStr` for secrets).
2. **Document it.** Add the variable to `.env.example` under the matching group
   (`# Cache`, `# Background jobs`, `# Audit & activity`) with a sensible placeholder.
3. **Use it.** Read it via `from app.core.config import settings` — never `os.environ` elsewhere.
4. **Docs.** Note it in [../05-configuration-and-constants.md](../05-configuration-and-constants.md)
   if notable; add a CHANGELOG entry; bump the version.
5. **Verify.** Run `make lint && make test && make feature-check`.

## Verification checklist
- [ ] Field added to `Settings` (typed; `SecretStr` if secret).
- [ ] `.env.example` updated.
- [ ] Read via `settings`, not `os.environ`.
- [ ] CHANGELOG/version updated.
- [ ] `make lint && make test && make feature-check` all pass.

## Worked example
`mcp_api_key: SecretStr | None = None` in `config.py` is documented as `MCP_API_KEY=` in
`.env.example` and consumed by `ApiKeyGate` in `app/core/mcp.py`.