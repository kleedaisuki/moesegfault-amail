"""Exercise one deployed staging SMTP -> amail ZIP/search workflow.

中文：仅使用已登录的合成账号和真实 SMTP，不打印地址、邮件、标识符或凭据。
English: One-shot, local deployed probe; never substitute API ingestion for SMTP.

Usage (after first-party synthetic registration and native CLI login):
    AMAIL_TEST_SMTP_TOKEN=<private> CF_EMAIL_ROUTING_TOKEN=<private> \
      CLOUDFLARE_ZONE_ID=<private> python infra/tests/staging_mail_e2e.py \
      --confirm-staging --home .temp/staging-identity-flow/RUN/amail-home-1 \
      --amail .temp/staging-smoke-41297c6/amail.exe

The executable and home must already exist. The script never creates an account,
authorizes a browser, changes a release gate or enables general sending.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import format_datetime
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import smtplib
import ssl
import subprocess
import sys
import time
import tomllib
import urllib.request


ROOT = Path(__file__).resolve().parents[2]
TEMP = (ROOT / ".temp").resolve()
API = "https://api.cloudflare.com/client/v4"
DOMAIN = "mail-staging.moesegfault.dev"
INGRESS = "amail-inbound-staging"
ACCOUNT_ADDRESS_LIMIT = 10
DOMAIN_LITERAL_RULE_LIMIT = 200
SENDING_TAG = "176c49089bf54e7e91e3e537eadcc140"
SENDER = "probe@mail-staging.moesegfault.dev"
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000b49444154789c636000020000050001a5f645400000000049454e44ae426082"
)


class ProbeFailure(Exception):
    """A fixed-label failure safe to expose. / 可安全输出的固定标签失败。"""


def check(condition: bool, label: str) -> None:
    """Reject a failed invariant without source data. / 不泄露原始数据地拒绝违约情况。"""

    if not condition:
        raise ProbeFailure(label)


def run_nonce() -> str:
    """Use a guarded hosted-run suffix or an unpredictable local default.

    中文：托管运行仅接受已校验的后缀；本地默认为不可预测随机值。
    """

    supplied = os.environ.get("AMAIL_TEST_RUN_NONCE", "")
    check(not supplied or bool(re.fullmatch(r"[a-f0-9]{16}", supplied)), "run_nonce_invalid")
    return supplied or secrets.token_hex(8)


def acceptance_failure(primary: ProbeFailure | None, cleanup: ProbeFailure | None) -> ProbeFailure | None:
    """Retain both fixed failure stages when cleanup also fails.

    中文：清理也失败时保留原始阶段与清理阶段，绝不误报通过。
    """

    if primary and cleanup:
        return ProbeFailure(f"{primary}_cleanup_{cleanup}")
    return cleanup or primary


def inside_temp(value: str, *, must_exist: bool = True) -> Path:
    """Confine all local artifacts to repository `.temp`. / 限制所有产物在仓库 `.temp`。"""

    path = Path(value).resolve()
    check(TEMP in path.parents, "path_outside_repository_temp")
    if must_exist:
        check(path.exists(), "required_path_missing")
    return path


def cli_env(home: Path) -> dict[str, str]:
    """Pin CLI to staging and prevent telemetry upload. / 固定预发布端点并关闭遥测上传。"""

    allowed = {
        "SYSTEMROOT", "WINDIR", "COMSPEC", "PATH", "PATHEXT", "TEMP", "TMP",
        "USERPROFILE", "APPDATA", "LOCALAPPDATA", "PROGRAMFILES",
        "PROGRAMFILES(X86)", "COMMONPROGRAMFILES", "HOMEDRIVE", "HOMEPATH",
        "LANG", "LC_ALL",
    }
    env = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    env.update(
        AMAIL_HOME=str(home),
        AMAIL_API_BASE="https://mail-staging.moesegfault.dev",
        AMAIL_ISSUER="https://identity-staging.moesegfault.dev",
        AMAIL_CLIENT_ID="amail-cli-staging",
        AMAIL_REDIRECT_URI="http://127.0.0.1/callback",
        AMAIL_TELEMETRY="off",
    )
    return env


SAFE_API_CODES = frozenset({
    "routing_unavailable", "capacity_exhausted", "address_unavailable",
    "address_limit", "address_provision_unknown", "address_state_changed",
    "address_deleting", "address_retired", "not_found", "service_unavailable", "send_held",
    "semantic_index_incomplete",
})


def cli_failure(stderr: bytes, fallback: str) -> str:
    """Extract only a known public API status/code, never raw CLI stderr.

    The Worker emits fixed error codes, but the CLI also prints an opaque
    correlation ID. Keep that ID and all unrecognized text out of Actions logs.
    """

    if len(stderr) > 65_536:
        return fallback
    found = re.search(
        rb"mail API [a-z_.]+ failed: HTTP ([45][0-9]{2})[^\r\n]{0,40}, code=([a-z][a-z0-9_]{0,48})(?:,|\r|\n|$)",
        stderr,
    )
    if not found:
        return fallback
    code = found.group(2).decode("ascii")
    if code not in SAFE_API_CODES:
        return fallback
    return f"{fallback}_http_{found.group(1).decode('ascii')}_{code}"


def amail(binary: Path, env: dict[str, str], *args: str, failure: str) -> list[dict]:
    """Capture JSONL in memory; suppress sensitive stdout/stderr. / 仅在内存解析 JSONL。"""

    try:
        proc = subprocess.run(
            [str(binary), *args], env=env, capture_output=True, timeout=90, check=False
        )
    except (subprocess.TimeoutExpired, OSError):
        raise ProbeFailure(failure) from None
    check(proc.returncode == 0, cli_failure(proc.stderr, failure))
    check(len(proc.stdout) <= 2_000_000, "cli_output_oversized")
    try:
        values = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
    except (ValueError, UnicodeDecodeError):
        raise ProbeFailure("cli_output_invalid") from None
    check(all(isinstance(value, dict) for value in values), "cli_output_shape")
    return values


def amail_not_found(binary: Path, env: dict[str, str], *args: str) -> None:
    """Require the stable 404 error without leaking raw stderr. / 核对稳定 404 而不输出错误正文。"""

    try:
        proc = subprocess.run(
            [str(binary), *args], env=env, capture_output=True, timeout=90, check=False
        )
    except (subprocess.TimeoutExpired, OSError):
        raise ProbeFailure("deleted_resource_check_failed") from None
    check(proc.returncode != 0 and b"code=not_found" in proc.stderr, "deleted_resource_still_accessible")


def cf_rules(zone: str, token: str) -> list[dict]:
    """Read a complete, count-consistent Cloudflare routing inventory."""

    rules: list[dict] = []
    total_count: int | None = None
    for page in range(1, 201):
        path = f"/zones/{zone}/email/routing/rules?per_page=50&page={page}"
        req = urllib.request.Request(
            API + path, headers={"Authorization": "Bearer " + token, "Accept": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=25) as response:
                check(response.status == 200, "routing_read_failed")
                raw = response.read(262_145)
        except Exception:
            raise ProbeFailure("routing_read_failed") from None
        check(len(raw) <= 262_144, "routing_response_oversized")
        try:
            value = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            raise ProbeFailure("routing_response_invalid") from None
        batch, total_count, pages = validated_rule_page(value, page, total_count)
        rules.extend(batch)
        if page == pages:
            return rules
    raise ProbeFailure("routing_page_bound")


def validated_rule_page(value: object, page: int, prior_total: int | None) -> tuple[list[dict], int, int]:
    """Require provider pagination counts before treating a short page as final.

    The live API may omit `total_pages`, but it reports page, per_page, count,
    and total_count. A truncated inventory must never greenlight a mutation.
    """

    check(isinstance(value, dict) and value.get("success") is True, "routing_response_invalid")
    batch, info = value.get("result"), value.get("result_info")
    check(isinstance(batch, list) and all(isinstance(rule, dict) for rule in batch), "routing_response_invalid")
    check(isinstance(info, dict), "routing_pages_invalid")
    available = info.get("total_count")
    check(
        type(info.get("page")) is int and info["page"] == page
        and type(info.get("per_page")) is int and info["per_page"] == 50
        and type(info.get("count")) is int and info["count"] == len(batch)
        and type(available) is int and 0 <= available <= 10_000
        and (prior_total is None or prior_total == available),
        "routing_pages_invalid",
    )
    pages = max(1, (available + 49) // 50)
    reported = info.get("total_pages")
    check(
        reported is None or type(reported) is int
        and (reported == pages or available == 0 and reported == 0),
        "routing_pages_invalid",
    )
    check(
        page <= pages and len(batch) == min(50, max(0, available - (page - 1) * 50)),
        "routing_pages_invalid",
    )
    return batch, available, pages


def assert_staging_sender(zone: str, token: str) -> None:
    """Require provider-enabled staging sender domain before SMTP. / SMTP 前核实预发布发信域已启用。"""

    req = urllib.request.Request(
        f"{API}/zones/{zone}/email/sending/subdomains/{SENDING_TAG}",
        headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            raw = response.read(65_537)
            status = response.status
        check(len(raw) <= 65_536, "staging_sender_status_invalid")
        data = json.loads(raw)
    except Exception:
        raise ProbeFailure("staging_sender_status_unavailable") from None
    row = data.get("result") if isinstance(data, dict) else None
    check(
        status == 200
        and data.get("success") is True
        and isinstance(row, dict)
        and row.get("name") == DOMAIN
        and row.get("enabled") is True,
        "staging_sender_not_enabled",
    )


def route_for(rules: list[dict], address: str) -> list[dict]:
    """Match only exact literal recipients. / 仅匹配精确收件地址规则。"""

    return [
        rule
        for rule in rules
        if isinstance(rule, dict)
        and any(
            isinstance(m, dict)
            and m.get("type") == "literal"
            and m.get("field") == "to"
            and str(m.get("value", "")).lower() == address
            for m in rule.get("matchers") or []
        )
    ]


def assert_address_creation_preflight(owned: list[dict], rules: list[dict], address: str) -> None:
    """Fail before mutation if the owned alias or provider domain is already full.

    The compact CLI intentionally emits address rows, not the API's D1-wide
    capacity object. This check cannot prove global D1 capacity or Rules Write;
    it only rejects known per-account and provider-inventory conflicts. The
    Worker/provider remain authoritative at creation time.
    """

    seen: set[str] = set()
    for row in owned:
        candidate = row.get("address")
        check(isinstance(candidate, str) and bool(candidate), "address_preflight_shape")
        check(row.get("state") in ("active", "pending", "deleting"), "address_preflight_shape")
        normalized = candidate.lower()
        check(normalized not in seen, "address_preflight_shape")
        seen.add(normalized)
    check(address.lower() not in seen, "address_preflight_candidate_owned")
    check(len(seen) < ACCOUNT_ADDRESS_LIMIT, "address_preflight_account_full")

    domain_rules = 0
    for rule in rules:
        check(isinstance(rule, dict), "routing_inventory_shape")
        matchers = rule.get("matchers")
        check(isinstance(matchers, list), "routing_inventory_shape")
        check(all(isinstance(matcher, dict) for matcher in matchers), "routing_inventory_shape")
        if rule.get("name") == f"amail {address}" or route_for([rule], address):
            raise ProbeFailure("address_preflight_candidate_routed")
        if any(
            matcher.get("type") == "literal"
            and matcher.get("field") == "to"
            and isinstance(matcher.get("value"), str)
            and matcher["value"].lower().endswith("@" + DOMAIN)
            for matcher in matchers
        ):
            domain_rules += 1
    check(domain_rules < DOMAIN_LITERAL_RULE_LIMIT, "address_preflight_domain_full")


def assert_route(zone: str, token: str, address: str, present: bool) -> None:
    """Cross-check service state with Cloudflare's exact rule. / 独立核对服务状态和规则。"""

    matches = route_for(cf_rules(zone, token), address)
    if not present:
        check(not matches, "route_orphan_after_retirement")
        return
    check(len(matches) == 1, "route_count_mismatch")
    rule = matches[0]
    check(
        rule.get("enabled") is True
        and rule.get("source") == "api"
        and rule.get("name") == f"amail {address}"
        and rule.get("actions") == [{"type": "worker", "value": [INGRESS]}]
        and rule.get("matchers")
        == [{"type": "literal", "field": "to", "value": address}],
        "route_target_mismatch",
    )


