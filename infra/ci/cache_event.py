"""Report real cache lookup results without confusing step success with a hit."""

import argparse
import json
import os

CACHES = ("cli-dependencies", "worker-dependencies", "worker-bundler")


def event(cache: str, hit: str) -> dict:
    """False may include partial dependency restoration, not necessarily a cold run."""
    if cache not in CACHES:
        raise ValueError("unknown_cache")
    return {"event": "ci_cache_lookup", "cache": cache,
            "lookup": {"true": "exact_hit", "false": "non_exact_or_miss"}.get(hit, "unreported")}


def main() -> None:
    """Emit public operation metadata to JSONL and the human GitHub job summary."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cache", choices=CACHES)
    value = event(parser.parse_args().cache, os.getenv("CI_CACHE_HIT", ""))
    print(json.dumps(value, sort_keys=True))
    path = os.getenv("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as summary:
            summary.write(f"- Cache `{value['cache']}`: **{value['lookup']}**.\n")


if __name__ == "__main__":
    main()
