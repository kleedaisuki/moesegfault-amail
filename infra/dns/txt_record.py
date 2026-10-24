"""Compare logical TXT data without confusing DNS string chunks with records."""

from __future__ import annotations

import dns.exception
import dns.rdata
import dns.rdataclass
import dns.rdatatype


def txt_content(value: str) -> str:
    """Decode quoted DNS presentation; preserve unquoted provider content exactly.

    RFC 1035 TXT RDATA consists of one or more character strings. RFC 6376
    requires concatenating those strings without adding whitespace for DKIM.
    Parsing raw unquoted API content as zone text would instead lose semicolons
    as comments and split meaningful spaces, so only quoted presentation is parsed.
    """
    if not value.lstrip(" \t").startswith('"'):
        return value
    try:
        record = dns.rdata.from_text(dns.rdataclass.IN, dns.rdatatype.TXT, value)
        strings: tuple[bytes, ...] = record.strings
        return b"".join(strings).decode("utf-8")
    except (dns.exception.DNSException, UnicodeDecodeError, ValueError):
        # Provider values may include key data; never propagate parser prose.
        raise ValueError("dns_txt_presentation_invalid") from None
