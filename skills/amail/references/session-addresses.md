# Session, bootstrap and address lifecycle

Read only for first use, authentication or an address operation. Installed
v0.2.0 commands do not establish release publication or remote policy.

## First authorized task

If installation is needed, select a complete actually published release for the
current OS. Verify CLI and matching Agent Skill using that release's SHA256SUMS;
never substitute a candidate merely because stable assets are missing. Once
installed, check `amail --version` and read the [privacy disclosure](privacy.md)
before first mailbox use if the user has not already understood it.

```sh
amail login
amail auth status
amail address list
```

The agent starts login; the human completes Identity browser sign-in/consent.
Never request a password, token, browser session or copied authorization code.
Reuse an appropriate active owned address rather than automatically creating one.
The production Identity issuer and staging issuer are different realms; a rejected
mail request does not justify switching realms or bypassing validation.

`amail auth logout` removes the local credential when the platform permits it and
attempts refresh-token revocation. It does not promise logout from the browser's
Identity single sign-on session. Login uses an ephemeral `127.0.0.1` callback and
checks the configured issuer; do not weaken that check to resolve an error.

## Own address operations

```sh
amail address add alice
amail address delete alice@mail.moesegfault.dev
```

Choose a user-authorized available local part. User addresses belong under
`mail.moesegfault.dev`, not the apex `moesegfault.dev`; `mail@moesegfault.dev` is a
site sender, not a user mailbox. Service names are reserved. An account has at
most ten pending/active/non-retired address slots, subject to its plan, approved
overage budget and retained pre-upgrade address allowance. All existing users move
to Free while retaining every registered address; do not retire an address merely
to fit Free. Existing excess addresses are grandfathered, not newly billable slots.
Read [billing](billing.md) for effective allowance. The service reserves two of
the provider's 200 literal routes for operational intake, leaving a bounded
198-user-alias design. Capacity estimates do not prove provider availability.

After timeout, `503` or `routing_unavailable`, creation is ambiguous: inspect
the **same owned alias** with `address list`, not a new local part. `active` needs
no retry; `pending` may be retried with the same name only after reconciliation
establishes no active provider route and service health. If state remains unclear,
escalate safe error code/status/request ID for authorized exact-alias inspection.
The ordinary agent should not operate provider control planes directly.

`deleting` can persist during routing reconciliation. Do not race another add
against retirement or assume CLI absence proves provider-route removal. A retired
name remains reserved to prevent old mail reaching a future owner.
`capacity_exhausted` means stop, not try another alias to evade the cap.
