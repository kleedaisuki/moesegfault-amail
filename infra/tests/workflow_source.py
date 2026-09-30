"""Extract source-contract jobs using the repository's block-style YAML layout.

This is intentionally not a general YAML parser: workflow jobs use plain job
identifiers at two-space indentation under a single top-level ``jobs`` mapping.
Keeping raw source preserves expression, shell-order and secret assertions.
"""

import re


def jobs(source: str) -> dict[str, str]:
    """Return isolated job bodies, rejecting absent or duplicate safety keys.

    A body ends at the next sibling job, not a caller-selected later job. A
    subsequent top-level mapping also ends the jobs section. Nested step names
    and shell text cannot become siblings at their deeper indentation. Unsupported
    shallow layout fails closed rather than absorbing an unrecognized sibling.
    """
    source = source.replace("\r\n", "\n")
    sections = list(re.finditer(r"^jobs:[ \t]*$", source, re.MULTILINE))
    if len(sections) != 1:
        raise ValueError("workflow jobs mapping missing or duplicated")
    body = source[sections[0].end():]
    end = re.search(r"^[A-Za-z_][A-Za-z0-9_-]*:", body, re.MULTILINE)
    if end:
        body = body[:end.start()]
    for line in body.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        if line[indent:].startswith("\t") or indent in (0, 1, 3):
            raise ValueError("workflow job indentation unsupported")
        if indent == 2 and not re.fullmatch(
            r"  [A-Za-z_][A-Za-z0-9_-]*:[ \t]*(?:#.*)?", line
        ):
            raise ValueError("workflow job must use a plain block mapping key")
    starts = list(re.finditer(r"^  ([A-Za-z_][A-Za-z0-9_-]*):([^\n]*)$", body, re.MULTILINE))
    result = {}
    for index, item in enumerate(starts):
        name = item.group(1)
        suffix = item.group(2).strip()
        if suffix and not suffix.startswith("#"):
            raise ValueError("workflow job must use a block mapping")
        if name in result:
            raise ValueError("workflow job duplicated")
        stop = starts[index + 1].start() if index + 1 < len(starts) else len(body)
        result[name] = body[item.end():stop].lstrip("\n")
    return result


def job_block(source: str, target: str) -> str:
    """Return exactly one named job body; missing jobs fail the contract test."""
    try:
        return jobs(source)[target]
    except KeyError:
        raise ValueError("workflow safety job missing") from None
