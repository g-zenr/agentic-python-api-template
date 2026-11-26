## Definition of Done
- [ ] Playbook steps completed in order
- [ ] Feature README updated (Status, Endpoints, Business rules, Data model, Change history row)
- [ ] `docs/features.md` row added / updated / moved to Removed
- [ ] `docs/CHANGELOG.md` entry (Added / Changed / Fixed / Removed; `BREAKING:` when applicable)
- [ ] Version bumped in `pyproject.toml` (and ONLY there)
- [ ] ADR written when the playbook says REQUIRED
- [ ] `Msg` keys present in every locale; orphaned keys/constants removed
- [ ] Every mutation is audited (`audit.record`) and wrapped in `transaction()`
- [ ] No slow work inside requests (jobs + 202 polling)
- [ ] Cached reads have invalidation on every write path, listed in the README
- [ ] `make typecheck` passes; coverage gate (80%) holds
- [ ] New routes are permissioned and rate-limited where sensitive
- [ ] `make lint && make test && make feature-check` all pass

## Notes
- See [AGENTS.md](../AGENTS.md) for the full rulebook and playbooks under `docs/playbooks/`.