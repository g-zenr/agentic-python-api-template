# 06 — Localization

> How the request locale is resolved, how catalogs work, and how parity is enforced.

## What you will learn
- How the locale is chosen per request.
- The catalog format and placeholder rules.
- How tests enforce key/placeholder parity.
- How to add a new language.

## Locale resolution
`app/core/middleware.py` reads the `Accept-Language` header and calls
`app.core.i18n.resolve_locale`, which returns the first supported language tag (ignoring region
and quality values). The result is stored in a `ContextVar` (`locale_var`) so any code can call
`t(...)` without threading the locale through every function.

```python
resolve_locale("fil-PH,en;q=0.8")  # -> "fil"
resolve_locale("de-DE")  # -> "en" (default fallback)
```

## Catalog format
Each file in `app/core/locales/` is a flat JSON object mapping a `Msg` value (dotted key) to
text. Placeholders use `str.format` syntax and MUST be identical across locales.

```json
{ "note.created": "Note created" }
```

## The `Msg` enum
Every user-facing key is a member of `Msg` in `app/core/messages.py`. Its value is the dotted key.
Adding a message means: add the member **and** the key in **every** locale file.

## Placeholder rules
- Placeholders are `{name}` and are filled via `t(key, **params)`.
- The set of placeholders must match across all locales for the same key (a test enforces this).
- Never build sentences by concatenating translated fragments.

## How parity is enforced
`tests/test_i18n.py` asserts that every `Msg` value exists in every locale, that all locales share
an identical key set, and that placeholders match. `scripts/check_feature.py` reports orphaned
`Msg` members and locale/`Msg` mismatches.

## Adding a language
1. Add the code to `Settings.supported_locales` and `.env.example` (`SUPPORTED_LOCALES`).
2. Create `app/core/locales/<code>.json` with the **same keys** as `en.json`.
3. Translate the values, preserving every `{placeholder}`.
4. Run `make test` (i18n parity) and `make feature-check`.

## Common mistakes
- Adding a `Msg` member but forgetting a locale file.
- Translating a placeholder name (e.g. `{name}` → `{nombre}`).
- Concatenating fragments instead of using placeholders.

## See also
- [05 — Configuration and constants](05-configuration-and-constants.md)
- [Playbook: add a message and locale](playbooks/add-message-and-locale.md)