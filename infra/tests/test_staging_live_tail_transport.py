"""Synthetic transport tests: no Cloudflare calls or address mutation."""

from __future__ import annotations

import asyncio
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
import io
import unittest
from unittest.mock import patch

from staging_live_tail_transport import FILTER, TailSession, TailTransportError, _tail_record
from test_staging_live_tail_observer import REQUEST, event, frame


ACCOUNT = "a" * 32
TAIL = "b" * 32
SECRET_URL = "wss://tail.example.invalid/private?secret=do-not-print"


def created() -> dict:
    """Return a bounded Cloudflare API success envelope with a secret URL."""

    return {"success": True, "result": {
        "id": TAIL, "url": SECRET_URL,
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=9)).isoformat(),
    }}


class FakeSocket:
    """Keep inbound frames in memory and expose only the expected protocol."""

    subprotocol = "trace-v1"

    def __init__(self) -> None:
        """Start a fake connected Tail socket."""

        self.frames: asyncio.Queue = asyncio.Queue()
        self.closed = False
        self.sent: list[str] = []

    async def send(self, message: str) -> None:
        """Record Wrangler-compatible initial control frames."""

        self.sent.append(message)

    async def recv(self):
        """Block until a synthetic complete WebSocket message arrives."""

        return await self.frames.get()

    async def close(self) -> None:
        """Record deterministic cleanup."""

        self.closed = True


class TailTransportTests(unittest.IsolatedAsyncioTestCase):
    """Assert fixed output, exact filter payload, and reliable deletion."""

    async def test_observed_failure_binds_cli_request_and_deletes(self) -> None:
        """A coherent chain is classified only with the CLI's request ID."""

        socket = FakeSocket()

        async def connect(_url, **kwargs):
            """Inspect bounded stream settings without network access."""

            self.assertEqual(kwargs["max_size"], 65_536)
            self.assertEqual(kwargs["max_queue"], 1)
            self.assertEqual(kwargs["subprotocols"], ["trace-v1"])
            return socket

        calls = []

        def api(url, token, method, body=None):
            """Record only method/filter/cleanup rather than credentials or URL."""

            calls.append((method, body))
            return created() if method == "POST" else {"success": True}

        output = io.StringIO()
        with patch("staging_live_tail_transport._json_request", side_effect=api):
            with redirect_stdout(output), redirect_stderr(output):
                async with TailSession(ACCOUNT, "private-token", connect_socket=connect) as session:
                    socket.frames.put_nowait(frame(
                        event("routing_list", "phase_failure"),
                        event("request_exit", "server_error"),
                    ).decode())
                    label = await session.finish(REQUEST)
        self.assertEqual(label, "routing_list_failed")
        self.assertEqual(calls, [("POST", FILTER), ("DELETE", None)])
        self.assertEqual(socket.sent, ['{"debug":false}'])
        self.assertTrue(socket.closed)
        self.assertEqual(output.getvalue(), "")

    async def test_binary_frame_fails_closed_without_echo(self) -> None:
        """Binary payloads are never decoded or printed as log data."""

        socket = FakeSocket()

        async def connect(_url, **_kwargs):
            """Return the fake socket without network."""

            return socket

        with patch("staging_live_tail_transport._json_request",
                   side_effect=lambda _url, _token, method, _body=None:
                   created() if method == "POST" else {"success": True}):
            async with TailSession(ACCOUNT, "private-token", connect_socket=connect) as session:
                socket.frames.put_nowait(b"private binary payload")
                self.assertEqual(await session.finish(REQUEST), "UNVERIFIED (stream_loss)")

    async def test_delete_failure_overrides_positive_classification(self) -> None:
        """No causal result is published while server-side Tail remains live."""

        socket = FakeSocket()

        async def connect(_url, **_kwargs):
            """Return the fake socket without network."""

            return socket

        def api(_url, _token, method, _body=None):
            """Simulate a private API deletion failure without exposing it."""

            if method == "DELETE":
                raise TailTransportError("private failure")
            return created()

        with patch("staging_live_tail_transport._json_request", side_effect=api):
            async with TailSession(ACCOUNT, "private-token", connect_socket=connect) as session:
                socket.frames.put_nowait(frame(
                    event("routing_list", "phase_failure"),
                    event("request_exit", "server_error"),
                ).decode())
                self.assertEqual(await session.finish(REQUEST),
                                 "UNVERIFIED (transport_cleanup_failed)")

    def test_unsafe_tail_url_is_rejected(self) -> None:
        """Never connect to a downgraded, credential-bearing, or local URL."""

        for url in ("http://example.invalid/", "wss://user:pass@example.invalid/",
                    "wss://example.invalid:444/", "wss://localhost/private",
                    "file:///private"):
            value = created()
            value["result"]["url"] = url
            with self.subTest(url=url), self.assertRaises(TailTransportError):
                _tail_record(value)

    async def test_cancellation_during_close_still_deletes_tail(self) -> None:
        """A cancelled socket close cannot skip the exact server-side DELETE."""

        class SlowClose(FakeSocket):
            """Suspend the first close until the owner task is cancelled."""

            def __init__(self) -> None:
                """Prepare a deterministic close barrier."""

                super().__init__()
                self.started = asyncio.Event()

            async def close(self) -> None:
                """Hold the first close; let a later cleanup complete."""

                self.started.set()
                await asyncio.Event().wait()

        socket = SlowClose()
        calls = []

        async def connect(_url, **_kwargs):
            """Return the fake socket without network."""

            return socket

        def api(_url, _token, method, _body=None):
            """Count control-plane calls without retaining credentials."""

            calls.append(method)
            return created() if method == "POST" else {"success": True}

        with patch("staging_live_tail_transport._json_request", side_effect=api):
            session = TailSession(ACCOUNT, "private-token", connect_socket=connect)
            await session.__aenter__()
            closing = asyncio.create_task(session._close())
            await asyncio.wait_for(socket.started.wait(), timeout=2)
            closing.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await closing
            self.assertEqual(calls, ["POST", "DELETE"])
            self.assertIsNone(session._tail_id)

    async def test_initial_control_frame_failure_deletes_tail(self) -> None:
        """No connected claim is issued if the WebSocket control send fails."""

        class FailedSend(FakeSocket):
            """Fail before the stream can be accepted by the parser."""

            async def send(self, _message: str) -> None:
                """Simulate a transport error without exposing its text."""

                raise RuntimeError("private WebSocket error")

        socket = FailedSend()
        calls = []

        async def connect(_url, **_kwargs):
            """Return the fake socket without network."""

            return socket

        def api(_url, _token, method, _body=None):
            """Count only the control-plane method."""

            calls.append(method)
            return created() if method == "POST" else {"success": True}

        with patch("staging_live_tail_transport._json_request", side_effect=api):
            with self.assertRaises(TailTransportError):
                await TailSession(ACCOUNT, "private-token", connect_socket=connect).__aenter__()
        self.assertEqual(calls, ["POST", "DELETE"])
        self.assertTrue(socket.closed)

