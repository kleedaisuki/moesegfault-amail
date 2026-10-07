//! Account-scoped v0.2 resource admission and durable, provider-aware usage accounting.
//! All amounts are integer CNY micros; storage uses decimal bytes and periods use UTC seconds.

use crate::{auth::Principal, bind_num, bind_str, database::Database, AppError, AppResult};
use serde::{Deserialize, Serialize};

/// Uniform service-safety burst bound, independent of a commercial plan.
pub(crate) const SENDS_PER_MINUTE: i64 = 2;
/// Shared provider-exposure ceiling; this is not an individual monthly entitlement.
pub(crate) const GLOBAL_OUTBOUND_RECIPIENTS_PER_DAY: i64 = 10_000;
/// Routing platform slots remain independent of included/grandfathered addresses.
pub(crate) const OWNER_ADDRESS_PLATFORM_LIMIT: i64 = 10;

/// Verified Billing authority, never accepted directly from an agent request.
pub(crate) struct Snapshot {
    /// Closed tariff identifier, independent of marketing display strings.
    pub plan: String,
    /// Immutable opaque amail principal identifier used by Billing.
    pub billing_owner_id: String,
    /// Human consent receipt preserved with every eventual usage event.
    pub authorization_id: String,
    /// Validated originating server span retained across deferred usage delivery.
    pub origin_traceparent: Option<String>,
    /// Explicit human-approved variable-spending cap; zero denies paid growth.
    pub overage_budget_micros: i64,
    /// Paid entitlement expiry in Unix seconds; Free has no expiry.
    pub valid_until: Option<i64>,
    /// Monotonic authority timestamp prevents an older refresh from rolling back consent.
    pub authority_updated_at: i64,
}

/// Current local entitlement and measured resource use; private owner IDs stay server-side.
#[derive(Deserialize, Serialize)]
pub(crate) struct Account {
    pub plan: String,
    pub included_outbound: i64,
    pub included_storage_bytes: i64,
    pub included_addresses: i64,
    pub grandfathered_addresses: i64,
    pub billing_owner_id: Option<String>,
    /// Private immutable authority receipt; omit from public account projections.
    pub authorization_id: Option<String>,
    /// Server-only causal context, never a public account identifier.
    pub origin_traceparent: Option<String>,
    pub overage_budget_micros: i64,
    pub valid_until: Option<i64>,
    pub authority_updated_at: i64,
    pub period_start: i64,
    pub period_end: i64,
    pub accrued_micros: i64,
    pub reserved_micros: i64,
    pub outbound_accepted: i64,
    pub outbound_reserved: i64,
    pub storage_bytes: i64,
    pub address_count: i64,
}

impl Account {
    /// Human consent, not a paid plan alone, permits variable-resource growth.
    pub(crate) fn overage_enabled(&self) -> bool {
        self.overage_budget_micros > 0
            && self.billing_owner_id.is_some()
            && self.authorization_id.is_some()
    }

    /// Included address slots preserve legacy allocations without pretending all ten are free.
    pub(crate) fn address_limits(&self) -> serde_json::Value {
        let effective = self.included_addresses.max(self.grandfathered_addresses);
        serde_json::json!({
            "limit":effective,"limit_kind":"effective_included_addresses",
            "included_limit":self.included_addresses,
            "grandfathered_limit":self.grandfathered_addresses,
            "effective_included_limit":effective,
            "platform_limit":OWNER_ADDRESS_PLATFORM_LIMIT,
            "overage_enabled":self.overage_enabled()
        })
    }

    /// Closed commercial projection excludes payer IDs, authorization receipts and causal context.
    pub(crate) fn sending_allowance(&self) -> serde_json::Value {
        serde_json::json!({
            "plan":self.plan,"period_start":self.period_start,"period_end":self.period_end,
            "outbound":{"meter":"outbound_recipients","included":self.included_outbound,
                "accepted":self.outbound_accepted,"reserved":self.outbound_reserved,
                "remaining_included":(self.included_outbound-self.outbound_accepted-self.outbound_reserved).max(0)},
            "overage":{"enabled":self.overage_enabled(),"currency":"CNY",
                "budget_micros":self.overage_budget_micros,"accrued_micros":self.accrued_micros,
                "reserved_micros":self.reserved_micros,
                "remaining_budget_micros":(self.overage_budget_micros-self.accrued_micros-self.reserved_micros).max(0)}
        })
    }
}

