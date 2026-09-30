-- Staging-only encrypted acceptance operations state; not a public Mail migration.
-- Apply once to the exact reviewed staging MAIL_DB; a table name is not schema proof.
CREATE TABLE staging_acceptance_escrows (
    original_run TEXT PRIMARY KEY CHECK(length(original_run) BETWEEN 1 AND 20 AND original_run NOT GLOB '*[^0-9]*' AND substr(original_run,1,1)!='0'),
    attempt INTEGER NOT NULL CHECK(attempt=1),
    repository TEXT NOT NULL CHECK(repository='kleedaisuki/moesegfault-amail'),
    workflow TEXT NOT NULL CHECK(workflow='.github/workflows/staging-ten-address-acceptance.yml'),
    source_sha TEXT NOT NULL CHECK(length(source_sha)=40 AND source_sha NOT GLOB '*[^a-f0-9]*'),
    schema_version INTEGER NOT NULL CHECK(schema_version=2),
    key_generation TEXT NOT NULL CHECK(length(key_generation) BETWEEN 1 AND 40 AND key_generation NOT GLOB '*[^a-z0-9-]*'),
    envelope_sha TEXT NOT NULL CHECK(length(envelope_sha)=64 AND envelope_sha NOT GLOB '*[^a-f0-9]*'),
    envelope_bytes INTEGER NOT NULL CHECK(envelope_bytes BETWEEN 41 AND 2000256),
    chunk_count INTEGER NOT NULL CHECK(chunk_count BETWEEN 1 AND 31 AND chunk_count=(envelope_bytes+65535)/65536),
    reserved_bytes INTEGER NOT NULL CHECK(reserved_bytes=((envelope_bytes+2)/3)*4+chunk_count*1028+4096),
    artifact_id TEXT CHECK(artifact_id IS NULL OR length(artifact_id) BETWEEN 1 AND 20 AND artifact_id NOT GLOB '*[^0-9]*' AND substr(artifact_id,1,1)!='0'),
    state TEXT NOT NULL CHECK(state IN ('writing','sealed','armed','cleanup_verified')),
    created_at INTEGER NOT NULL DEFAULT (unixepoch()) CHECK(created_at>=0),
    armed_at INTEGER CHECK(armed_at IS NULL OR armed_at>=created_at),
    cleanup_verified_at INTEGER CHECK(cleanup_verified_at IS NULL OR cleanup_verified_at>=created_at),
    cleanup_receipt_sha TEXT CHECK(cleanup_receipt_sha IS NULL OR length(cleanup_receipt_sha)=64 AND cleanup_receipt_sha NOT GLOB '*[^a-f0-9]*'),
    cleanup_verifier_run TEXT CHECK(cleanup_verifier_run IS NULL OR length(cleanup_verifier_run) BETWEEN 1 AND 20 AND cleanup_verifier_run NOT GLOB '*[^0-9]*' AND substr(cleanup_verifier_run,1,1)!='0'),
    cleanup_verifier_sha TEXT CHECK(cleanup_verifier_sha IS NULL OR length(cleanup_verifier_sha)=40 AND cleanup_verifier_sha NOT GLOB '*[^a-f0-9]*'),
    cleanup_check_set TEXT CHECK(cleanup_check_set IS NULL OR cleanup_check_set='quota-readonly-native-teardown-v1'),
    issue_number INTEGER CHECK(issue_number IS NULL OR issue_number>0),
    CHECK(state!='armed' OR armed_at IS NOT NULL),
    CHECK(state!='cleanup_verified' OR cleanup_verified_at IS NOT NULL AND cleanup_receipt_sha IS NOT NULL
        AND cleanup_verifier_run IS NOT NULL AND cleanup_verifier_sha IS NOT NULL AND cleanup_check_set IS NOT NULL)
);

CREATE TABLE staging_acceptance_escrow_chunks (
    original_run TEXT NOT NULL REFERENCES staging_acceptance_escrows(original_run) ON DELETE RESTRICT,
    chunk_index INTEGER NOT NULL CHECK(chunk_index BETWEEN 0 AND 30),
    chunk_bytes INTEGER NOT NULL CHECK(chunk_bytes BETWEEN 1 AND 65536),
    chunk_sha TEXT NOT NULL CHECK(length(chunk_sha)=64 AND chunk_sha NOT GLOB '*[^a-f0-9]*'),
    ciphertext_b64 TEXT NOT NULL CHECK(length(ciphertext_b64) BETWEEN 4 AND 87384 AND ciphertext_b64 NOT GLOB '*[^A-Za-z0-9+/=]*'),
    PRIMARY KEY(original_run,chunk_index)
);

-- New records cannot enter with a forged terminal receipt or arm/artifact state.
CREATE TRIGGER staging_acceptance_initial_state BEFORE INSERT ON staging_acceptance_escrows
WHEN NEW.state!='writing' OR NEW.artifact_id IS NOT NULL OR NEW.armed_at IS NOT NULL
    OR NEW.cleanup_verified_at IS NOT NULL OR NEW.cleanup_receipt_sha IS NOT NULL
    OR NEW.cleanup_verifier_run IS NOT NULL OR NEW.cleanup_verifier_sha IS NOT NULL OR NEW.cleanup_check_set IS NOT NULL
