"""Fail deployment before Wrangler sees sentinel or cross-environment ops bindings.

中文：在 Wrangler 部署前拒绝哨兵配置或跨环境的运营存储绑定。
English: Reject placeholder values and staging/production binding overlap before deploy.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import tomllib


def check(config: dict, target: str) -> None:
    """Validate non-secret deploy invariants; do not print values on failure.

    中文：验证非秘密部署不变量，失败时不输出配置值。
    """

    env = config if target == "production" else config["env"]["staging"]
    vars_ = env["vars"]
    expected = {
        "production": ("amail-ops", "mail.moesegfault.dev", "https://ops.moesegfault.dev", "true"),
        "staging": ("amail-ops-staging", "mail-staging.moesegfault.dev", "https://ops-staging.moesegfault.dev", "false"),
    }[target]
    name, role_domain, origin, apex = expected
    if env["name"] != name or vars_["ROLE_DOMAIN"] != role_domain or vars_["OPS_ORIGIN"] != origin or vars_["ALLOW_APEX_ROLES"] != apex:
        raise ValueError("operator environment identity mismatch")
    if env.get("workers_dev") is not False or env["routes"] != [{"pattern": origin.removeprefix("https://"), "custom_domain": True}]:
        raise ValueError("operator HTTP route is not the exact private hostname")
    if env["observability"].get("enabled") is not False:
        raise ValueError("operator raw-mail observability must remain disabled")
    if "addresses" in config or "addresses" in env:
        raise ValueError("literal role routes must be managed by the conflict-safe tool")
    if vars_["TEAM_DOMAIN"].startswith("https://REPLACE_") or not vars_["TEAM_DOMAIN"].startswith("https://"):
        raise ValueError("Cloudflare Access team domain is not configured")
    if vars_["ACCESS_AUD"].startswith("REPLACE_") or not vars_["ACCESS_AUD"]:
        raise ValueError("Cloudflare Access audience is not configured")
    databases = env["d1_databases"]
    buckets = env["r2_buckets"]
    senders = env["send_email"]
    expected_database = f"moesegfault-mail-ops-{target}"
    expected_bucket = f"moesegfault-mail-ops-reports-{target}"
    user_databases = {"ad06f7f3-8897-4150-b9a9-7a46a8e55b30", "74f35f95-42ce-482c-86e6-dffbdd35cbbe"}
    if len(databases) != 1 or databases[0]["binding"] != "OPS_DB" or databases[0]["database_name"] != expected_database or len(databases[0]["database_id"]) != 36 or "REPLACE" in databases[0]["database_id"] or databases[0]["database_id"] in user_databases:
        raise ValueError("dedicated OPS_DB is not configured")
    if len(buckets) != 1 or buckets[0]["binding"] != "OPS_REPORTS" or buckets[0]["bucket_name"] != expected_bucket:
        raise ValueError("dedicated OPS_REPORTS is not configured")
    if len(senders) != 1 or senders[0]["name"] != "OFFICIAL_EMAIL" or senders[0]["allowed_sender_addresses"] != ["mail@moesegfault.dev"]:
        raise ValueError("official alert sender is not constrained")
    other = config["env"]["staging"] if target == "production" else config
    if databases[0]["database_id"] == other["d1_databases"][0]["database_id"] or buckets[0]["bucket_name"] == other["r2_buckets"][0]["bucket_name"]:
        raise ValueError("staging and production operator storage overlap")


def main() -> int:
    """Validate an explicitly prepared config, not the checked-in template.

    中文：仅校验明确准备的配置，不把仓库模板当成已部署实例。
    """

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--target", choices=("production", "staging"), required=True)
    args = parser.parse_args()
    try:
        with args.config.open("rb") as stream:
            check(tomllib.load(stream), args.target)
    except (OSError, KeyError, TypeError, ValueError, tomllib.TOMLDecodeError) as error:
        print(f"Operator deploy preflight failed: {type(error).__name__}", file=sys.stderr)
        return 1
    print(f"Operator {args.target} non-secret config passed; Access policy and Worker secrets still require live verification")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
