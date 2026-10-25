"""Probe the production embedding contract with synthetic non-private text.

中文：在 GitHub Actions 中远程验证 Voyage 4 的 256 维输出，不记录密钥或向量。
English: Verify Voyage 4's 256-dimensional output in CI without logging secrets or vectors.
"""

from __future__ import annotations

import json
import math
import os
import sys
import urllib.error
import urllib.request
from typing import Any

URL = "https://openrouter.ai/api/v1/embeddings"
MODEL = "voyageai/voyage-4"
DIMENSIONS = 256
SYNTHETIC_INPUT = "amail deployment probe: find a fictional message about a blue paper kite"


def validate(payload: dict[str, Any]) -> None:
    """要求恰好一个有限且非零的 256 维向量。 / Require one finite nonzero 256D vector."""

    data = payload.get("data")
    if not isinstance(data, list) or len(data) != 1:
        raise ValueError("OpenRouter returned an unexpected number of embeddings")
    embedding = data[0].get("embedding") if isinstance(data[0], dict) else None
    if not isinstance(embedding, list) or len(embedding) != DIMENSIONS:
        length = len(embedding) if isinstance(embedding, list) else "invalid"
        raise ValueError(f"OpenRouter embedding length is {length}, expected {DIMENSIONS}")
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) for value in embedding):
        raise ValueError("OpenRouter returned a non-finite embedding component")
    if not any(value != 0 for value in embedding):
        raise ValueError("OpenRouter returned an all-zero embedding")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Never forward the route key or probe text to a redirected endpoint."""

    def redirect_request(
        self, request: urllib.request.Request, response: Any, code: int,
        message: str, headers: Any, new_url: str,
    ) -> None:
        return None


def probe(token: str, role: str) -> None:
    """Exercise the exact production Voyage float payload for one input role."""
    body = json.dumps({
        "model": MODEL,
        "input": SYNTHETIC_INPUT,
        "dimensions": DIMENSIONS,
        "encoding_format": "float",
        "input_type": role,
        "provider": {"only": ["voyageai"], "allow_fallbacks": False, "data_collection": "deny"},
    }).encode()
    request = urllib.request.Request(
        URL,
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://amail.moesegfault.dev/",
            "X-Title": "amail deployment probe",
            "X-OpenRouter-Cache": "false",
        },
        method="POST",
    )
    with urllib.request.build_opener(NoRedirect()).open(request, timeout=90) as response:
        raw = response.read(64 * 1024 + 1)
    if len(raw) > 64 * 1024:
        raise ValueError("embedding_response_too_large")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("embedding_response_invalid")
    validate(payload)


def main() -> int:
    """Use synthetic input only; never log a provider body, key or vector."""
    token = os.environ.get("OPENROUTER_API_KEY", "")
    if not token:
        print("OPENROUTER_API_KEY is required", file=sys.stderr)
        return 2
    try:
        for role in ("query", "document"):
            probe(token, role)
    except urllib.error.HTTPError as error:
        print(f"OpenRouter embedding probe failed with HTTP {error.code}", file=sys.stderr)
        return 1
    except (urllib.error.URLError, TimeoutError, ValueError, KeyError, TypeError):
        print("OpenRouter embedding probe failed: contract_unverified", file=sys.stderr)
        return 1
    print(f"OpenRouter {MODEL} returned finite {DIMENSIONS}-dimensional query and document embeddings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
