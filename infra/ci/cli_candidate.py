"""Package hosted native CLI candidates without publishing a tag or release.

Run ``binary`` after release-mode native tests/build, upload its output per runner,
then download those same-run artifacts and run ``assemble``. The bundle is review
material, not publication admission. Source/run metadata contains no credentials.
"""

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / ".temp/ci/cli-candidate"
TARGETS = ("x86_64-unknown-linux-gnu", "x86_64-pc-windows-msvc", "aarch64-apple-darwin")


def context() -> dict:
    """Bind review bytes to one hosted source SHA, run, attempt and compiler."""
    sha, run, attempt = (os.getenv(key, "") for key in
                         ("GITHUB_SHA", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"))
    if (os.getenv("GITHUB_ACTIONS") != "true" or not re.fullmatch(r"[0-9a-f]{40}", sha)
            or not re.fullmatch(r"[1-9][0-9]{0,19}", run)
            or not re.fullmatch(r"[1-9][0-9]{0,4}", attempt)):
        raise ValueError("hosted_candidate_context_required")
    with (ROOT / "crates/amail/Cargo.toml").open("rb") as file:
        version = tomllib.load(file)["package"]["version"]
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
        raise ValueError("candidate_version_invalid")
    with (ROOT / "rust-toolchain.toml").open("rb") as file:
        compiler = tomllib.load(file)["toolchain"]["channel"]
    return {"schema": "amail-cli-candidate/v1", "version": version,
            "source_sha": sha, "run_id": run, "run_attempt": int(attempt),
            "rust": compiler, "publication": "unpublished-candidate"}


def digest(path: Path) -> str:
    """Hash an ordinary bounded file without following a symlink."""
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 256 * 1024 * 1024:
        raise ValueError(f"candidate_file_invalid: {path.name}")
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def write_json(path: Path, value: dict) -> None:
    """Write deterministic public metadata beside the review archives."""
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def archive_name(version: str, target: str) -> str:
    """Keep candidate names visibly distinct from public release archives."""
    extension = "zip" if "windows" in target else "tar.gz"
    return f"amail-v{version}-candidate-{target}.{extension}"


def candidate_readme(version: str) -> str:
    """Prepend isolated acceptance instructions without changing public README bytes."""
    return f"""# amail v{version} — unpublished staging candidate

This archive is for staging acceptance, not a Release. **The binary still defaults
to production for backward compatibility.** Use a separate shell and dedicated
staging home before login or any mailbox operation; do not reuse a production home.

From the directory where you keep this acceptance task, configure staging:

```sh
export AMAIL_HOME=\"$PWD/.temp/amail-staging-acceptance\"
export AMAIL_API_BASE=https://mail-staging.moesegfault.dev
export AMAIL_ISSUER=https://identity-staging.moesegfault.dev
export AMAIL_CLIENT_ID=amail-cli-staging
./amail config
./amail discover
```

Windows PowerShell:

```powershell
$env:AMAIL_HOME = Join-Path $PWD '.temp/amail-staging-acceptance'
$env:AMAIL_API_BASE = 'https://mail-staging.moesegfault.dev'
$env:AMAIL_ISSUER = 'https://identity-staging.moesegfault.dev'
$env:AMAIL_CLIENT_ID = 'amail-cli-staging'
.\\amail.exe config
.\\amail.exe discover
```

Keep the registered default loopback redirect `http://127.0.0.1/callback`; do not
substitute a production client or remote redirect. Inspect `config` before login:
the API, issuer, client and dedicated home must all be the staging values above.
Staging Identity is a separate realm: a production account/session does not prove
staging authorization. Use only an authorized staging identity and owned fixtures.
No token or password belongs in these commands, task notes or public logs.

Automatic semantic indexing sends mail subject/body text to OpenRouter and upstream
model providers even when `--semantic` is never used. There is no per-account off
switch. Read the [staging privacy boundary](https://amail-staging.moesegfault.dev/manual/#隐私与边界)
before creating an address; use nonsensitive synthetic content for acceptance.
Staging testing does not authorize general sending or change a global send hold.

Verify this bundle's `SHA256SUMS` and `candidate.json` before use. The product
reference below retains stable defaults/links; it is not an instruction to point
this staging acceptance task at production.

---

""" + (ROOT / "README.md").read_text(encoding="utf-8")


def binary() -> None:
    """Archive the actual native release binary and its public license/manual."""
    info = context()
    compiler = subprocess.check_output(["rustc", "-vV"], text=True)
    target = next(line.removeprefix("host: ") for line in compiler.splitlines()
                  if line.startswith("host: "))
    if target not in TARGETS:
        raise ValueError(f"candidate_host_unsupported: {target}")
    executable = "amail.exe" if "windows" in target else "amail"
    source = ROOT / "target/release" / executable
    inputs = [(source, executable), (ROOT / "README.md", "README.md"),
              (ROOT / "LICENSE", "LICENSE")]
    for path, _ in inputs:
        digest(path)
    version = subprocess.check_output([str(source), "--version"], text=True).strip()
    if version != f"amail {info['version']}":
        raise ValueError("candidate_binary_version_mismatch")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    archive = OUTPUT / archive_name(info["version"], target)
    if "windows" in target:
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
            for path, name in inputs:
                if name == "README.md":
                    bundle.writestr(name, candidate_readme(info["version"]))
                else:
                    bundle.write(path, name)
    else:
        with tarfile.open(archive, "w:gz") as bundle:
            for path, name in inputs:
                if name == "README.md":
                    content = candidate_readme(info["version"]).encode("utf-8")
                    entry = tarfile.TarInfo(name)
                    entry.size = len(content)
                    entry.mode = 0o644
                    bundle.addfile(entry, io.BytesIO(content))
                else:
                    bundle.add(path, arcname=name, recursive=False)
    write_json(OUTPUT / f"{target}.json", {**info, "target": target,
               "archive": archive.name, "sha256": digest(archive)})


def assemble() -> None:
    """Verify all three same-run producers, then add skill and bundle checksums."""
    info = context()
    expected = set()
    for target in TARGETS:
        metadata = OUTPUT / f"{target}.json"
        digest(metadata)
        producer = json.loads(metadata.read_text(encoding="utf-8"))
        archive = OUTPUT / archive_name(info["version"], target)
        if producer != {**info, "target": target, "archive": archive.name,
                        "sha256": digest(archive)}:
            raise ValueError(f"candidate_producer_mismatch: {target}")
        expected.update((metadata.name, archive.name))
    if {path.name for path in OUTPUT.iterdir()} != expected:
        raise ValueError("candidate_file_set_mismatch")
    skill = OUTPUT / f"amail-agent-skill-v{info['version']}-candidate.zip"
    paths = sorted((ROOT / "skills/amail").rglob("*"))
    if not (ROOT / "skills/amail/SKILL.md").is_file():
        raise ValueError("candidate_skill_missing")
    with zipfile.ZipFile(skill, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in paths:
            if path.is_symlink():
                raise ValueError("candidate_skill_symlink_refused")
            if path.is_file():
                digest(path)
                bundle.write(path, path.relative_to(ROOT / "skills").as_posix())
    write_json(OUTPUT / "candidate.json", {**info, "targets": list(TARGETS),
               "files": {path.name: digest(path) for path in sorted(OUTPUT.iterdir())}})
    checksums = "".join(f"{digest(path)}  {path.name}\n" for path in sorted(OUTPUT.iterdir()))
    (OUTPUT / "SHA256SUMS").write_text(checksums, encoding="utf-8")


def main() -> None:
    """Select the producer or assembly stage; no provider operations are present."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("binary", "assemble"))
    args = parser.parse_args()
    {"binary": binary, "assemble": assemble}[args.stage]()


if __name__ == "__main__":
    main()
