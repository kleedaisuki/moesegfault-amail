"""Compare logical TXT data without confusing DNS string chunks with records."""

from __future__ import annotations

import dns.exception
import dns.tokenizer


def txt_content(value: str) -> str:
    """Decode quoted DNS presentation; preserve unquoted provider content exactly.

    RFC 1035 TXT RDATA consists of one or more character strings. RFC 6376
    requires concatenating those strings without adding whitespace for DKIM.
    Provider API presentation may quote the already-joined logical value as one
    string longer than a wire component's 255-byte limit. Use the pinned DNS
    tokenizer's escape decoding, not an RDATA constructor that encodes that limit.
    Parsing raw unquoted API content as zone text would instead lose semicolons
    as comments and split meaningful spaces, so only quoted presentation is parsed.
    """
    if not value.lstrip(" \t").startswith('"'):
        return value
    try:
        tokenizer = dns.tokenizer.Tokenizer(value)
        strings: list[bytes] = []
        while True:
            token = tokenizer.get(want_comment=True)
            if token.is_eof():
                break
            if not token.is_quoted_string():
                raise dns.exception.SyntaxError
            strings.append(token.unescape_to_bytes().value)
        return b"".join(strings).decode("utf-8")
    except (dns.exception.DNSException, UnicodeDecodeError, ValueError):
        # Provider values may include key data; never propagate parser prose.
        raise ValueError("dns_txt_presentation_invalid") from None
