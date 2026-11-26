# Contributing

Thanks for contributing! This project is designed for AI coding agents as well as humans.

- Read [AGENTS.md](AGENTS.md) first — it is the rulebook and task workflow.
- Follow the playbooks in `docs/playbooks/` for ADD / UPDATE / REMOVE and for jobs, caching, audit,
  transactions, and endpoint protection.
- Before opening a PR, run `make lint && make test && make feature-check` and ensure
  `make typecheck` passes and coverage stays ≥ 80%.
- Keep changes documented in the same PR (README, registry, CHANGELOG, ADR when required).

## Reporting bugs / vulnerabilities
See [SECURITY.md](SECURITY.md) for private vulnerability reporting.