def rows(values: list[dict]) -> list[dict]:
    """Strip pagination records from compact JSONL. / 排除分页记录。"""

    return [value for value in values if "id" in value]


def selected(values: list[dict], target: str, expected: int, label: str) -> list[dict]:
    """Check exact run-owned hit count. / 核对本次测试邮件的精确命中数。"""

    hits = [value for value in rows(values) if value.get("subject") == target]
    check(len(hits) == expected, label)
    return hits


def make_mail(address: str, nonce: str, rich: bool) -> tuple[EmailMessage, dict]:
    """Generate one unique RFC 5322 MIME and its private oracle. / 生成唯一 MIME 和私有预言值。"""

    suffix = "Signal" if rich else "Distractor"
    subject = f"AMAIL-E2E-{nonce}-{suffix}"
    phrase = f"NebulaInvariant-{nonce}" if rich else f"HarborOpposite-{nonce}"
    msg = EmailMessage()
    msg["From"] = SENDER
    msg["To"] = address
    msg["Subject"] = subject
    msg["Message-ID"] = f"<amail-e2e-{nonce}-{suffix.lower()}@{DOMAIN}>"
    msg["Date"] = format_datetime(datetime.now(timezone.utc))
    msg.set_content(f"Synthetic staging notification. {phrase}\n")
    if rich:
        msg.add_alternative(
            f'<p>{phrase}</p><img src="cid:chart-{nonce}" onerror="alert(1)">',
            subtype="html",
        )
        html = msg.get_payload()[-1]
        html.add_related(PNG, maintype="image", subtype="png", cid=f"<chart-{nonce}>", filename="chart.png")
        binary = secrets.token_bytes(73)
        msg.add_attachment(
            binary, maintype="application", subtype="octet-stream", filename="payload.bin"
        )
    else:
        binary = b""
    return msg, {
        "subject": subject,
        "phrase": phrase,
        "submitted_message_id": str(msg["Message-ID"]),
        "asset_digest": hashlib.sha256(binary).digest(),
        "cid": f"chart-{nonce}",
    }


