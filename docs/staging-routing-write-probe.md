# Staging routing-token Write policy diagnostic

The first hosted address-add failure in [run 36524101354](staging-address-add-incident-36524101354.md) did not preserve the Cloudflare rule-creation status. A successful Rules list proves only read permission. `infra/provider/probe_routing_write.py` provides an **opt-in, non-mutating** diagnostic of the **configured policy** for the existing GitHub staging `CF_EMAIL_ROUTING_TOKEN` and exact `CF_ZONE_ID`. It does not create a route, send mail, or change token permissions.

## Manual hosted usage

Run only from a manually dispatched, GitHub-hosted diagnostic job after its workflow is reviewed. The workflow integration is deliberately separate; this file does not add a dispatch path. Pass existing GitHub secrets through environment variables, not shell arguments or echoed commands:

```yaml
- name: Inspect staging routing-token Write policy
  env:
    CF_ZONE_ID: 6edff81c6ed02f412e70868076411a5e
    CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
    CF_EMAIL_ROUTING_TOKEN: ${{ secrets.CF_EMAIL_ROUTING_TOKEN }}
    CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
  run: python infra/provider/probe_routing_write.py
```

The zone ID above matches the reviewed staging `ci.yml` literal; re-check it if the staging zone changes. The broad `CLOUDFLARE_API_TOKEN` must have **API Tokens Read** for a user-owned routing token, or **Account API Tokens Read** for an account-owned token. Its current access is not established: if it cannot read details, the result is `unavailable`; do not compensate by granting token-management Write or by posting a dummy rule. Restrict job permissions and logs, and do not upload raw API responses as artifacts.

The script uses only `GET /user/tokens/verify` (falling back to the account verify endpoint), then the corresponding user/account token-details GET with the separate reader credential. It retains the returned token ID only in memory. Its stdout contains only fixed outcome labels, optional numeric HTTP status/error codes, and never credentials, IDs, policy resources, rule data, or addresses. `configured_grant`, `no_grant`, and `explicit_deny` are conclusions from complete recognized token policies for this exact zone. `unknown` and `unavailable` are fail-closed. A configured grant **does not prove an effective successful POST**: token IP/time conditions, account membership or service state, credential drift between GitHub and the deployed Worker, and provider validation may still matter. Inspect those privately or use future privacy-reviewed instrumentation if necessary.

The parser recognizes the [documented zone selectors and deny precedence](https://developers.cloudflare.com/fundamentals/api/how-to/create-via-api/), the [Email Routing Rules Write permission](https://developers.cloudflare.com/fundamentals/api/reference/permissions/), and the [user](https://developers.cloudflare.com/api/resources/user/subresources/tokens/methods/get/) or [account token details](https://developers.cloudflare.com/api/resources/accounts/subresources/tokens/methods/get/) APIs. The [verify API](https://developers.cloudflare.com/api/resources/user/subresources/tokens/methods/verify/) alone reports validity, not permissions. Do not use an invalid `{}` POST as a permission test: it is still a mutating endpoint and a validation error is not a contractual Write proof.
