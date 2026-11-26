-- Production hardening: token model, versioning, idempotency, and the audit guard trigger.
-- (Written by hand via the `prisma migrate diff --script` fallback: the schema engine is blocked
--  by an OS Application Control policy in the build environment.)

-- AlterTable: users
ALTER TABLE "users" ADD COLUMN "token_version" INTEGER NOT NULL DEFAULT 0,
ADD COLUMN "email_verified_at" TIMESTAMP(3),
ADD COLUMN "deleted_at" TIMESTAMP(3);

-- AlterTable: notes
ALTER TABLE "notes" ADD COLUMN "version" INTEGER NOT NULL DEFAULT 1;

-- CreateTable: refresh_tokens
CREATE TABLE "refresh_tokens" (
    "id" TEXT NOT NULL,
    "user_id" TEXT NOT NULL,
    "family_id" TEXT NOT NULL,
    "token_hash" TEXT NOT NULL,
    "expires_at" TIMESTAMP(3) NOT NULL,
    "revoked_at" TIMESTAMP(3),
    "replaced_by" TEXT,
    "ip" TEXT,
    "user_agent" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "refresh_tokens_pkey" PRIMARY KEY ("id")
);

-- CreateTable: one_time_tokens
CREATE TABLE "one_time_tokens" (
    "id" TEXT NOT NULL,
    "user_id" TEXT NOT NULL,
    "purpose" TEXT NOT NULL,
    "token_hash" TEXT NOT NULL,
    "expires_at" TIMESTAMP(3) NOT NULL,
    "used_at" TIMESTAMP(3),
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "one_time_tokens_pkey" PRIMARY KEY ("id")
);

-- CreateTable: idempotency_records
CREATE TABLE "idempotency_records" (
    "id" TEXT NOT NULL,
    "scope" TEXT NOT NULL,
    "key" TEXT NOT NULL,
    "request_hash" TEXT NOT NULL,
    "status_code" INTEGER,
    "response" JSONB,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "idempotency_records_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "refresh_tokens_token_hash_key" ON "refresh_tokens"("token_hash");
CREATE INDEX "refresh_tokens_user_id_idx" ON "refresh_tokens"("user_id");
CREATE INDEX "refresh_tokens_family_id_idx" ON "refresh_tokens"("family_id");
CREATE INDEX "refresh_tokens_expires_at_idx" ON "refresh_tokens"("expires_at");

CREATE UNIQUE INDEX "one_time_tokens_token_hash_key" ON "one_time_tokens"("token_hash");
CREATE INDEX "one_time_tokens_user_id_purpose_idx" ON "one_time_tokens"("user_id", "purpose");

CREATE UNIQUE INDEX "idempotency_records_scope_key_key" ON "idempotency_records"("scope", "key");
CREATE INDEX "idempotency_records_created_at_idx" ON "idempotency_records"("created_at");

-- AddForeignKey
ALTER TABLE "refresh_tokens" ADD CONSTRAINT "refresh_tokens_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "one_time_tokens" ADD CONSTRAINT "one_time_tokens_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- Append-only guard: audit_logs may be inserted and (by retention) deleted, and ip/user_agent may
-- be scrubbed to NULL, but nothing else may be updated.
CREATE OR REPLACE FUNCTION audit_logs_guard() RETURNS trigger AS $$
BEGIN
  IF (NEW.id, NEW.occurred_at, NEW.actor_id, NEW.actor_type, NEW.action, NEW.resource_type,
      NEW.resource_id, NEW.outcome, NEW.changes, NEW.metadata, NEW.request_id)
     IS DISTINCT FROM
     (OLD.id, OLD.occurred_at, OLD.actor_id, OLD.actor_type, OLD.action, OLD.resource_type,
      OLD.resource_id, OLD.outcome, OLD.changes, OLD.metadata, OLD.request_id)
     OR (NEW.ip IS NOT NULL AND NEW.ip IS DISTINCT FROM OLD.ip)
     OR (NEW.user_agent IS NOT NULL AND NEW.user_agent IS DISTINCT FROM OLD.user_agent) THEN
    RAISE EXCEPTION 'audit_logs is append-only (only ip and user_agent may be scrubbed to NULL)';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER audit_logs_guard_trg BEFORE UPDATE ON audit_logs
FOR EACH ROW EXECUTE FUNCTION audit_logs_guard();