def smtp_send(token: str, address: str, messages: list[EmailMessage]) -> None:
    """Submit via real authenticated TLS SMTP; acceptance is not receipt. / 用真实 SMTP 提交。"""

    try:
        with smtplib.SMTP_SSL(
            "smtp.mx.cloudflare.net", 465, timeout=30, context=ssl.create_default_context()
        ) as smtp:
            smtp.login("api_token", token)
            for message in messages:
                check(not smtp.sendmail(SENDER, [address], message.as_bytes()), "smtp_recipient_refused")
    except ProbeFailure:
        raise
    except Exception:
        raise ProbeFailure("smtp_submission_failed") from None


def await_messages(binary: Path, env: dict[str, str], subjects: set[str]) -> dict[str, dict]:
    """Wait for CLI-visible deliveries, not mere SMTP 250. / 等待 CLI 实际可见的投递。"""

    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        listed = rows(amail(binary, env, "sync", "--limit", "100", failure="sync_failed"))
        found = [item for item in listed if item.get("subject") in subjects]
        if len(found) == len(subjects):
            check(len({item.get("subject") for item in found}) == len(subjects), "duplicate_delivery")
            return {item["subject"]: item for item in found}
        time.sleep(5)
    raise ProbeFailure("cli_delivery_timeout")


