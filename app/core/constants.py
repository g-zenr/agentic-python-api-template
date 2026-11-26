"""Static, non-localized constants and enums: the single source for literals.

If a literal is shown to end users, it belongs in `messages.py` + locale JSON instead.
"""

from enum import StrEnum


class Defaults:
    JWT_SECRET = "dev-secret"


class Header:
    LOCALE = "accept-language"
    REQUEST_ID = "x-request-id"
    CACHE_CONTROL = "cache-control"
    ETAG = "etag"
    IF_NONE_MATCH = "if-none-match"
    IF_MATCH = "if-match"
    RETRY_AFTER = "retry-after"
    LOCATION = "location"
    USER_AGENT = "user-agent"
    FORWARDED_FOR = "x-forwarded-for"
    IDEMPOTENCY_KEY = "idempotency-key"
    IDEMPOTENCY_REPLAY = "idempotent-replay"
    DEPRECATION = "deprecation"
    SUNSET = "sunset"
    LINK = "link"
    STS = "strict-transport-security"
    CONTENT_TYPE_OPTIONS = "x-content-type-options"
    FRAME_OPTIONS = "x-frame-options"
    REFERRER_POLICY = "referrer-policy"
    CSP = "content-security-policy"


class Pagination:
    DEFAULT_PAGE = 1
    DEFAULT_SIZE = 20
    MAX_SIZE = 100


class CacheControl:
    NO_STORE = "no-store"
    REVALIDATE = "private, no-cache"


class Role(StrEnum):
    USER = "USER"
    ADMIN = "ADMIN"


class Permission(StrEnum):
    USERS_READ = "users:read"
    AUDIT_READ = "audit:read"
    ACTIVITY_READ = "activity:read"
    JOBS_READ_ALL = "jobs:read_all"
    JOBS_MANAGE_ALL = "jobs:manage_all"


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
    PASSWORD_MIN = 8
    PASSWORD_MAX = 128
    NAME_MAX = 100
    TITLE_MAX = 120
    BODY_MAX = 20_000
    IDEMPOTENCY_KEY_MAX = 100
    USER_AGENT_MAX = 300
    SORT_MAX_FIELDS = 3
    SEARCH_MAX = 100


class Tag:
    HEALTH = "Health"
    AUTH = "Auth"
    USERS = "Users"
    NOTES = "Notes"
    JOBS = "Jobs"
    AUDIT = "Audit"


class CacheNS(StrEnum):
    USER = "user"
    NOTES = "notes"
    RATE = "rate"


class CacheTTL:
    SHORT = 60
    MEDIUM = 300
    LONG = 3600
    NEGATIVE = 15
    JITTER = 0.1


class CachePolicy:
    SOCKET_TIMEOUT = 1.0


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


class AuditReason(StrEnum):
    UNKNOWN_EMAIL = "unknown_email"
    BAD_PASSWORD = "bad_password"
    INSUFFICIENT_PERMISSION = "insufficient_permission"


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


class JobPolicy:
    DEFAULT_TIMEOUT = 300
    DEFAULT_MAX_ATTEMPTS = 3
    BACKOFF_BASE = 5
    BACKOFF_MAX = 600
    RESULT_MAX_BYTES = 512_000
    HEARTBEAT_SECONDS = 20
    SHUTDOWN_GRACE = 30
    SCHEDULE_CHECK_SECONDS = 30
    SYSTEM_SCOPE = "system"


class Schedule:
    HOURLY = 3600
    DAILY = 86400


class Activity:
    SKIP_PATHS = ("/docs", "/openapi.json", "/mcp", "/metrics")  # plus f"{api_prefix}/health"
    UNMATCHED = "<unmatched>"


class Redaction:
    FIELDS = frozenset({"password", "password_hash", "token", "access_token", "secret"})
    IGNORED = frozenset({"updated_at"})
    MASK = "***"


class RateBucket(StrEnum):
    GLOBAL_IP = "global_ip"
    LOGIN_IP = "login_ip"
    LOGIN_ACCOUNT = "login_account"
    REGISTER_IP = "register_ip"
    REFRESH_IP = "refresh_ip"
    FORGOT_IP = "forgot_ip"
    FORGOT_ACCOUNT = "forgot_account"
    RESEND_USER = "resend_user"


# (limit, window seconds); GLOBAL_IP limit comes from settings.
RATE_POLICY: dict[RateBucket, tuple[int, int]] = {
    RateBucket.LOGIN_IP: (10, 60),
    RateBucket.LOGIN_ACCOUNT: (5, 900),
    RateBucket.REGISTER_IP: (5, 3600),
    RateBucket.REFRESH_IP: (30, 60),
    RateBucket.FORGOT_IP: (5, 3600),
    RateBucket.FORGOT_ACCOUNT: (3, 3600),
    RateBucket.RESEND_USER: (3, 3600),
}
