"""Static, non-localized constants and enums: the single source for literals.

If a literal is shown to end users, it belongs in `messages.py` + locale JSON instead.
"""

from enum import StrEnum


class Defaults:
    JWT_SECRET: str = "dev-secret"


class Header:
    LOCALE: str = "accept-language"
    REQUEST_ID: str = "x-request-id"
    CACHE_CONTROL: str = "cache-control"
    ETAG: str = "etag"
    IF_NONE_MATCH: str = "if-none-match"
    IF_MATCH: str = "if-match"
    RETRY_AFTER: str = "retry-after"
    LOCATION: str = "location"
    USER_AGENT: str = "user-agent"
    FORWARDED_FOR: str = "x-forwarded-for"
    IDEMPOTENCY_KEY: str = "idempotency-key"
    IDEMPOTENCY_REPLAY: str = "idempotent-replay"
    STS: str = "strict-transport-security"
    CONTENT_TYPE_OPTIONS: str = "x-content-type-options"
    FRAME_OPTIONS: str = "x-frame-options"
    REFERRER_POLICY: str = "referrer-policy"
    CSP: str = "content-security-policy"


class Pagination:
    DEFAULT_PAGE: int = 1
    DEFAULT_SIZE: int = 20
    MAX_SIZE: int = 100


class CacheControl:
    NO_STORE: str = "no-store"
    REVALIDATE: str = "private, no-cache"


class Role(StrEnum):
    USER = "USER"
    ADMIN = "ADMIN"


class Permission(StrEnum):
    USERS_READ = "users:read"
    AUDIT_READ = "audit:read"
    ACTIVITY_READ = "activity:read"
    JOBS_READ_ALL = "jobs:read_all"
    JOBS_MANAGE_ALL = "jobs:manage_all"
    PERMISSIONS_MANAGE = "permissions:manage"


class TokenPurpose(StrEnum):
    VERIFY_EMAIL = "verify_email"
    RESET_PASSWORD = "reset_password"


class ErrorCode(StrEnum):
    INTERNAL = "INTERNAL_ERROR"
    VALIDATION = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    CONFLICT = "CONFLICT"
    RATE_LIMITED = "RATE_LIMITED"
    PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    PRECONDITION_FAILED = "PRECONDITION_FAILED"
    PRECONDITION_REQUIRED = "PRECONDITION_REQUIRED"


class Limits:
    PASSWORD_MIN: int = 8
    PASSWORD_MAX: int = 128
    NAME_MAX: int = 100
    TITLE_MAX: int = 120
    BODY_MAX: int = 20_000
    IDEMPOTENCY_KEY_MAX: int = 100
    USER_AGENT_MAX: int = 300
    SORT_MAX_FIELDS: int = 3
    SEARCH_MAX: int = 100


class Tag:
    HEALTH = "Health"
    AUTH = "Auth"
    USERS = "Users"
    NOTES = "Notes"
    JOBS = "Jobs"
    AUDIT = "Audit"
    PERMISSIONS = "Permissions"


class CacheNS(StrEnum):
    USER = "user"
    NOTES = "notes"
    RATE = "rate"
    PERMISSIONS = "permissions"


class CacheTTL:
    SHORT: int = 60
    MEDIUM: int = 300
    LONG: int = 3600
    NEGATIVE: int = 15
    JITTER: float = 0.1


class CachePolicy:
    SOCKET_TIMEOUT: float = 1.0


class ActorType(StrEnum):
    USER = "user"
    SYSTEM = "system"
    ANONYMOUS = "anonymous"