def safe_zip(binary: Path, env: dict[str, str], target: str, archive: Path, dest: Path) -> None:
    """Use native CLI ZIP download and extraction. / 使用 CLI 原生 ZIP 下载与安全解包。"""

    amail(binary, env, "read", target, "-o", str(archive), failure="read_archive_failed")
    check(archive.is_file() and archive.stat().st_size > 0, "archive_file_missing")
    amail(binary, env, "unpack", str(archive), "-o", str(dest), failure="unpack_failed")
    check(dest.is_dir(), "archive_directory_missing")
    for entry in dest.rglob("*"):
        check(not entry.is_symlink(), "archive_symlink_present")
        check(entry.resolve() == dest or dest in entry.resolve().parents, "archive_path_escape")


def verify_archive(dest: Path, oracle: dict, address: str, target: str) -> None:
    """Compare immutable receipt, sanitized HTML and byte-exact assets. / 核对回执、HTML 和资源字节。"""

    try:
        manifest = tomllib.loads((dest / "manifest.toml").read_text(encoding="utf-8"))
        body = (dest / "body.txt").read_text(encoding="utf-8")
        html = (dest / "body.html").read_text(encoding="utf-8")
    except (OSError, ValueError, UnicodeDecodeError):
        raise ProbeFailure("archive_body_or_manifest_invalid") from None
    check(
        manifest.get("version") == 1
        and manifest.get("id") == target
        and manifest.get("direction") == "inbound"
        and manifest.get("subject") == oracle["subject"]
        and manifest.get("message_id") == oracle["delivered_message_id"]
        and address in manifest.get("to", []),
        "archive_receipt_mismatch",
    )
    check(oracle["phrase"] in body and oracle["phrase"] in html, "archive_content_mismatch")
    check(f"cid:{oracle['cid']}" in html and "onerror" not in html.lower(), "html_sanitizer_mismatch")
    assets = manifest.get("assets")
    check(isinstance(assets, list) and len(assets) == 2, "archive_asset_count")
    inline = [a for a in assets if a.get("cid") == oracle["cid"]]
    attach = [a for a in assets if a.get("filename") == "payload.bin"]
    check(len(inline) == len(attach) == 1, "archive_asset_metadata")
    check((dest / inline[0]["path"]).read_bytes() == PNG, "inline_asset_bytes")
    check(
        hashlib.sha256((dest / attach[0]["path"]).read_bytes()).digest()
        == oracle["asset_digest"],
        "attachment_digest_mismatch",
    )


