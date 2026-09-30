"""Literal c3f binding fixture from immutable daaab1f/run 36761367007 evidence.

No current TOML or production matcher constructs this fixture. Values are public
resource identities already documented, not secrets or a stored provider body.
"""
import copy

VERSION = "c3f6401a-1e84-4f51-91df-ae77d90683e9"
BINDINGS = [
    {"name": "MAIL_DB", "type": "d1", "database_id": "74f35f95-42ce-482c-86e6-dffbdd35cbbe"},
    {"name": "ROLE_MONITOR", "type": "d1", "database_id": "272e024c-453a-461b-bea0-c37a62c89d24"},
    {"name": "MAIL_BODIES", "type": "r2_bucket", "bucket_name": "moesegfault-mail-raw-staging"},
    {"name": "EMAIL", "type": "send_email"},
    {"name": "OPENROUTER_API_KEY", "type": "secret_text"},
    {"name": "CF_EMAIL_ROUTING_TOKEN", "type": "secret_text"},
    {"name": "INGRESS_SECRET", "type": "secret_text"},
    {"name": "ADDRESS_DIAGNOSTICS", "type": "plain_text", "text": "v1"},
    {"name": "IDENTITY_ISSUER", "type": "plain_text", "text": "https://identity-staging.moesegfault.dev"},
    {"name": "OIDC_CLIENT_ID", "type": "plain_text", "text": "amail-cli-staging"},
    {"name": "CF_ZONE_ID", "type": "plain_text", "text": "6edff81c6ed02f412e70868076411a5e"},
    {"name": "MAIL_DOMAIN", "type": "plain_text", "text": "mail-staging.moesegfault.dev"},
    {"name": "EMAIL_INGRESS_WORKER_NAME", "type": "plain_text", "text": "amail-inbound-staging"},
    {"name": "OPENROUTER_EMBEDDING_MODEL", "type": "plain_text", "text": "qwen/qwen3-embedding-8b"},
]


def historical_version():
    """Return an independent mutable provider-shaped synthetic historical version."""
    return {"id": VERSION, "resources": {"bindings": copy.deepcopy(BINDINGS)}}
