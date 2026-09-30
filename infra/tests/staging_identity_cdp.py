"""Drive only staging first-party Identity pages through a local Chrome CDP session.

中文：仅经本机 Chrome CDP 操作预发布 Identity 第一方页面；绝不在日志打印 URL 或秘密。
English: This is a deliberately interactive deployment probe, not a unit test.

Usage (after the private inbox and exact route are verified):
    python infra/tests/staging_identity_cdp.py register --confirm-staging --run-dir .temp/staging-identity-flow/RUN
    python infra/tests/staging_identity_cdp.py login --confirm-staging --run-dir .temp/staging-identity-flow/RUN --amail .temp/staging-cli/amail.exe

The helper generates username/password and stores only a same-user Windows
DPAPI blob. The operator supplies only the vetted OTP through a hidden prompt.
Registration closes the exact route before submitting OTP.
No browser, route or account action occurs merely by importing this module.
"""

from __future__ import annotations

import argparse
import base64
import getpass
import json
import os
from pathlib import Path
import queue
import re
import secrets
import socket
import subprocess
import sys
import threading
import time
from typing import Callable
from urllib.parse import parse_qs, urlsplit
from urllib.request import ProxyHandler, build_opener

import websocket


ROOT = Path(__file__).resolve().parents[2]
TEMP = (ROOT / ".temp").resolve()
ROUTE_HELPER = ROOT / "workers" / "identity-test-inbox" / "ensure_route.py"
LOGIN_ORIGIN = "https://login-staging.moesegfault.dev"
ISSUER = "https://identity-staging.moesegfault.dev"
MAIL_API = "https://mail-staging.moesegfault.dev"
ACCOUNT_ORIGIN = "https://account-staging.moesegfault.dev"
CLIENT = "amail-cli-staging"
ALIAS = "amail-e2e@moesegfault.dev"
CREDENTIAL_FILE = "credential.dpapi"
DPAPI_ENTROPY = b"moesegfault-amail-staging-identity-test-v1"
REGISTRATION = "/v1/password/registrations"
PASSWORD_AUTH = "/v1/password/authentications"
VERIFICATION_START = re.compile(r"^/v1/me/contacts/[^/]+/verification-transactions$")
VERIFICATION_DONE = re.compile(r"^/v1/me/contacts/[^/]+/verification-transactions/[^/]+/completion$")
# Hosted Windows Chrome can need longer than a dozen seconds to create its
# first isolated profile. Keep a finite pre-mutation budget instead of racing
# cold startup; the enclosing E2E job has its own overall deadline.
CHROME_CDP_STARTUP_SECONDS = 45


class ProbeError(Exception):
    """A safe stage failure whose message contains no browser/provider data. / 不含浏览器或供应商数据的安全阶段错误。"""


def generate_credential() -> tuple[str, str]:
    """Create a unique synthetic username and 256-bit random password.

    中文：生成唯一合成用户名与 256 位随机密码，不借用真人账号。
    """

    return f"amail_e2e_{secrets.token_hex(8)}", secrets.token_urlsafe(32)


