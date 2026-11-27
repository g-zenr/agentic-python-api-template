# Playbook: Add an endpoint

> When to use, prerequisites, numbered steps, a verification checklist, and a worked example.

## When to use
Use this to add a single route to an **existing** feature. (A whole new concept is an ADD — see
`add-feature.md`.)

## Prerequisites
- The target feature exists and you have read its `README.md`.

## Steps
1. **Schema.** If the endpoint has a request/response body, add models to the feature's
   `schemas.py` extending `ApiModel`.
2. **Repository.** If it needs a new query, add a method to the feature's `repository.py`.
3. **Service.** Add a module-level async function to `service.py` with the business rule; raise an
   `AppError` subclass with a `Msg` key on failure.
4. **Router.** Add the route to `router.py` with `response_model=ApiResponse[...]`, `summary`,
   `description`, and the correct `status_code`. Return `ok(...)` or `page_of(...)`. Add auth via
   `CurrentUser`/`VerifiedUser` + `require_permission(...)` if needed.
5. **Docs.** Update the README Endpoints table and add a Change history row; update "Last changed"
   in `docs/features.md`; add a CHANGELOG entry; bump the version (minor for a new endpoint).
6. **Tests + verify.** Add/adjust `tests/features/test_<x>.py`; run
   `make lint && make test && make feature-check`.

## Verification checklist
- [ ] Schema added (if needed).
- [ ] Repository method added (if needed).
- [ ] Service function with typed error.
- [ ] Route with response_model + summary + description + status code.
- [ ] README Endpoints + Change history; registry "Last changed"; CHANGELOG; version bump.
- [ ] Tests updated.
- [ ] `make lint && make test && make feature-check` all pass.

## Worked example
`GET /notes/{note_id}` was added to `notes`: `NoteOut` already existed, `service.get` calls the
`_owned` guard, and the router declares the route with `response_model=ApiResponse[NoteOut]`.