/// Initialize a permanent Free account and roll calendar periods without releasing unknown sends.
pub(crate) async fn ensure_account(database: &Database, user: &Principal) -> AppResult<()> {
    database.batch(vec![
        database.prepare("INSERT OR IGNORE INTO resource_accounts(owner_iss,owner_sub) VALUES(?1,?2)")
            .bind(&[bind_str(&user.iss),bind_str(&user.sub)])?,
        database.prepare("UPDATE resource_accounts SET accounting_tick=MIN(unixepoch(),COALESCE(valid_until,unixepoch())) WHERE owner_iss=?1 AND owner_sub=?2")
            .bind(&[bind_str(&user.iss),bind_str(&user.sub)])?,
        database.prepare("UPDATE resource_accounts SET plan='free',included_outbound=100,included_storage_bytes=200000000,included_addresses=1,overage_budget_micros=0,valid_until=NULL,accounting_tick=unixepoch() WHERE owner_iss=?1 AND owner_sub=?2 AND valid_until IS NOT NULL AND valid_until<=unixepoch()")
            .bind(&[bind_str(&user.iss),bind_str(&user.sub)])?,
        database.prepare("INSERT OR IGNORE INTO resource_periods(owner_iss,owner_sub,period_start,period_end,included_outbound,entitlement_outbound,accounted_at) SELECT owner_iss,owner_sub,unixepoch('now','start of month'),unixepoch('now','start of month','+1 month'),included_outbound,included_outbound,unixepoch('now','start of month') FROM resource_accounts WHERE owner_iss=?1 AND owner_sub=?2")
            .bind(&[bind_str(&user.iss),bind_str(&user.sub)])?,
        database.prepare("UPDATE resource_periods SET included_outbound=MAX(outbound_accepted+outbound_reserved,(SELECT included_outbound FROM resource_accounts a WHERE a.owner_iss=resource_periods.owner_iss AND a.owner_sub=resource_periods.owner_sub)),entitlement_outbound=(SELECT included_outbound FROM resource_accounts a WHERE a.owner_iss=resource_periods.owner_iss AND a.owner_sub=resource_periods.owner_sub) WHERE owner_iss=?1 AND owner_sub=?2 AND period_start=unixepoch('now','start of month') AND entitlement_outbound!=(SELECT included_outbound FROM resource_accounts a WHERE a.owner_iss=resource_periods.owner_iss AND a.owner_sub=resource_periods.owner_sub)")
            .bind(&[bind_str(&user.iss),bind_str(&user.sub)])?,
    ]).await?;
    Ok(())
}

/// Settle elapsed stock time before a mutation, refresh or scheduled outbox drain.
pub(crate) async fn accrue(database: &Database, user: &Principal) -> AppResult<()> {
    ensure_account(database, user).await
}