def store_credential(run_dir: Path, username: str, password: str, address: str = ALIAS) -> None:
    """Persist only a current-user DPAPI blob before registration submission.

    中文：提交注册前仅保存当前 Windows 用户可解密的 DPAPI 密文。
    """

    if os.name != "nt":
        raise ProbeError("windows_dpapi_required")
    try:
        import win32crypt

        plaintext = json.dumps({"username": username, "password": password, "address": address}).encode("utf-8")
        ciphertext = win32crypt.CryptProtectData(
            plaintext, "amail staging test account", DPAPI_ENTROPY, None, None, 0
        )
        fd = os.open(run_dir / CREDENTIAL_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(ciphertext)
    except Exception:
        raise ProbeError("dpapi_credential_write_failed") from None


def decoded_credential(value: object) -> tuple[str, str, str]:
    """Validate a DPAPI payload while preserving pre-address legacy blobs."""

    if not isinstance(value, dict):
        raise ProbeError("dpapi_credential_invalid")
    username, password = value.get("username"), value.get("password")
    # Existing verified account blobs predate address parameterization.
    address = value.get("address", ALIAS)
    if not isinstance(username, str) or not isinstance(password, str) or not isinstance(address, str):
        raise ProbeError("dpapi_credential_invalid")
    if not re.fullmatch(r"[a-z0-9_]{3,32}", username) or not 15 <= len(password) <= 128:
        raise ProbeError("dpapi_credential_invalid")
    if not re.fullmatch(r"amail-e2e(?:-[a-z0-9-]{1,21})?@moesegfault\.dev", address):
        raise ProbeError("dpapi_credential_invalid")
    return username, password, address


def load_credential(run_dir: Path) -> tuple[str, str, str]:
    """Decrypt the same-user test credential without exposing it to arguments/logs.

    中文：仅由同一 Windows 用户解密测试凭据，不写入命令参数或日志。
    """

    if os.name != "nt":
        raise ProbeError("windows_dpapi_required")
    path = run_dir / CREDENTIAL_FILE
    try:
        import win32crypt

        if path.stat().st_size > 16_384:
            raise ProbeError("dpapi_credential_invalid")
        _, plaintext = win32crypt.CryptUnprotectData(
            path.read_bytes(), DPAPI_ENTROPY, None, None, 0
        )
        return decoded_credential(json.loads(plaintext))
    except ProbeError:
        raise
    except Exception:
        raise ProbeError("dpapi_credential_read_failed") from None


def under_temp(path: str) -> Path:
    """Confine every test artifact to repository `.temp`. / 将所有测试产物限制在仓库 `.temp`。"""

    resolved = Path(path).resolve()
    if resolved == TEMP or TEMP not in resolved.parents:
        raise ProbeError("artifact_path_outside_repo_temp")
    return resolved


def chrome_path() -> Path:
    """Use an already installed Chrome; never download a browser. / 使用已安装的 Chrome，不下载浏览器。"""

    configured = os.environ.get("AMAIL_TEST_CHROME")
    candidates = [
        Path(configured) if configured else Path("__missing__"),
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise ProbeError("installed_chrome_unavailable")


def local_port() -> int:
    """Select a temporary localhost-only CDP port. / 选择仅本机使用的临时 CDP 端口。"""

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def browser_environment() -> dict[str, str]:
    """Pass only platform basics into Chrome and the non-secret CLI process.

    中文：仅传递平台基础环境，避免 Chrome/CLI 继承未知名称的秘密。
    """

    allowed = {
        "SYSTEMROOT", "WINDIR", "COMSPEC", "PATH", "PATHEXT", "TEMP", "TMP",
        "USERPROFILE", "APPDATA", "LOCALAPPDATA", "PROGRAMFILES",
        "PROGRAMFILES(X86)", "COMMONPROGRAMFILES", "HOMEDRIVE", "HOMEPATH",
        "LANG", "LC_ALL",
    }
    return {
        key: value for key, value in os.environ.items()
        if key.upper() in allowed
    }


def route(action: str | None = None, address: str = ALIAS) -> str:
    """Audit or close the one reviewed alias without echoing provider output.

    中文：只审计或关闭唯一受审别名，不回显供应商输出。
    """

    args = [sys.executable, str(ROUTE_HELPER), "--address", address]
    if action:
        args.append(action)
    result = subprocess.run(args, capture_output=True, text=True, timeout=60, check=False)
    if result.returncode:
        raise ProbeError("exact_route_control_failed")
    state = result.stdout.strip()
    if state not in {"enabled", "absent", "removed", "created"}:
        raise ProbeError("exact_route_state_unexpected")
    return state


class Browser:
    """Minimal CDP page driver with no HAR, screenshot, console or body logging.

    中文：最小 CDP 页面驱动，不保存 HAR、截图、控制台或响应正文日志。
    """

    def __init__(self, profile: Path):
        """Launch an isolated headless Chrome profile under `.temp`. / 在 `.temp` 启动隔离的无头 Chrome。"""

        self.port = local_port()
        self.profile = profile
        self.profile.mkdir(parents=True, exist_ok=False)
        origin = f"http://127.0.0.1:{self.port}"
        self.process = subprocess.Popen(
            [
                str(chrome_path()),
                "--headless=new",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-extensions",
                "--disable-sync",
                f"--user-data-dir={self.profile}",
                "--remote-debugging-address=127.0.0.1",
                f"--remote-debugging-port={self.port}",
                f"--remote-allow-origins={origin}",
                "about:blank",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=browser_environment(),
        )
        try:
            self.ws = self._connect(origin)
            self.next_id = 0
            self.request_methods: dict[str, str] = {}
            self.responses: dict[str, list[tuple[int, str]]] = {}
            self.finished: set[str] = set()
            self.call("Page.enable")
            self.call("Runtime.enable")
            self.call("Network.enable")
        except BaseException:
            # A constructor failure never reaches the caller's browser finally.
            # 构造失败时调用者还没有实例，必须在此关闭 Chrome。
            try:
                if hasattr(self, "ws"):
                    self.ws.close()
            except Exception:
                pass
            try:
                if self.process.poll() is None:
                    self.process.kill()
                self.process.wait(timeout=5)
            except Exception:
                pass
            raise

    def _connect(self, origin: str) -> websocket.WebSocket:
        """Attach only to the local page target. / 仅连接本机页面目标。"""

        deadline = time.monotonic() + CHROME_CDP_STARTUP_SECONDS
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                break
            try:
                with build_opener(ProxyHandler({})).open(f"{origin}/json", timeout=1) as response:
                    targets = json.load(response)
                page = next(t for t in targets if t.get("type") == "page")
                endpoint = urlsplit(page["webSocketDebuggerUrl"])
                if endpoint.scheme != "ws" or endpoint.hostname != "127.0.0.1" or endpoint.port != self.port:
                    raise ProbeError("chrome_cdp_endpoint_mismatch")
                return websocket.create_connection(
                    page["webSocketDebuggerUrl"], timeout=1, origin=origin,
                    http_no_proxy=["127.0.0.1"],
                )
            except (OSError, ValueError, KeyError, StopIteration, websocket.WebSocketException):
                time.sleep(0.15)
        exited = self.process.poll() is not None
        raise ProbeError("chrome_exited_before_cdp" if exited else "chrome_cdp_startup_timeout")

    def _receive(self, timeout: float) -> dict:
        """Retain statuses only for actual POSTs, never CORS preflight responses.

        中文：按请求 ID 关联方法；只保留真实 POST，不把 OPTIONS 预检当成注册结果。
        """

        self.ws.settimeout(timeout)
        try:
            message = json.loads(self.ws.recv())
        except (TimeoutError, OSError, ValueError, websocket.WebSocketException) as error:
            raise ProbeError("chrome_cdp_timeout_or_disconnect") from error
        method = message.get("method")
        params = message.get("params") or {}
        request_id = params.get("requestId", "")
        if method == "Network.requestWillBeSent":
            # CDP emits requestWillBeSent before responseReceived. Redirects may
            # reuse an ID, so always replace the method with the new request's.
            # CDP 先发送请求事件；重定向可能复用 ID，故须以最新请求方法为准。
            if request_id:
                self.request_methods[request_id] = params.get("request", {}).get("method", "")
        elif method == "Network.responseReceived" and self.request_methods.get(request_id) == "POST":
            url = params.get("response", {}).get("url", "")
            parsed = urlsplit(url)
            path = parsed.path
            if f"{parsed.scheme}://{parsed.netloc}" == ISSUER and (
                path in (REGISTRATION, PASSWORD_AUTH)
                or VERIFICATION_START.fullmatch(path) or VERIFICATION_DONE.fullmatch(path)
            ):
                self.responses.setdefault(path, []).append(
                    (int(params.get("response", {}).get("status", 0)), request_id)
                )
        elif method == "Network.loadingFinished":
            self.request_methods.pop(request_id, None)
            self.finished.add(request_id)
        elif method == "Network.loadingFailed":
            self.request_methods.pop(request_id, None)
        return message

    def call(self, method: str, params: dict | None = None, timeout: float = 20) -> dict:
        """Send one CDP method without exposing request values. / 发送 CDP 方法但不暴露参数值。"""

        self.next_id += 1
        request_id = self.next_id
        self.ws.send(json.dumps({"id": request_id, "method": method, "params": params or {}}))
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            message = self._receive(max(0.1, deadline - time.monotonic()))
            if message.get("id") == request_id:
                if "error" in message:
                    detail = str(message["error"].get("message", "")).lower()
                    if method == "Runtime.evaluate" and (
                        "execution context was destroyed" in detail
                        or "cannot find context" in detail
                        or "target navigated" in detail
                    ):
                        raise ProbeError("chrome_execution_context_changed")
                    raise ProbeError("chrome_cdp_command_failed")
                return message.get("result") or {}
        raise ProbeError("chrome_cdp_command_timeout")

    def evaluate(self, expression: str) -> object:
        """Evaluate bounded first-party DOM operations only. / 只执行限定的第一方 DOM 操作。"""

        result = self.call(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True, "awaitPromise": False},
        )
        if result.get("exceptionDetails"):
            raise ProbeError("first_party_dom_evaluation_failed")
        return result.get("result", {}).get("value")

    def navigate(self, url: str) -> None:
        """Navigate only to reviewed staging authorization/Login origins.

        中文：只导航到已审查的预发布授权与登录域名。
        """

        parsed = urlsplit(url)
        if f"{parsed.scheme}://{parsed.netloc}" not in {LOGIN_ORIGIN, ISSUER, ACCOUNT_ORIGIN}:
            raise ProbeError("unexpected_navigation_origin")
        self.call("Page.navigate", {"url": url})

    def wait_dom(self, selector: str, timeout: float = 45) -> None:
        """Wait for one expected first-party field. / 等待一个预期第一方字段。"""

        deadline = time.monotonic() + timeout
        expression = f"Boolean(document.querySelector({json.dumps(selector)}))"
        while time.monotonic() < deadline:
            try:
                if self.evaluate(expression):
                    return
            except ProbeError as error:
                if str(error) != "chrome_execution_context_changed":
                    raise
            time.sleep(0.2)
        raise ProbeError("first_party_field_missing")

    def require_login_origin(self) -> None:
        """Refuse to type credentials on any other origin. / 拒绝向其他来源输入凭据。"""

        if self.evaluate("location.origin") != LOGIN_ORIGIN:
            raise ProbeError("first_party_origin_mismatch")

    def require_account_origin(self) -> None:
        """Type a recovery code only on the reviewed staging Account Center."""

        if self.evaluate("location.origin") != ACCOUNT_ORIGIN:
            raise ProbeError("first_party_origin_mismatch")

    def fill(self, selector: str, value: str) -> None:
        """Fill a named input through DOM events; no direct Identity API calls.

        中文：通过 DOM 事件填写具名输入框，不直接调用 Identity API。
        """

        script = (
            "(()=>{const e=document.querySelector(" + json.dumps(selector) + ");"
            "if(!(e instanceof HTMLInputElement))return false;"
            "Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(e,"
            + json.dumps(value)
            + ");e.dispatchEvent(new Event('input',{bubbles:true}));"
            "e.dispatchEvent(new Event('change',{bubbles:true}));return true})()"
        )
        if self.evaluate(script) is not True:
            raise ProbeError("first_party_input_missing")

    def click(self, selector: str) -> None:
        """Click only an expected first-party button. / 仅点击预期的第一方按钮。"""

        expression = f"(()=>{{const e=document.querySelector({json.dumps(selector)});if(!e)return false;e.click();return true}})()"
        if self.evaluate(expression) is not True:
            raise ProbeError("first_party_button_missing")

    def response(self, predicate, timeout: float = 45) -> tuple[int, str]:
        """Wait for a matching actual POST status without printing URLs or bodies.

        中文：仅等待匹配的真实 POST 状态，不输出 URL 或正文。
        """

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for path, observations in self.responses.items():
                if predicate(path) and observations:
                    return observations[-1]
            try:
                self._receive(min(0.5, max(0.1, deadline - time.monotonic())))
            except ProbeError as error:
                if str(error) != "chrome_cdp_timeout_or_disconnect":
                    raise
        raise ProbeError("identity_response_missing")

    def response_body(self, request_id: str, timeout: float = 20) -> dict:
        """Inspect only the verification result in memory. / 只在内存检查验证结果。"""

        deadline = time.monotonic() + timeout
        while request_id not in self.finished and time.monotonic() < deadline:
            try:
                self._receive(min(0.5, max(0.1, deadline - time.monotonic())))
            except ProbeError as error:
                if str(error) != "chrome_cdp_timeout_or_disconnect":
                    raise
        if request_id not in self.finished:
            raise ProbeError("verification_response_incomplete")
        result = self.call("Network.getResponseBody", {"requestId": request_id})
        body = result.get("body", "")
        if result.get("base64Encoded"):
            body = base64.b64decode(body).decode("utf-8")
        try:
            parsed = json.loads(body)
        except (ValueError, UnicodeDecodeError):
            raise ProbeError("verification_response_invalid") from None
        if not isinstance(parsed, dict):
            raise ProbeError("verification_response_invalid")
        return parsed

    def close(self) -> None:
        """Close the local browser without retaining protocol logs. / 关闭本地浏览器且不保留协议日志。"""

        try:
            self.ws.close()
        finally:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)


def registration(
    run_dir: Path, address: str = ALIAS, *,
    credential: tuple[str, str] | None = None,
    code_source: Callable[[float], str] | None = None,
) -> None:
    """Complete normal first-party registration, then remove route before OTP submit.

    中文：完成正常第一方注册，并在提交验证码前移除路由。
    """

    if route(address=address) != "enabled":
        raise ProbeError("exact_route_not_enabled")
    browser: Browser | None = None
    try:
        # Cloudflare accepted an immediate send after Rules readback but later
        # classified it as routing_unknown_address; wait for data-plane settle.
        # Rules 回读成功后立即发送仍可能 routing_unknown_address，故等待数据面稳定。
        time.sleep(60)
        if route(address=address) != "enabled":
            raise ProbeError("exact_route_changed_during_settle")
        username, password = credential if credential is not None else generate_credential()
        decoded_credential({"username": username, "password": password, "address": address})
        store_credential(run_dir, username, password, address)
        browser = Browser(run_dir / "registration-browser")
        browser.navigate(f"{LOGIN_ORIGIN}/register")
        browser.wait_dom('input[name="display_name"]')
        browser.require_login_origin()
        for name, value in {
            "display_name": "amail staging test",
            "username": username,
            "email": address,
            "password": password,
            "password_confirm": password,
        }.items():
            browser.fill(f'input[name="{name}"]', value)
        browser.click('button[name="method"][value="password"]')
        status, _ = browser.response(lambda path: path == REGISTRATION, timeout=50)
        if status != 201:
            raise ProbeError(f"registration_http_{status}")
        browser.wait_dom('form.verification-card input[name="code"]')
        started, _ = browser.response(lambda path: bool(VERIFICATION_START.fullmatch(path)), timeout=40)
        if started != 201:
            raise ProbeError(f"verification_start_http_{started}")
        challenge_started = time.monotonic()
        if code_source is None:
            print("registration_created_verification_started; inspect private MIME and enter code once")
            code = getpass.getpass("Vetted eight-digit OTP (hidden): ").strip()
        else:
            code = code_source(challenge_started).strip()
        if not re.fullmatch(r"[0-9]{8}", code):
            raise ProbeError("otp_shape_invalid")
        if time.monotonic() - challenge_started >= 9 * 60:
            raise ProbeError("otp_window_expired_without_attempt")
        if route("--remove", address) not in {"removed", "absent"} or route(address=address) != "absent":
            raise ProbeError("exact_route_cleanup_failed")
        browser.require_login_origin()
        browser.fill('form.verification-card input[name="code"]', code)
        browser.click('form.verification-card button[type="submit"]')
        completed, request_id = browser.response(lambda path: bool(VERIFICATION_DONE.fullmatch(path)), timeout=40)
        if completed != 200:
            raise ProbeError(f"verification_completion_http_{completed}")
        if browser.response_body(request_id).get("verification_state") != "verified":
            raise ProbeError("contact_not_verified")
        print("contact_verified; close browser and delete private MIME/object")
    finally:
        original = sys.exc_info()[1]
        cleanup_errors = []
        try:
            if browser:
                browser.close()
        except Exception:
            cleanup_errors.append("browser_teardown_failed")
        # A browser teardown failure must never skip exact-route cleanup.
        # 即使浏览器关闭失败，也绝不可跳过精确路由清理。
        try:
            if route(address=address) == "enabled":
                if route("--remove", address) not in {"removed", "absent"} or route(address=address) != "absent":
                    cleanup_errors.append("exact_route_cleanup_failed")
        except Exception:
            cleanup_errors.append("exact_route_cleanup_failed")
        if cleanup_errors:
            if isinstance(original, ProbeError):
                cleanup_errors.insert(0, str(original))
            raise ProbeError("+".join(cleanup_errors))


def first_line(process: subprocess.Popen[str], timeout: float = 40) -> tuple[str, queue.Queue[str]]:
    """Capture one CLI authorization URL only in memory. / 仅在内存捕获一条 CLI 授权 URL。"""

    lines: queue.Queue[str] = queue.Queue(maxsize=8)

    def reader() -> None:
        """Transfer bounded CLI output to a private in-memory queue. / 将有界 CLI 输出移入私有内存队列。"""

        assert process.stdout is not None
        for line in process.stdout:
            if len(line) > 8192:
                lines.put("__oversize__")
                break
            lines.put(line)

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    try:
        line = lines.get(timeout=timeout).strip()
    except queue.Empty:
        raise ProbeError("cli_authorization_url_timeout") from None
    if line == "__oversize__":
        raise ProbeError("cli_authorization_url_oversize")
    return line, lines


def cli_json(binary: Path, environment: dict[str, str], *args: str) -> dict:
    """Read one compact CLI JSON response without echoing it. / 读取紧凑 CLI JSON 而不回显。"""

    result = subprocess.run(
        [str(binary), *args], env=environment, capture_output=True, text=True, timeout=60, check=False
    )
    if result.returncode:
        raise ProbeError("cli_post_login_command_failed")
    try:
        value = json.loads(result.stdout.strip())
    except ValueError:
        raise ProbeError("cli_post_login_json_invalid") from None
    if not isinstance(value, dict):
        raise ProbeError("cli_post_login_json_invalid")
    return value


def valid_authorization_url(value: str) -> bool:
    """Validate the sensitive native request in memory without returning its fields.

    中文：仅在内存检查敏感原生授权请求，不返回其中字段。
    """

    try:
        parsed = urlsplit(value)
        query = parse_qs(parsed.query)
        redirect_values = query.get("redirect_uri", [])
        if len(redirect_values) != 1:
            return False
        redirect = urlsplit(redirect_values[0])
        proof = re.compile(r"[A-Za-z0-9_-]{43,128}")
        return (
            f"{parsed.scheme}://{parsed.netloc}" == ISSUER
            and query.get("client_id") == [CLIENT]
            and query.get("response_type") == ["code"]
            and query.get("code_challenge_method") == ["S256"]
            and all(len(query.get(name, [])) == 1 and proof.fullmatch(query[name][0])
                    for name in ("state", "nonce", "code_challenge"))
            and len(query.get("scope", [])) == 1
            and sorted(query["scope"][0].split()) == ["offline_access", "openid", "profile"]
            and redirect.scheme == "http"
            and redirect.hostname == "127.0.0.1"
            and redirect.path == "/callback"
            and bool(redirect.port)
            and not (redirect.query or redirect.fragment or redirect.username or redirect.password)
        )
    except ValueError:
        return False


def native_login(run_dir: Path, binary: Path, expected_address: str | None = None) -> None:
    """Run actual native PKCE in a fresh browser and cross-process CLI session.

    中文：在全新浏览器内完成真实原生 PKCE，并跨进程检验 CLI 会话。
    """

    username, password, address = load_credential(run_dir)
    if expected_address is not None and address != expected_address:
        raise ProbeError("login_contact_does_not_match_encrypted_run")
    attempt = secrets.token_hex(8)
    home = run_dir / f"amail-home-{attempt}"
    home.mkdir(parents=True, exist_ok=False)
    environment = browser_environment()
    environment.update({
        "AMAIL_HOME": str(home),
        "AMAIL_ISSUER": ISSUER,
        "AMAIL_CLIENT_ID": CLIENT,
        "AMAIL_API_BASE": MAIL_API,
        "AMAIL_REDIRECT_URI": "http://127.0.0.1/callback",
        "AMAIL_TELEMETRY": "off",
    })
    config = cli_json(binary, environment, "config")
    if any(config.get(key) != value for key, value in {
        "issuer": ISSUER, "client_id": CLIENT, "api_base": MAIL_API,
        "redirect_uri": "http://127.0.0.1/callback", "telemetry_enabled": False,
    }.items()):
        raise ProbeError("cli_staging_coordinates_mismatch")
    process = subprocess.Popen(
        [str(binary), "auth", "login", "--no-browser"],
        env=environment, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, text=True, bufsize=1,
    )
    browser: Browser | None = None
    try:
        auth_url, lines = first_line(process)
        if not valid_authorization_url(auth_url):
            raise ProbeError("cli_authorization_request_mismatch")
        browser = Browser(run_dir / f"authorization-browser-{attempt}")
        browser.navigate(auth_url)
        browser.wait_dom('input[name="login"]', timeout=60)
        browser.require_login_origin()
        browser.fill('input[name="login"]', username)
        browser.fill('input[name="password"]', password)
        browser.click('form.auth-form button[type="submit"]')
        if process.wait(timeout=250) != 0:
            raise ProbeError("cli_native_login_failed")
        try:
            final = lines.get(timeout=5).strip()
        except queue.Empty:
            raise ProbeError("cli_final_response_missing") from None
        try:
            authenticated = json.loads(final).get("authenticated")
        except (ValueError, AttributeError):
            authenticated = False
        if authenticated is not True:
            raise ProbeError("cli_native_login_not_authenticated")
        if cli_json(binary, environment, "auth", "status").get("authenticated") is not True:
            raise ProbeError("cli_cross_process_auth_missing")
        # Address list may legitimately print no JSONL when the account owns no addresses.
        # 新账户没有地址时，address list 可以合法地不输出 JSONL。
        result = subprocess.run(
            [str(binary), "address", "list"], env=environment, capture_output=True,
            text=True, timeout=45, check=False,
        )
        if result.returncode:
            raise ProbeError("staging_mail_resource_auth_failed")
        print("native_pkce_login_and_mail_resource_authorization_passed")
    finally:
        teardown_failed = False
        try:
            if browser:
                browser.close()
        except Exception:
            teardown_failed = True
        # Always stop the loopback CLI, even when Chrome teardown fails.
        # 即使 Chrome 关闭失败，也必须停止回环监听中的 CLI。
        try:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
        except Exception:
            teardown_failed = True
        if teardown_failed:
            raise ProbeError("native_process_teardown_failed")


def main() -> int:
    """Require explicit staging confirmation and emit only safe stage labels.

    中文：必须显式确认预发布环境，且仅输出安全阶段标签。
    """

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["register", "login"])
    parser.add_argument("--confirm-staging", action="store_true")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--amail")
    parser.add_argument("--address", help="registered staging contact; checked against encrypted run on login")
    args = parser.parse_args()
    if not args.confirm_staging:
        print("staging_confirmation_required", file=sys.stderr)
        return 2
    try:
        run_dir = under_temp(args.run_dir)
        run_dir.mkdir(parents=True, exist_ok=True)
        if args.phase == "register":
            registration(run_dir, args.address or ALIAS)
        else:
            if not args.amail:
                raise ProbeError("ci_built_amail_required")
            binary = under_temp(args.amail)
            if not binary.is_file():
                raise ProbeError("ci_built_amail_missing")
            native_login(run_dir, binary, args.address)
    except ProbeError as error:
        print(str(error), file=sys.stderr)
        return 1
    except (OSError, ValueError, subprocess.TimeoutExpired):
        print("staging_identity_probe_failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
