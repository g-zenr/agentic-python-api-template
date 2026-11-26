# Feature registry

> Single index of every feature. Updated by every add / update / remove. Enforced by tests.

## Active features
| Feature | Status | Prefix | Prisma model(s) | MCP tools | Since | Last changed | README |
|---|---|---|---|---|---|---|---|
| health | stable | /health | none | get_current_time | 0.1.0 | 0.3.0 | [link](../app/features/health/README.md) |
| auth | stable | /auth | none (uses User) | none | 0.1.0 | 0.3.0 | [link](../app/features/auth/README.md) |
| users | stable | /users | User | none | 0.1.0 | 0.3.0 | [link](../app/features/users/README.md) |
| notes | stable | /notes | Note | none | 0.1.0 | 0.3.0 | [link](../app/features/notes/README.md) |
| jobs | stable | /jobs | Job | none | 0.2.0 | 0.2.0 | [link](../app/features/jobs/README.md) |
| audit | stable | /audit | AuditLog, ActivityLog | none | 0.2.0 | 0.2.0 | [link](../app/features/audit/README.md) |
| maintenance | stable | none | none (purges Job, AuditLog, ActivityLog) | none | 0.2.0 | 0.2.0 | [link](../app/features/maintenance/README.md) |

Status values: `experimental` | `stable` | `deprecated`.

## Removed features
| Feature | Removed in | Date | Reason | Data dropped? | Reference |
|---|---|---|---|---|---|