def search_cases(binary: Path, env: dict[str, str], address: str, oracle: dict, row: dict) -> None:
    """Exercise composed positive and discriminating negative predicates. / 检验组合正例和反例。"""

    subject, phrase = oracle["subject"], oracle["phrase"]
    received = datetime.fromisoformat(row["received_at"].replace("Z", "+00:00"))
    after = received.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    before = (received + timedelta(seconds=1)).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    common = (
        "--mailbox", address, "--after", after, "--before", before,
        "--title", subject, "--from", SENDER, "--to", address,
        "--body", phrase, "--meta", f"message_id={oracle['delivered_message_id']}", "--unread",
    )
    selected(amail(binary, env, "search", *common, failure="search_positive_failed"), subject, 1, "search_positive_count")
    negative = [
        ("wrong_mailbox", ("--mailbox", "nobody@" + DOMAIN, "--title", subject)),
        ("wrong_title", ("--title", subject + "-missing")),
        ("wrong_body", ("--body", phrase + "-missing", "--title", subject)),
        ("wrong_metadata", ("--meta", f"message_id={oracle['delivered_message_id']}-missing", "--title", subject)),
        ("wrong_time", ("--after", before, "--title", subject)),
        ("exclusive_before", ("--before", after, "--title", subject)),
        ("wrong_case", ("--title", subject.lower(), "--case-sensitive")),
        ("wrong_regex", ("--title", "^NEVERMATCH$", "--regex")),
    ]
    for label, args in negative:
        selected(amail(binary, env, "search", *args, failure=f"search_{label}_failed"), subject, 0, f"search_{label}_count")
    selected(
        amail(binary, env, "search", "--title", f"^AMAIL-E2E-.*-Signal$", "--regex", failure="search_regex_positive_failed"),
        subject, 1, "search_regex_positive_count",
    )


def semantic_cases(
    binary: Path, env: dict[str, str], address: str, nonce: str,
    rich_row: dict, rich_oracle: dict, distractor_row: dict,
) -> None:
    """Check the two delivered messages without adding mail or changing state.

    Document indexing runs on a five-minute Cron. Only the typed incomplete
    index result is retried, under one seven-minute deadline for all four
    searches. Provider/auth/quota failures remain failures, never retries.
    """

    from staging_semantic_e2e import SemanticProbeError, check_cli_search

    deadline = time.monotonic() + 7 * 60

    def search(*args: str) -> list[dict]:
        """Return only complete CLI JSONL rows; suppress raw provider output."""

        while True:
            try:
                return rows(amail(binary, env, "search", *args, failure="semantic_search_failed"))
            except ProbeFailure as error:
                if str(error) != "semantic_search_failed_http_503_semantic_index_incomplete":
                    raise
                if time.monotonic() + 30 >= deadline:
                    raise ProbeFailure("semantic_index_timeout") from None
                time.sleep(30)

    signal = {"id": rich_row.get("id"), "received_at": rich_row.get("received_at"),
              "phrase": rich_oracle["phrase"]}
    distractor = {"id": distractor_row.get("id"), "received_at": distractor_row.get("received_at")}
    try:
        check_cli_search(search, address, nonce, signal, distractor)
    except SemanticProbeError as error:
        raise ProbeFailure(str(error)) from None
    print("semantic_two_message_search_verified")