BEGIN SELECT RAISE(ABORT,'escrow_initial_state_invalid'); END;

-- One outstanding envelope is enforced atomically, including incomplete preparation.
CREATE UNIQUE INDEX staging_acceptance_one_outstanding
ON staging_acceptance_escrows((1)) WHERE state IN ('writing','sealed','armed');

CREATE INDEX staging_acceptance_due ON staging_acceptance_escrows(state,armed_at);

-- All nonpurged ciphertext states reserve budget; only verified empty receipts shrink.
CREATE TRIGGER staging_acceptance_budget BEFORE INSERT ON staging_acceptance_escrows
WHEN NEW.reserved_bytes + (SELECT COALESCE(SUM(CASE WHEN state='cleanup_verified' AND NOT EXISTS(
    SELECT 1 FROM staging_acceptance_escrow_chunks c WHERE c.original_run=staging_acceptance_escrows.original_run
) THEN 4096 ELSE reserved_bytes END),0) FROM staging_acceptance_escrows) > 16777216
BEGIN SELECT RAISE(ABORT,'escrow_budget_exhausted'); END;

-- Chunk bounds/phase must match their immutable parent, including the last slice.
CREATE TRIGGER staging_acceptance_chunk_admission BEFORE INSERT ON staging_acceptance_escrow_chunks
WHEN NOT EXISTS(SELECT 1 FROM staging_acceptance_escrows e WHERE e.original_run=NEW.original_run
    AND e.state='writing' AND NEW.chunk_index<e.chunk_count
    AND NEW.chunk_bytes=MIN(65536,e.envelope_bytes-NEW.chunk_index*65536)
    AND length(NEW.ciphertext_b64)=((NEW.chunk_bytes+2)/3)*4)
BEGIN SELECT RAISE(ABORT,'escrow_chunk_admission_invalid'); END;

-- The original envelope and source coordinates cannot be rewritten in place.
CREATE TRIGGER staging_acceptance_binding_immutable
BEFORE UPDATE OF original_run,attempt,repository,workflow,source_sha,schema_version,key_generation,envelope_sha,envelope_bytes,chunk_count,reserved_bytes,created_at
ON staging_acceptance_escrows
BEGIN SELECT RAISE(ABORT,'escrow_binding_immutable'); END;

CREATE TRIGGER staging_acceptance_artifact_immutable BEFORE UPDATE OF artifact_id ON staging_acceptance_escrows
WHEN OLD.artifact_id IS NOT NULL AND NEW.artifact_id IS NOT OLD.artifact_id
BEGIN SELECT RAISE(ABORT,'escrow_artifact_immutable'); END;

-- A terminal receipt cannot be rewritten, acknowledged away or turned into another run.
CREATE TRIGGER staging_acceptance_receipt_immutable
BEFORE UPDATE OF cleanup_verified_at,cleanup_receipt_sha,cleanup_verifier_run,cleanup_verifier_sha,cleanup_check_set
ON staging_acceptance_escrows WHEN OLD.state='cleanup_verified'
BEGIN SELECT RAISE(ABORT,'escrow_receipt_immutable'); END;

CREATE TRIGGER staging_acceptance_arm_immutable BEFORE UPDATE OF armed_at ON staging_acceptance_escrows
WHEN OLD.armed_at IS NOT NULL
BEGIN SELECT RAISE(ABORT,'escrow_arm_immutable'); END;

-- No backward transition can turn an ambiguous armed invocation into a new permission.
CREATE TRIGGER staging_acceptance_state_transition BEFORE UPDATE OF state ON staging_acceptance_escrows
WHEN NOT (OLD.state='writing' AND NEW.state='sealed' OR OLD.state='sealed' AND NEW.state='armed'
    OR OLD.state IN ('writing','sealed','armed') AND NEW.state='cleanup_verified')
BEGIN SELECT RAISE(ABORT,'escrow_state_transition_invalid'); END;

CREATE TRIGGER staging_acceptance_chunks_immutable BEFORE UPDATE ON staging_acceptance_escrow_chunks
BEGIN SELECT RAISE(ABORT,'escrow_chunk_immutable'); END;

-- Future purge is receipt-only; age, acknowledgement and failed jobs are not receipts.
CREATE TRIGGER staging_acceptance_chunks_retained BEFORE DELETE ON staging_acceptance_escrow_chunks
WHEN NOT EXISTS(SELECT 1 FROM staging_acceptance_escrows e WHERE e.original_run=OLD.original_run
    AND e.state='cleanup_verified' AND e.cleanup_verified_at IS NOT NULL AND e.cleanup_receipt_sha IS NOT NULL)
BEGIN SELECT RAISE(ABORT,'escrow_cleanup_receipt_required'); END;

CREATE TRIGGER staging_acceptance_parent_retained BEFORE DELETE ON staging_acceptance_escrows
BEGIN SELECT RAISE(ABORT,'escrow_receipt_retained'); END;
