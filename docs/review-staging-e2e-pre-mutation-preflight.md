# Review: staging E2E pre-mutation address gate

Status: **reviewed, no substantive defect found** at commit `009ff1c` (2026-09-29). This is a source review, not a hosted test or permission attestation.

## Contract and evidence

- `infra/tests/staging_mail_e2e.py::main` derives the HMAC-backed run candidate before the new inventory check. The check completes before `creation_attempted=True` and the sole `amail address add`; its only external calls are authenticated CLI `address list` and Cloudflare Rules GET. A failed preflight therefore cannot create or retire a route. The existing `finally` cleanup still covers the create boundary.
- The CLI's `AddressCommand::List` uses `emit_items` for `addresses`, so its machine output is address JSONL rows, **not** the API's `capacity` object. The preflight correctly counts non-retired rows and rejects an already-owned candidate; the three accepted states match `mail-worker::list_addresses`'s active, pending/provisioning projection, and deleting rows. It does not claim to establish D1-wide capacity or Rules Write.
- `cf_rules` now requires consistent `page`, `per_page=50`, `count`, and `total_count` on every fetched page; it derives the expected last page when the live API omits `total_pages`. It rejects a short non-final page, changed total, unexpected row type, and pagination beyond the bound. The new mocked tests cover the key contradictory/truncated shapes.
- The provider gate rejects an exact literal `to` matcher or conflicting run-rule name for the candidate, and counts one rule per staging-subdomain literal route. It does not count apex routes as staging capacity. Provider GET failures and malformed inventories collapse to fixed labels; raw responses, aliases, and credentials are not printed.

## Scope limits

The inventory is a point-in-time observation, not a lock: another actor could create a route after GET. Neither the CLI list nor the Rules GET proves the Worker's separate token has Write permission, and the Worker/provider create boundary remains authoritative. This is an explicit design limitation, not a defect in a gate that is meant to reject known conflicts before one legitimate E2E attempt. The hosted Python tests and the deployed E2E run were not executed in this review; the pending GitHub Actions result should be assessed separately.