def cleanup_run(
    binary: Path, env: dict[str, str], zone: str, token: str, address: str, nonce: str
) -> None:
    """Try message and address cleanup independently; require route absence.

    中文：消息清理失败仍须尝试退役地址；以独立规则回读确认没有孤儿路由。
    """

    message_error = False
    try:
        listed = rows(amail(binary, env, "sync", "--limit", "100", failure="cleanup_sync_failed"))
        subjects = {f"AMAIL-E2E-{nonce}-Signal", f"AMAIL-E2E-{nonce}-Distractor"}
        for item in listed:
            if item.get("subject") in subjects:
                amail(binary, env, "delete", item["id"], failure="cleanup_message_delete_failed")
    except Exception:
        message_error = True

    # Do not let a failed message sync or address list suppress retirement.
    # 邮件同步或地址列表失败，也不能阻止退役已知的本次地址。
    retire_error = False
    try:
        amail(binary, env, "address", "delete", address, failure="address_retire_failed")
    except Exception:
        retire_error = True

    # Deletion can remain `deleting` until the five-minute Worker Cron
    # reconciles a provisioning failure. Never call a live alias retired
    # merely because its provider route is already absent.
    deadline = time.monotonic() + 7 * 60
    route_absent = False
    address_absent = False
    while time.monotonic() < deadline:
        try:
            route_absent = not route_for(cf_rules(zone, token), address)
        except Exception:
            route_absent = False
        try:
            owned = amail(binary, env, "address", "list", failure="retire_readback_failed")
            address_absent = not [row for row in owned if row.get("address") == address]
        except Exception:
            address_absent = False
        if route_absent and address_absent:
            break
        time.sleep(3)
    check(route_absent and address_absent, "address_or_route_cleanup_failed")
    check(not message_error, "message_cleanup_failed")
    # A failed delete might mean no address was created; absence is decisive.
    # 删除请求失败可能意味着地址从未创建；最终不存在才是决定性条件。
    if retire_error:
        print("address_route_absent_after_retire_error")
    else:
        print("address_route_retired")


