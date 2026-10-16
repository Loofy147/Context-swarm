-- Reference migration only. Review and apply to a disposable development database first.
BEGIN;

CREATE TABLE scs_principals (
  principal_id text PRIMARY KEY,
  status text NOT NULL CHECK (status IN ('active','suspended','revoked')),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE scs_contexts (
  context_id text PRIMARY KEY,
  context_type text NOT NULL,
  owner_principal_id text NOT NULL REFERENCES scs_principals(principal_id),
  lifecycle_status text NOT NULL CHECK (lifecycle_status IN ('draft','active','blocked','archived','superseded')),
  current_version integer NOT NULL CHECK (current_version >= 1),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE scs_context_versions (
  context_id text NOT NULL REFERENCES scs_contexts(context_id),
  version integer NOT NULL CHECK (version >= 1),
  parent_version integer,
  schema_version text NOT NULL,
  canonical_json jsonb NOT NULL,
  canonical_bytes_sha256 char(64) NOT NULL CHECK (canonical_bytes_sha256 ~ '^[a-f0-9]{64}$'),
  created_by text NOT NULL REFERENCES scs_principals(principal_id),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (context_id, version),
  FOREIGN KEY (context_id, parent_version) REFERENCES scs_context_versions(context_id, version),
  CHECK (parent_version IS NULL OR parent_version < version)
);

ALTER TABLE scs_contexts ADD CONSTRAINT scs_context_current_version_fk
  FOREIGN KEY (context_id, current_version) REFERENCES scs_context_versions(context_id, version)
  DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE scs_relationships (
  source_context_id text NOT NULL REFERENCES scs_contexts(context_id),
  relationship_type text NOT NULL CHECK (relationship_type IN ('parent_of','depends_on','references','derived_from','conflicts_with','supersedes','shares_with')),
  target_context_id text NOT NULL REFERENCES scs_contexts(context_id),
  created_by text NOT NULL REFERENCES scs_principals(principal_id),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (source_context_id, relationship_type, target_context_id),
  CHECK (source_context_id <> target_context_id)
);

CREATE TABLE scs_artifacts (
  digest char(64) PRIMARY KEY CHECK (digest ~ '^[a-f0-9]{64}$'),
  storage_key text NOT NULL UNIQUE,
  byte_length bigint NOT NULL CHECK (byte_length >= 0),
  media_type text NOT NULL,
  schema_version text,
  origin_ref text,
  verification_status text NOT NULL CHECK (verification_status IN ('unverified','verified','rejected')),
  created_by text NOT NULL REFERENCES scs_principals(principal_id),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE scs_context_artifacts (
  context_id text NOT NULL,
  version integer NOT NULL,
  digest char(64) NOT NULL REFERENCES scs_artifacts(digest),
  role text NOT NULL,
  PRIMARY KEY (context_id, version, digest, role),
  FOREIGN KEY (context_id, version) REFERENCES scs_context_versions(context_id, version)
);

CREATE TABLE scs_events (
  event_id text PRIMARY KEY,
  event_type text NOT NULL,
  context_id text REFERENCES scs_contexts(context_id),
  actor_ref text NOT NULL,
  authorization_ref text,
  base_version integer,
  result_version integer,
  causation_ref text,
  correlation_ref text,
  payload jsonb NOT NULL,
  payload_digest char(64) NOT NULL CHECK (payload_digest ~ '^[a-f0-9]{64}$'),
  occurred_at timestamptz NOT NULL,
  recorded_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE scs_outbox (
  outbox_id bigserial PRIMARY KEY,
  event_id text NOT NULL UNIQUE REFERENCES scs_events(event_id),
  job_type text NOT NULL,
  idempotency_key text NOT NULL UNIQUE,
  payload jsonb NOT NULL,
  status text NOT NULL CHECK (status IN ('pending','processing','completed','failed','blocked')),
  attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
  available_at timestamptz NOT NULL DEFAULT now(),
  locked_until timestamptz,
  last_error_code text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE scs_grants (
  grant_id text PRIMARY KEY,
  principal_id text NOT NULL REFERENCES scs_principals(principal_id),
  resource_type text NOT NULL,
  resource_id text NOT NULL,
  permission text NOT NULL,
  granted_by text NOT NULL REFERENCES scs_principals(principal_id),
  expires_at timestamptz,
  revoked_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE scs_approvals (
  approval_id text PRIMARY KEY,
  operation_digest char(64) NOT NULL CHECK (operation_digest ~ '^[a-f0-9]{64}$'),
  resource_type text NOT NULL,
  resource_id text NOT NULL,
  proposer_principal_id text NOT NULL REFERENCES scs_principals(principal_id),
  approver_principal_id text REFERENCES scs_principals(principal_id),
  status text NOT NULL CHECK (status IN ('pending','approved','rejected','expired','revoked')),
  policy_version text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  decided_at timestamptz,
  CHECK (status <> 'approved' OR (approver_principal_id IS NOT NULL AND decided_at IS NOT NULL))
);

CREATE INDEX scs_relationships_target_idx ON scs_relationships(target_context_id);
CREATE INDEX scs_events_context_recorded_idx ON scs_events(context_id, recorded_at);
CREATE INDEX scs_outbox_ready_idx ON scs_outbox(status, available_at);
CREATE INDEX scs_grants_lookup_idx ON scs_grants(principal_id, resource_type, resource_id, permission);

COMMIT;
