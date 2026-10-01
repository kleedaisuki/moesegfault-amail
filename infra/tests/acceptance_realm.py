"""Immutable service coordinates for dormant hosted acceptance adapters.

This is configuration, not dispatch authorization. Production callers must also
prove protected credentials, serving provenance, containment and send hold.
No provider account IDs or secrets are obtained from ambient staging state.
"""

from dataclasses import dataclass, fields
from pathlib import Path
import re
from typing import Literal
from urllib.parse import urlsplit


@dataclass(frozen=True)
class AcceptanceRealm:
    """Bind native authorization, inbound routing and SMTP to one explicit realm.

    All coordinates are required. Instances contain no credentials. In production
    public coordinates are pinned to first-party services, and resource IDs must
    differ from staging. Selecting a name never supplies credentials or defaults.
    """

    name: Literal["staging", "production"]
    domain: str
    mail_api: str
    issuer: str
    login_origin: str
    account_origin: str
    client_id: str
    ingress: str
    mail_database_id: str
    sending_tag: str
    sender: str

    def __post_init__(self) -> None:
        """Reject malformed coordinates before any browser or provider capability."""
        if self.name not in ("staging", "production"):
            raise ValueError("acceptance_realm_invalid")
        if any(not isinstance(getattr(self, field.name), str) or not getattr(self, field.name)
               for field in fields(self)):
            raise ValueError("acceptance_realm_invalid")
        if not re.fullmatch(r"[a-z0-9]+(?:[.-][a-z0-9]+)+", self.domain):
            raise ValueError("acceptance_realm_invalid")
        for origin in (self.mail_api, self.issuer, self.login_origin, self.account_origin):
            parsed = urlsplit(origin)
            if (parsed.scheme != "https" or not parsed.hostname or parsed.netloc != parsed.hostname
                    or parsed.path or parsed.query or parsed.fragment
                    or not re.fullmatch(r"[a-z0-9]+(?:[.-][a-z0-9]+)+", parsed.hostname)):
                raise ValueError("acceptance_realm_invalid")
        if (self.mail_api != "https://" + self.domain
                or not re.fullmatch(r"[a-z0-9-]{1,64}", self.client_id)
                or not re.fullmatch(r"[a-z0-9-]{1,63}", self.ingress)
                or not re.fullmatch(r"[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}", self.mail_database_id)
                or not re.fullmatch(r"[a-f0-9]{32}", self.sending_tag)
                or not re.fullmatch(r"[a-z0-9._-]+@" + re.escape(self.domain), self.sender)):
            raise ValueError("acceptance_realm_invalid")
        if self.name == "production":
            # Credentials may only reach the reviewed first-party production origins.
            pinned = {
                "domain": "mail.moesegfault.dev", "mail_api": "https://mail.moesegfault.dev",
                "issuer": "https://identity.moesegfault.dev",
                "login_origin": "https://login.moesegfault.dev",
                "account_origin": "https://account.moesegfault.dev", "client_id": "amail-cli",
                "ingress": "amail-inbound", "sender": "probe@mail.moesegfault.dev",
            }
            if any(getattr(self, name) != value for name, value in pinned.items()):
                raise ValueError("production_coordinate_not_pinned")
            for field in fields(self):
                value = getattr(self, field.name)
                if field.name != "name" and ("staging" in value or value == getattr(STAGING, field.name)):
                    raise ValueError("production_staging_coordinate_forbidden")

    def cli_coordinates(self, home: Path) -> dict[str, str]:
        """Return only pinned CLI variables; callers still filter inherited secrets."""
        return {
            "AMAIL_HOME": str(home), "AMAIL_API_BASE": self.mail_api,
            "AMAIL_ISSUER": self.issuer, "AMAIL_CLIENT_ID": self.client_id,
            "AMAIL_REDIRECT_URI": "http://127.0.0.1/callback", "AMAIL_TELEMETRY": "off",
        }


STAGING = AcceptanceRealm(
    name="staging", domain="mail-staging.moesegfault.dev",
    mail_api="https://mail-staging.moesegfault.dev",
    issuer="https://identity-staging.moesegfault.dev",
    login_origin="https://login-staging.moesegfault.dev",
    account_origin="https://account-staging.moesegfault.dev", client_id="amail-cli-staging",
    ingress="amail-inbound-staging", mail_database_id="74f35f95-42ce-482c-86e6-dffbdd35cbbe",
    sending_tag="176c49089bf54e7e91e3e537eadcc140", sender="probe@mail-staging.moesegfault.dev",
)