def main() -> int:
    """Run after native login, then retire only the run-owned alias. / 登录后执行并只清理本次别名。"""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-staging", action="store_true")
    parser.add_argument("--home", required=True)
    parser.add_argument("--amail", required=True)
    parser.add_argument("--check-semantic", action="store_true")
    args = parser.parse_args()
    check(args.confirm_staging, "staging_confirmation_required")
    home, binary = inside_temp(args.home), inside_temp(args.amail)
    check(binary.is_file() and home.is_dir(), "cli_binary_or_home_missing")
    zone = os.environ.get("CLOUDFLARE_ZONE_ID", "")
    routing_token = os.environ.get("CF_EMAIL_ROUTING_TOKEN", "")
    smtp_token = os.environ.get("AMAIL_TEST_SMTP_TOKEN", "")
    check(bool(re.fullmatch(r"[a-f0-9]{32}", zone)), "zone_id_missing")
    check(bool(routing_token) and bool(smtp_token), "cloudflare_tokens_missing")
    assert_staging_sender(zone, smtp_token)
    env = cli_env(home)
    status = amail(binary, env, "auth", "status", failure="auth_status_failed")
    check(len(status) == 1 and status[0].get("authenticated") is True, "not_authenticated")
    # A hosted run may crash before cleanup. The protected synthetic password
    # plus run ID/attempt can reconstruct only its alias for exact-rule
    # reconciliation, without publishing the address; local probes stay random.
    # 托管运行崩溃后须有受保护密码及运行编号才能重建别名；本地仍默认随机。
    nonce = run_nonce()
    address = f"e2e-{nonce}@{DOMAIN}"
    part = f"e2e-{nonce}"
    owned = amail(binary, env, "address", "list", failure="address_preflight_failed")
    assert_address_creation_preflight(owned, cf_rules(zone, routing_token), address)
    creation_attempted = False
    primary_error: ProbeFailure | None = None
    cleanup_error: ProbeFailure | None = None
    try:
        creation_attempted = True
        result = amail(binary, env, "address", "add", part, failure="address_register_failed")
        check(len(result) == 1 and result[0].get("address") == address, "address_register_mismatch")
        check(result[0].get("state") in ("pending", "active"), "address_register_state")
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            owned = amail(binary, env, "address", "list", failure="address_readback_failed")
            matching = [r for r in owned if r.get("address") == address]
            if len(matching) == 1 and matching[0].get("state") == "active":
                break
            time.sleep(3)
        else:
            raise ProbeFailure("address_activation_timeout")
        assert_route(zone, routing_token, address, True)
        print("address_and_literal_route_verified")

        # Email Routing rule propagation can lag the control-plane readback.
        # 邮件路由数据面可能落后于规则 API 回读。
        time.sleep(60)
        assert_route(zone, routing_token, address, True)
        rich, rich_oracle = make_mail(address, nonce, True)
        distractor, distractor_oracle = make_mail(address, nonce, False)
        smtp_send(smtp_token, address, [rich, distractor])
        print("smtp_submitted")
        messages = await_messages(binary, env, {rich_oracle["subject"], distractor_oracle["subject"]})
        rich_row = messages[rich_oracle["subject"]]
        target = rich_row.get("id")
        check(isinstance(target, str) and bool(re.fullmatch(r"[A-Za-z0-9_-]+", target)), "message_id_shape")
        detail = amail(binary, env, "get", target, failure="get_failed")
        check(len(detail) == 1 and detail[0].get("read") is False, "get_implicitly_marked_read")
        wire_id = detail[0].get("metadata", {}).get("message_id")
        check(isinstance(wire_id, str) and 3 <= len(wire_id) <= 256, "message_metadata_missing")
        # A changed Message-ID has no attributed cause without an independent
        # raw-ingress/provider oracle; separate it from internal consistency.
        # 缺少独立原始入站或提供商证据时，Message-ID 变化不能归因。
        rich_oracle["delivered_message_id"] = wire_id
        print(
            "source_message_id_preserved"
            if wire_id == rich_oracle["submitted_message_id"]
            else "message_id_changed_unattributed"
        )
        archive_file = home.parent / f"archive-{nonce}.zip"
        archive_dir = home.parent / f"archive-{nonce}"
        safe_zip(binary, env, target, archive_file, archive_dir)
        verify_archive(archive_dir, rich_oracle, address, target)
        detail = amail(binary, env, "get", target, failure="get_after_read_failed")
        check(len(detail) == 1 and detail[0].get("read") is False, "read_implicitly_marked_read")
        print("smtp_to_zip_verified")

        search_cases(binary, env, address, rich_oracle, rich_row)
        if args.check_semantic:
            semantic_cases(
                binary, env, address, nonce, rich_row, rich_oracle,
                messages[distractor_oracle["subject"]],
            )
        amail(binary, env, "mark", target, "--read", failure="mark_read_failed")
        selected(amail(binary, env, "search", "--title", rich_oracle["subject"], "--read", failure="read_search_failed"), rich_oracle["subject"], 1, "read_search_count")
        selected(amail(binary, env, "search", "--title", rich_oracle["subject"], "--unread", failure="unread_search_failed"), rich_oracle["subject"], 0, "unread_search_count")
        amail(binary, env, "delete", target, failure="message_delete_failed")
        selected(amail(binary, env, "search", "--title", rich_oracle["subject"], failure="deleted_search_failed"), rich_oracle["subject"], 0, "deleted_search_count")
        amail_not_found(binary, env, "get", target)
        amail_not_found(binary, env, "read", target, "-o", str(home.parent / f"deleted-{nonce}.zip"))
        remaining = rows(amail(binary, env, "sync", "--limit", "100", failure="other_message_sync_failed"))
        distractors = [r for r in remaining if r.get("subject") == distractor_oracle["subject"]]
        check(len(distractors) == 1, "other_message_lost")
        amail(binary, env, "delete", distractors[0]["id"], failure="distractor_delete_failed")
        print("search_read_delete_verified")
    except Exception as error:
        primary_error = error if isinstance(error, ProbeFailure) else ProbeFailure("probe_unexpected_failure")
    finally:
        if creation_attempted:
            try:
                cleanup_run(binary, env, zone, routing_token, address, nonce)
            except ProbeFailure as error:
                cleanup_error = error
            except Exception:
                cleanup_error = ProbeFailure("cleanup_unexpected_failure")
    failure = acceptance_failure(primary_error, cleanup_error)
    if failure:
        raise failure
    print("staging_inbound_e2e_verified")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ProbeFailure as error:
        print(f"staging_e2e_failed:{error}", file=sys.stderr)
        raise SystemExit(1) from None
    except Exception:
        print("staging_e2e_failed:unexpected_failure", file=sys.stderr)
        raise SystemExit(1) from None
