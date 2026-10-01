"""Fail closed if staging Worker bindings point at production state.

中文：预发部署前检查资源、OIDC 和邮件域名隔离，防止误操作生产账户。
English: Reject staging configurations that could operate on production state.
"""

from __future__ import annotations

import pathlib
import sys
import tomllib

ROOT = pathlib.Path(__file__).resolve().parents[2]


def require(actual: object, expected: object, label: str) -> None:
    """断言配置值完全匹配。 / Require an exact reviewed configuration value."""

    if actual != expected:
        raise ValueError(f"unsafe staging {label}: expected {expected!r}, got {actual!r}")


def check() -> None:
    """验证 API、入口和持久化绑定都属于预发。 / Check staging API, ingress, and storage."""

    from check_mail_maintenance import check_source_configs
    check_source_configs()
    with (ROOT / "crates/mail-worker/wrangler.toml").open("rb") as file:
        config = tomllib.load(file)
    if "ADDRESS_DIAGNOSTICS" in config.get("vars", {}):
        raise ValueError("production address diagnostics must be omitted")
    mail = config["env"]["staging"]
    vars_ = mail["vars"]
    require(vars_["IDENTITY_ISSUER"], "https://identity-staging.moesegfault.dev", "issuer")
    require(vars_["OIDC_CLIENT_ID"], "amail-cli-staging", "OIDC client")
    require(vars_["CF_ZONE_ID"], "6edff81c6ed02f412e70868076411a5e", "Cloudflare zone")
    require(vars_["MAIL_DOMAIN"], "mail-staging.moesegfault.dev", "mail domain")
    require(vars_["ADDRESS_DIAGNOSTICS"], "v1", "address diagnostic gate")
    require(vars_["EMAIL_INGRESS_WORKER_NAME"], "amail-inbound-staging", "ingress Worker")
    require(
        mail["routes"],
        [{"pattern": "mail-staging.moesegfault.dev", "custom_domain": True}],
        "HTTP route",
    )
    require(mail["d1_databases"][0]["database_id"], "74f35f95-42ce-482c-86e6-dffbdd35cbbe", "D1 database")
    require(mail["r2_buckets"][0]["bucket_name"], "moesegfault-mail-raw-staging", "R2 bucket")
    if any(binding.get("name") == "OFFICIAL_EMAIL" for binding in mail.get("send_email", [])):
        raise ValueError("staging must not bind the production official sender")

    with (ROOT / "workers/mail-ingress/wrangler.toml").open("rb") as file:
        ingress = tomllib.load(file)["env"]["staging"]
    require(ingress["vars"]["MAIL_API_ORIGIN"], "https://mail-staging.moesegfault.dev", "ingress origin")
    require(ingress["services"][0]["service"], "amail-mail-staging", "ingress service binding")


def main() -> int:
    """只打印安全检查结果，不输出凭据。 / Report safety checks without credentials."""

    try:
        check()
    except (KeyError, IndexError, ValueError, OSError, tomllib.TOMLDecodeError) as error:
        print(f"staging isolation check failed: {error}", file=sys.stderr)
        return 1
    print("staging mail Worker, ingress, Identity, D1, and R2 bindings are isolated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