class AuditOutcome(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    DENIED = "denied"


class AuditResource(StrEnum):
    USER = "user"
    NOTE = "note"
    JOB = "job"
    ENDPOINT = "endpoint"
    LOG = "log"
    TOKEN = "token"
    PERMISSION = "permission"


class AuditReason(StrEnum):
    UNKNOWN_EMAIL = "unknown_email"
    BAD_PASSWORD = "bad_password"
    INSUFFICIENT_PERMISSION = "insufficient_permission"
    PERMISSION_DENIED = "permission_denied"
    POLICY_ERROR = "policy_error"


class AuditAction(StrEnum):
    AUTH_REGISTER = "auth.register"
    AUTH_LOGIN = "auth.login"
    AUTH_LOGIN_FAILED = "auth.login_failed"
    AUTH_REFRESH = "auth.refresh"
    AUTH_REFRESH_REUSE_DETECTED = "auth.refresh_reuse_detected"
    AUTH_LOGOUT = "auth.logout"
    AUTH_LOGOUT_ALL = "auth.logout_all"
    AUTH_PASSWORD_CHANGE = "auth.password_change"
    AUTH_EMAIL_VERIFY = "auth.email_verify"
    AUTH_PASSWORD_RESET_REQUEST = "auth.password_reset_request"
    AUTH_PASSWORD_RESET = "auth.password_reset"
    USER_UPDATE = "user.update"
    USER_DELETE = "user.delete"
    USER_EXPORT_REQUEST = "user.export_request"
    NOTE_CREATE = "note.create"
    NOTE_UPDATE = "note.update"
    NOTE_DELETE = "note.delete"
    NOTE_EXPORT_REQUEST = "note.export_request"
    JOB_CANCEL = "job.cancel"
    ACCESS_DENIED = "access.denied"
    RETENTION_PURGE = "retention.purge"
    ACCOUNT_ERASE = "account.erase"
    ADMIN_BOOTSTRAP = "admin.bootstrap"
    PERMISSION_GRANTS_UPDATED = "permission.grants_updated"


class JobStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


TERMINAL_JOB_STATUSES = frozenset({JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED})


class JobType(StrEnum):
    NOTES_EXPORT = "notes.export"
    PURGE_LOGS = "maintenance.purge_logs"
    PURGE_JOBS = "maintenance.purge_jobs"
    PURGE_EXPIRED = "maintenance.purge_expired"
    AUTH_SEND_TOKEN_EMAIL = "auth.send_token_email"
    ACCOUNT_EXPORT = "account.export"
    ACCOUNT_ERASE = "account.erase"
    ACCOUNT_ERASE_RECOVERY = "account.erase_recovery"


class JobPolicy:
    DEFAULT_TIMEOUT: int = 300
    DEFAULT_MAX_ATTEMPTS: int = 3
    BACKOFF_BASE: int = 5
    BACKOFF_MAX: int = 600
    RESULT_MAX_BYTES: int = 512_000
    HEARTBEAT_SECONDS: int = 20
    SHUTDOWN_GRACE: int = 30
    SCHEDULE_CHECK_SECONDS: int = 30
    SYSTEM_SCOPE: str = "system"


class Schedule:
    HOURLY: int = 3600
    DAILY: int = 86400


class Activity:
    SKIP_PATHS: tuple[str, ...] = (
        "/docs",
        "/openapi.json",
        "/mcp",
        "/metrics",
    )  # plus f"{api_prefix}/health"
    UNMATCHED: str = "<unmatched>"


class Redaction:
    FIELDS: frozenset[str] = frozenset(
        {
            "password", "password_hash", "token", "access_token", "secret",
            "refresh_token", "token_hash", "authorization", "api_key", "cookie",
            "reset_token", "verification_token", "client_secret",
        }
    )
    IGNORED: frozenset[str] = frozenset({"updated_at"})
    MASK: str = "***"


class RateBucket(StrEnum):
    GLOBAL_IP = "global_ip"
    LOGIN_IP = "login_ip"
    LOGIN_ACCOUNT = "login_account"
    REGISTER_IP = "register_ip"
    REFRESH_IP = "refresh_ip"
    FORGOT_IP = "forgot_ip"
    FORGOT_ACCOUNT = "forgot_account"
    RESEND_USER = "resend_user"
    PERMISSIONS_IP = "permissions_ip"


# (limit, window seconds); GLOBAL_IP limit comes from settings.
RATE_POLICY: dict[RateBucket, tuple[int, int]] = {
    RateBucket.LOGIN_IP: (10, 60),
    RateBucket.LOGIN_ACCOUNT: (5, 900),
    RateBucket.REGISTER_IP: (5, 3600),
    RateBucket.REFRESH_IP: (30, 60),
    RateBucket.FORGOT_IP: (5, 3600),
    RateBucket.FORGOT_ACCOUNT: (3, 3600),
    RateBucket.RESEND_USER: (3, 3600),
    RateBucket.PERMISSIONS_IP: (20, 60),
}


class GrantEffect(StrEnum):
    ALLOW = "ALLOW"
    DENY = "DENY"


class GrantCondition:
    """Typed vocabulary for `permission_grants.conditions`; new keys need an ADR."""

    OWN_ONLY: str = "own_only"