/// Apply a server-verified entitlement without changing identity, mail, grandfather rights or usage.
pub(crate) async fn apply_snapshot(
    database: &Database,
    user: &Principal,
    snapshot: &Snapshot,
) -> AppResult<()> {
    let (outbound, bytes, addresses) = match snapshot.plan.as_str() {
        "free" => (100, 200_000_000, 1),
        "lite" => (1_000, 2_000_000_000_i64, 3),
        "plus" => (5_000, 10_000_000_000_i64, 5),
        _ => return Err(AppError::bad("billing_plan_invalid")),
    };
    if snapshot.overage_budget_micros < 0
        || snapshot.billing_owner_id.is_empty()
        || snapshot.authorization_id.is_empty()
        || snapshot.authority_updated_at < 0
    {
        return Err(AppError::bad("billing_snapshot_invalid"));
    }
    if snapshot
        .origin_traceparent
        .as_deref()
        .is_some_and(|raw| crate::trace::parse_parent(raw).is_none())
    {
        return Err(AppError::bad("invalid_trace_context"));
    }
    ensure_account(database, user).await?;
    let origin = snapshot
        .origin_traceparent
        .as_deref()
        .map(bind_str)
        .unwrap_or(wasm_bindgen::JsValue::NULL);
    let expiry = snapshot
        .valid_until
        .map(bind_num)
        .unwrap_or(wasm_bindgen::JsValue::NULL);
    database.batch(vec![
        database.prepare("UPDATE resource_accounts SET plan=?3,included_outbound=?4,included_storage_bytes=?5,included_addresses=?6,billing_owner_id=?7,origin_traceparent=(CASE WHEN authorization_id IS NOT ?11 THEN ?12 ELSE COALESCE(origin_traceparent,?12) END),authorization_id=?11,overage_budget_micros=?8,valid_until=?9,authority_updated_at=?10 WHERE owner_iss=?1 AND owner_sub=?2 AND authority_updated_at<=?10 AND (billing_owner_id IS NULL OR billing_owner_id=?7)")
            .bind(&[bind_str(&user.iss),bind_str(&user.sub),bind_str(&snapshot.plan),bind_num(outbound),bind_num(bytes),bind_num(addresses),bind_str(&snapshot.billing_owner_id),bind_num(snapshot.overage_budget_micros),expiry,bind_num(snapshot.authority_updated_at),bind_str(&snapshot.authorization_id),origin])?,
        database.prepare("UPDATE resource_periods SET included_outbound=MAX(outbound_accepted+outbound_reserved,(SELECT included_outbound FROM resource_accounts a WHERE a.owner_iss=resource_periods.owner_iss AND a.owner_sub=resource_periods.owner_sub)),entitlement_outbound=(SELECT included_outbound FROM resource_accounts a WHERE a.owner_iss=resource_periods.owner_iss AND a.owner_sub=resource_periods.owner_sub) WHERE owner_iss=?1 AND owner_sub=?2 AND period_start=unixepoch('now','start of month') AND entitlement_outbound!=(SELECT included_outbound FROM resource_accounts a WHERE a.owner_iss=resource_periods.owner_iss AND a.owner_sub=resource_periods.owner_sub)")
            .bind(&[bind_str(&user.iss),bind_str(&user.sub)])?,
    ]).await?;
    Ok(())
}

/// Read local state after expiry/period reconciliation; no upstream call is needed for a Free owner.
pub(crate) async fn status(database: &Database, user: &Principal) -> AppResult<Account> {
    ensure_account(database, user).await?;
    database
        .prepare("SELECT * FROM resource_current WHERE owner_iss=?1 AND owner_sub=?2")
        .bind(&[bind_str(&user.iss), bind_str(&user.sub)])?
        .first::<Account>(None)
        .await?
        .ok_or_else(|| AppError {
            status: 503,
            code: "resource_account_missing",
        })
}

/// Atomically hold canonical recipient units before provider submission; retries reuse one reservation.
pub(crate) async fn reserve_send(
    database: &Database,
    user: &Principal,
    idem: &str,
    units: i64,
    origin_traceparent: Option<&str>,
) -> AppResult<()> {
    if units <= 0 {
        return Err(AppError::bad("invalid_recipients"));
    }
    if origin_traceparent.is_some_and(|raw| crate::trace::parse_parent(raw).is_none()) {
        return Err(AppError::bad("invalid_trace_context"));
    }
    let origin = origin_traceparent
        .map(bind_str)
        .unwrap_or(wasm_bindgen::JsValue::NULL);
    ensure_account(database, user).await?;
    let result=database.prepare("INSERT INTO resource_send_reservations(owner_iss,owner_sub,idem_key,period_start,units,authorization_id,origin_traceparent) SELECT ?1,?2,?3,period_start,?4,authorization_id,?5 FROM resource_current WHERE owner_iss=?1 AND owner_sub=?2 AND NOT EXISTS(SELECT 1 FROM resource_send_reservations r WHERE r.owner_iss=?1 AND r.owner_sub=?2 AND r.idem_key=?3)")
        .bind(&[bind_str(&user.iss),bind_str(&user.sub),bind_str(idem),bind_num(units),origin])?.run().await;
    if let Err(error) = result {
        if error.to_string().contains("outbound_quota_exhausted") {
            return Err(AppError {
                status: 429,
                code: "outbound_quota_exhausted",
            });
        }
        return Err(error.into());
    }
    #[derive(Deserialize)]
    struct Reservation {
        units: i64,
        state: String,
    }
    let row=database.prepare("SELECT units,state FROM resource_send_reservations WHERE owner_iss=?1 AND owner_sub=?2 AND idem_key=?3")
        .bind(&[bind_str(&user.iss),bind_str(&user.sub),bind_str(idem)])?.first::<Reservation>(None).await?
        .ok_or_else(||AppError {status:503,code:"send_reservation_missing"})?;
    if row.units != units || row.state != "reserved" {
        return Err(AppError::conflict("send_reservation_conflict"));
    }
    Ok(())
}

