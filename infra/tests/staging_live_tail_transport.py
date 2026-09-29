"""Owner-only, bounded Cloudflare Tail transport for the offline staging observer.

This module is deliberately not a CLI or CI step. Opening a filtered stream is
not authorization to create an address, and Cloudflare does not acknowledge
effective filter application. The only result is the observer's fixed label.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import ipaddress
import json
import logging
import re
import time
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from staging_live_tail_observer import (
    MAX_FRAME_BYTES, MAX_FRAMES, MAX_SECONDS, MAX_TOTAL_BYTES, TailObserver, WORKER,
)


API = "https://api.cloudflare.com/client/v4/accounts"
MAX_API_BYTES = 4096
HEX32 = re.compile(r"[0-9a-f]{32}\Z")
TAIL_ID = re.compile(r"[A-Za-z0-9_-]{1,32}\Z")
FILTER = {"filters": [{"method": ["POST"]}]}


class TailTransportError(Exception):
    """A fixed, content-free transport failure code."""


def _json_request(url: str, token: str, method: str, body: dict | None = None) -> dict:
    """Call the fixed Cloudflare API path with a small response cap and no logs."""

    data = None if body is None else json.dumps(body, separators=(",", ":")).encode()
    request = Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json",
    })
    try:
        with urlopen(request, timeout=10) as response:
            raw = response.read(MAX_API_BYTES + 1)
        if len(raw) > MAX_API_BYTES:
            raise TailTransportError("api_response_limit")
        value = json.loads(raw)
        if not isinstance(value, dict) or value.get("success") is not True:
            raise TailTransportError("api_response_unverified")
        return value
    except TailTransportError:
        raise
    except Exception from None:
        raise TailTransportError("api_request_failed") from None


def _tail_record(value: dict) -> tuple[str, str, datetime]:
    """Validate an opaque session without allowing an arbitrary URL scheme."""

    result = value.get("result")
    if not isinstance(result, dict):
        raise TailTransportError("tail_record_unverified")
    tail_id, url, expiry = result.get("id"), result.get("url"), result.get("expires_at")
    if not isinstance(tail_id, str) or TAIL_ID.fullmatch(tail_id) is None:
        raise TailTransportError("tail_record_unverified")
    if not isinstance(url, str) or len(url) > 2048:
        raise TailTransportError("tail_record_unverified")
    try:
        parsed = urlsplit(url)
        hostname = parsed.hostname
        try:
            ipaddress.ip_address(hostname or "")
            public_name = False
        except ValueError:
            public_name = bool(hostname and "." in hostname and not hostname.endswith(".local"))
        valid_url = (parsed.scheme == "wss" and bool(parsed.hostname)
                     and public_name
                     and not parsed.username and not parsed.password
                     and not parsed.fragment and parsed.port in (None, 443))
    except ValueError:
        valid_url = False
    if not valid_url:
        raise TailTransportError("tail_record_unverified")
    try:
        expires_at = datetime.fromisoformat(str(expiry).replace("Z", "+00:00"))
    except ValueError from None:
        raise TailTransportError("tail_record_unverified") from None
    if expires_at.tzinfo is None or expires_at <= datetime.now(timezone.utc):
        raise TailTransportError("tail_record_unverified")
    return tail_id, url, expires_at


class TailSession:
    """Capture one Tail session, retaining only validated observer projections.

    Use ``async with``; the caller owns isolation, privacy preflight, the
    authorized CLI operation, and exact CLI-derived request ID. ``open`` only
    proves a WebSocket connection, not provider filter effectiveness or E2E
    readiness. ``finish`` must follow the CLI's exact-route cleanup readback.
    """

    def __init__(self, account_id: str, token: str, *, connect_socket=None) -> None:
        """Restrict the session to one staging Worker and a valid account ID."""

        if HEX32.fullmatch(account_id) is None or not token:
            raise TailTransportError("credentials_unverified")
        self._endpoint = f"{API}/{account_id}/workers/scripts/{WORKER}/tails"
        self._token = token
        self._connect_socket = connect_socket
        self._observer = TailObserver()
        self._tail_id: str | None = None
        self._socket = None
        self._reader: asyncio.Task | None = None
        self._expiry: datetime | None = None
        self._deadline = time.monotonic() + MAX_SECONDS
        self._closed = False
        self._result: str | None = None
        logger = logging.getLogger("amail.staging.tail.transport")
        logger.addHandler(logging.NullHandler())
        logger.propagate = False
        self._logger = logger

    async def __aenter__(self) -> TailSession:
        """Create the exact POST-filtered Tail and connect with bounded frames."""

        try:
            if self._connect_socket is None:
                from websockets.asyncio.client import connect
            else:
                connect = self._connect_socket
            created = await asyncio.to_thread(
                _json_request, self._endpoint, self._token, "POST", FILTER,
            )
            self._tail_id, url, self._expiry = _tail_record(created)
            self._socket = await connect(
                url, subprotocols=["trace-v1"], compression=None, proxy=False,
                open_timeout=10, close_timeout=3, ping_interval=10, ping_timeout=10,
                max_size=MAX_FRAME_BYTES, max_queue=1, logger=self._logger,
            )
            if self._socket.subprotocol != "trace-v1":
                raise TailTransportError("transport_unverified")
            self._observer.connected()
            self._reader = asyncio.create_task(self._read())
            return self
        except Exception:
            await self._close()
            raise TailTransportError("transport_unverified") from None

    async def _read(self) -> None:
        """Discard every raw frame immediately after the offline parser sees it."""

        frames = 0
        total_bytes = 0
        try:
            while True:
                if (self._expiry is None or datetime.now(timezone.utc) >= self._expiry
                        or time.monotonic() >= self._deadline):
                    self._observer.lost()
                    return
                # Idle is not loss, but the parser's hard wall-clock limit is.
                try:
                    frame = await asyncio.wait_for(self._socket.recv(), timeout=10)
                except TimeoutError:
                    continue
                if not isinstance(frame, str):
                    self._observer.lost()
                    return
                raw = frame.encode("utf-8")
                if len(raw) > MAX_FRAME_BYTES:
                    self._observer.lost()
                    return
                frames += 1
                total_bytes += len(raw)
                if frames > MAX_FRAMES or total_bytes > MAX_TOTAL_BYTES:
                    self._observer.lost()
                    return
                self._observer.feed(raw)
        except asyncio.CancelledError:
            raise
        except Exception:
            self._observer.lost()

    async def finish(self, expected_request_id: str) -> str:
        """Return a fixed observed-chain label only after confirmed Tail deletion."""

        if self._result is not None:
            return self._result
        # A short bounded delivery grace is not a guarantee against silent loss.
        await asyncio.sleep(1)
        deleted = await self._close()
        self._result = self._observer.finish(
            clean_end=deleted, expected_request_id=expected_request_id,
        ) if deleted else "UNVERIFIED (transport_cleanup_failed)"
        return self._result

    async def _close(self) -> bool:
        """Cancel the receiver, close the socket, then delete the exact session."""

        if self._closed:
            return self._tail_id is None
        self._closed = True
        if self._reader is not None:
            self._reader.cancel()
            try:
                await self._reader
            except asyncio.CancelledError:
                pass
        if self._socket is not None:
            try:
                await asyncio.wait_for(self._socket.close(), timeout=5)
            except Exception:
                self._observer.lost()
        if self._tail_id is None:
            return True
        try:
            await asyncio.to_thread(
                _json_request, f"{self._endpoint}/{self._tail_id}", self._token, "DELETE",
            )
            self._tail_id = None
            return True
        except Exception:
            return False

    async def __aexit__(self, _type, _value, _traceback) -> None:
        """Always attempt server-side deletion even when the caller fails."""

        if self._result is None:
            self._observer.lost()
        await self._close()
