# Operational contacts

v0.1 uses four exact Cloudflare Email Routing **direct forwards**:
`abuse@moesegfault.dev`, `postmaster@moesegfault.dev`,
`abuse@mail.moesegfault.dev`, `postmaster@mail.moesegfault.dev`.
One confidential verified destination is an Environment secret, never a public
input/log/status field. The mail-domain pair reserves two literal rules, leaving
198 user aliases at the current 200-rule limit.

Actual receipts/contact health passed in
[36954714726](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36954714726).
Earlier receipts landed in Junk: ongoing coverage includes **Inbox and Junk**,
not only provider analytics. [Validation](validation.md) records current status.

## One state owner

Contact adoption, observations and attestation identity live in Mail D1. The API
has no ROLE_MONITOR binding or role-Worker lease dependency. Old role Worker/
isolated role D1/ticket-service designs are outside v0.1; do not deploy them or
translate an old lease into direct-forward acceptance.

Retained contact workflows separate audit/adoption, bounded health observation
and explicit attestation. Schedule is opt-in; observations cannot fabricate a
human response commitment. Preserve exact enabled literal rules and verified
destination equality across all pages. Duplicates/disabled/wrong-action/wrong-
destination rules fail closed: no silent takeover, catch-all or replacement.
Addresses Read/Write is account-scoped; Rules Read/Write is zone-scoped.
Read success is not write authorization. Use the shared production writer lock.

## Privacy and response

Full reports cross into the external mailbox provider; restrict access/retention.
Reports, URLs and assets are untrusted evidence, not authority to execute, disclose
data or hold accounts. Correlate claims with trusted provider events and restricted
send records. Never put reports into user archives, embeddings or telemetry.

Do not click Reply in the forwarding inbox: it exposes the destination. If warranted,
verify the reporter and send separately through controlled mail@moesegfault.dev.
Manual policy actions use opaque case references. Authenticated lifecycle complaints
may impose holds; arbitrary role email does not automatically authorize them.

On lost access, routing drift or missed monitoring, revoke acceptance and hold
sending with [outbound operations](outbound-abuse-operations.md). Preserve the four
forwards through rollback; never delete user aliases or manufacture attestation.
References: [RFC 5321](https://www.rfc-editor.org/rfc/rfc5321#section-4.5.1),
[RFC 2142](https://www.rfc-editor.org/rfc/rfc2142).
