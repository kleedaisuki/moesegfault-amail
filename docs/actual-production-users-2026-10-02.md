# Owned production mail journey

The actual-production-users workflow uses two dedicated protected production
Identity accounts, isolated hosted native CLI sessions and normal public commands.
It is not a JWT/D1/API shortcut or a generic test framework.
[36942533661](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36942533661)
passed A-to-B notification, B-to-A reply, received TEXT/HTML/assets, filters,
automatic semantic indexing, read state, ZIP export, deletion/isolation and delivered
feedback for those same two sends. [Validation](validation.md) is the status authority.

Explicit register/journey phases require RUN_OWNED_PRODUCTION_USERS. Credentials
are PRODUCTION_ACTOR_A_USERNAME/PASSWORD and PRODUCTION_ACTOR_B_USERNAME/PASSWORD
repository Secrets, never copied human/staging accounts. Partial registration is
recovered as the same account, not hidden by new credentials. The root coordinates
temporary exact verification routes and closes each before vetted OTP submission.
No credentials, OTP, OAuth URL or raw MIME in logs. Keep task files in root .temp.

The lane never changes global policy. When held, only the separately authorized
recipient-bound one-use grant with GRANT_OWNED_PRODUCTION_TWO_USER_SENDS may enable
its two synthetic sends. No grant is needed when allowed. Other send_held outcomes
are normal blockers, not permission to evade policy. Single submissions only:
unknown provider outcome forbids a blind second journey. Actual recipient archive
content and exact asset bytes prove delivery; send success alone does not.

Do not rerun a completed production campaign merely after a documentation/CI change.
Use existing evidence unless the actual product boundary changed or failed.
