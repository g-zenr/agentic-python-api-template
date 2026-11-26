# 0002 — Centralized constants and i18n

- **Status:** Accepted
- **Date:** 2026-11-26

## Context
Scattered literals and inline user-facing strings make an API inconsistent and impossible to
localize or audit. Agents need one obvious place for each kind of value.

## Decision
Route every value to exactly one home: environment → `core/config.py` (+ `.env.example`);
static literals/enums → `core/constants.py`; user-facing text → `Msg` in `core/messages.py` +
every `core/locales/*.json`; reusable logic → `app/shared/`. The request locale comes from
`Accept-Language` via a ContextVar. Tests enforce locale parity and flag orphaned keys.

## Consequences
- No magic strings or numbers in feature code.
- Adding a language is a mechanical, test-guarded step.
- `check_feature.py` reports orphaned messages/constants so cleanup is enforced.