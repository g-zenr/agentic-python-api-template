# Security Policy

## Reporting a vulnerability
Please report suspected vulnerabilities **privately** via GitHub Security Advisories
("Report a vulnerability" on the repository's Security tab). Do not open public issues.

We aim to acknowledge within 3 business days and to ship a fix or mitigation within 10 business days
for critical issues.

## Supported versions
| Version | Supported |
|---|---|
| 0.3.x | yes |
| 0.2.x | security fixes only |
| < 0.2 | no |

## Hardening
See [docs/16-security.md](docs/16-security.md). Production requires a strong `JWT_SECRET`, non-`*`
CORS/hosts, redis cache, JSON logs, SMTP email, https `APP_BASE_URL`, and a `METRICS_TOKEN`.