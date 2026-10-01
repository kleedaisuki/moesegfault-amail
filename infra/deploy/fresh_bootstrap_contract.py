"""Shared source-owned first-production storage epoch and artifact coordinates.

Constructing a value is validation, not provider creation or authority. Positive
scope ownership comes from the protected single-attempt creator and its immutable
response-bound receipt; original production/staging stores are never adopted.
"""

from dataclasses import dataclass
from datetime import datetime
import hashlib
import re

from pin_staging_mail import UUID

SHA = re.compile(r"[0-9a-f]{40}\Z")
DIGEST = re.compile(r"[0-9a-f]{64}\Z")
RUN = re.compile(r"[1-9][0-9]{0,19}\Z")
ORIGINAL_DATABASE = "ad06f7f3-8897-4150-b9a9-7a46a8e55b30"
STAGING_DATABASE = "74f35f95-42ce-482c-86e6-dffbdd35cbbe"
ORIGINAL_BUCKET = "moesegfault-mail-raw-production"
REPO = "kleedaisuki/moesegfault-amail"


@dataclass(frozen=True)
class Epoch:
    """One exact same-run full-CI artifact; names cannot be supplied by an operator."""

    source_sha: str
    run_id: str
    artifact_id: int
    manifest_sha256: str
    rust: str
    worker_build: str = "0.8.5"

    def __post_init__(self):
        """Strict types preserve original source/run/compiler ownership coordinates."""
        if (not isinstance(self.source_sha, str) or not SHA.fullmatch(self.source_sha)
                or not isinstance(self.run_id, str) or not RUN.fullmatch(self.run_id)
                or type(self.artifact_id) is not int or self.artifact_id <= 0
                or not isinstance(self.manifest_sha256, str) or not DIGEST.fullmatch(self.manifest_sha256)
                or not isinstance(self.rust, str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", self.rust)
                or self.worker_build != "0.8.5"):
            raise ValueError("fresh_epoch_unreviewed")

    @property
    def key(self) -> str:
        """A bounded 96-bit source/run-derived suffix, not a user-entered hash Secret."""
        return hashlib.sha256(f"{self.source_sha}:{self.run_id}".encode()).hexdigest()[:24]

    @property
    def database_name(self) -> str:
        """Select only the source-owned Mail production epoch namespace."""
        return "moesegfault-mail-production-" + self.key

    @property
    def bucket_name(self) -> str:
        """Preserve the original bucket; this separately owned name fits R2 limits."""
        return ORIGINAL_BUCKET + "-" + self.key


def utc_timestamp(value: object) -> str:
    """Validate exact operational UTC timestamps without treating age as drain."""
    if (not isinstance(value, str) or re.fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", value) is None):
        raise ValueError("fresh_creation_time_unreviewed")
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        raise ValueError("fresh_creation_time_unreviewed") from None
    return value


@dataclass(frozen=True)
class Scope:
    """Response-bound new stores; a validated object alone does not prove creation."""

    epoch: Epoch
    database: str
    database_created_at: str
    bucket_created_at: str

    def __post_init__(self):
        """Never substitute an original/staging store into fresh isolation evidence."""
        if (not isinstance(self.epoch, Epoch) or not isinstance(self.database, str)
                or UUID.fullmatch(self.database) is None
                or self.database in (ORIGINAL_DATABASE, STAGING_DATABASE)):
            raise ValueError("fresh_scope_unreviewed")
        utc_timestamp(self.database_created_at)
        utc_timestamp(self.bucket_created_at)

    @property
    def bucket(self) -> str:
        """The provider's returned bucket must match this derived name exactly."""
        return self.epoch.bucket_name

    @property
    def database_name(self) -> str:
        """Return the exact derived D1 name verified against the successful response."""
        return self.epoch.database_name