/// Release only a definitely unsubmitted attempt. Unknown/provider-accepted attempts cannot be released.
pub(crate) async fn release_send(
    database: &Database,
    user: &Principal,
    idem: &str,
) -> AppResult<()> {
    database.batch(vec![
        database.prepare("DELETE FROM resource_send_reservations WHERE owner_iss=?1 AND owner_sub=?2 AND idem_key=?3 AND state='reserved' AND EXISTS(SELECT 1 FROM send_requests s WHERE s.owner_iss=?1 AND s.owner_sub=?2 AND s.idem_key=?3 AND s.state IN ('preparing','reserving','rejected'))")
            .bind(&[bind_str(&user.iss),bind_str(&user.sub),bind_str(idem)])?,
        database.prepare("UPDATE send_requests SET quota_reserved=0 WHERE owner_iss=?1 AND owner_sub=?2 AND idem_key=?3 AND state='preparing'")
            .bind(&[bind_str(&user.iss),bind_str(&user.sub),bind_str(idem)])?,
    ]).await?;
    Ok(())
}

#[cfg(test)]
mod projection_tests {
    use super::*;

    /// Fixture uses private sentinels to ensure introspection cannot leak authority or tracing IDs.
    fn account() -> Account {
        Account {
            plan: "free".into(),
            included_outbound: 100,
            included_storage_bytes: 200_000_000,
            included_addresses: 1,
            grandfathered_addresses: 0,
            billing_owner_id: None,
            authorization_id: None,
            origin_traceparent: None,
            overage_budget_micros: 0,
            valid_until: None,
            authority_updated_at: 0,
            period_start: 1,
            period_end: 2,
            accrued_micros: 0,
            reserved_micros: 0,
            outbound_accepted: 0,
            outbound_reserved: 0,
            storage_bytes: 0,
            address_count: 0,
        }
    }

    #[test]
    fn address_projection_distinguishes_inclusion_grandfathering_and_platform_capacity() {
        let mut owner = account();
        let free = owner.address_limits();
        assert_eq!(free["limit"], 1);
        assert_eq!(free["included_limit"], 1);
        assert_eq!(free["platform_limit"], 10);
        assert_eq!(free["overage_enabled"], false);
        owner.grandfathered_addresses = 7;
        assert_eq!(owner.address_limits()["effective_included_limit"], 7);
        owner.included_addresses = 5;
        owner.overage_budget_micros = 5_000;
        assert_eq!(owner.address_limits()["limit"], 7);
        assert_eq!(
            owner.address_limits()["overage_enabled"],
            false,
            "a budget without human authority is not consent"
        );
        owner.billing_owner_id = Some("private-payer".into());
        owner.authorization_id = Some("private-authority".into());
        assert_eq!(owner.address_limits()["overage_enabled"], true);
    }

    #[test]
    fn sending_projection_reports_monthly_shared_holds_without_private_ids() {
        let mut owner = account();
        owner.outbound_accepted = 97;
        owner.outbound_reserved = 4;
        owner.overage_budget_micros = 10_000;
        owner.accrued_micros = 2_000;
        owner.reserved_micros = 5_000;
        owner.billing_owner_id = Some("private-payer".into());
        owner.authorization_id = Some("private-authority".into());
        owner.origin_traceparent = Some("private-context".into());
        let value = owner.sending_allowance();
        assert_eq!(value["outbound"]["included"], 100);
        assert_eq!(value["outbound"]["accepted"], 97);
        assert_eq!(value["outbound"]["reserved"], 4);
        assert_eq!(value["outbound"]["remaining_included"], 0);
        assert_eq!(value["overage"]["remaining_budget_micros"], 3_000);
        assert_eq!(value["overage"]["enabled"], true);
        for sentinel in ["private-payer", "private-authority", "private-context"] {
            assert!(!value.to_string().contains(sentinel));
        }
    }
}
