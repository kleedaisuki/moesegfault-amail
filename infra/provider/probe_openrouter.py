"""Probe the production embedding contract with synthetic non-private text.

中文：在 GitHub Actions 中远程验证 Qwen 8B 的 256 维输出，不记录密钥或向量。
English: Verify Qwen 8B's 256-dimensional output in CI without logging secrets or vectors.
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
MODEL = "qwen/qwen3-embedding-8b"
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


def main() -> int:
    """发送合成探针并只报告结构性结果。 / Probe with synthetic text and report structure only."""

    token = os.environ.get("OPENROUTER_API_KEY", "")
    if not token:
        print("OPENROUTER_API_KEY is required", file=sys.stderr)
        return 2
    body = json.dumps({
        "model": MODEL,
        "input": SYNTHETIC_INPUT,
        "dimensions": DIMENSIONS,
        "encoding_format": "float",
        "input_type": "search_query",
        "provider": {"zdr": True, "data_collection": "deny"},
    }).encode()
    request = urllib.request.Request(
        URL,
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://amail.moesegfault.dev/",
            "X-Title": "amail deployment probe",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            payload = json.load(response)
        validate(payload)
    except urllib.error.HTTPError as error:
        print(f"OpenRouter embedding probe failed with HTTP {error.code}", file=sys.stderr)
        return 1
    except (urllib.error.URLError, TimeoutError, ValueError, KeyError, TypeError) as error:
        print(f"OpenRouter embedding probe failed: {type(error).__name__}: {error}", file=sys.stderr)
        return 1
    print(f"OpenRouter {MODEL} returned one finite {DIMENSIONS}-dimensional embedding")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
