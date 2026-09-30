# Independent review: hosted real quota recovery cipher

Reviewed commit: `4dd8a38830ead87db425c4e52d67382271d42145`.
Date: 2026-10-01. Verdict: **GO for hosted source CI. No substantive defect
found in this increment.** This is not a live quota/recovery acceptance result.

## Scope and method

Static review of the four-file diff, the existing quota design and manifest
review, manifest fixture imports, `seal`, `open_manifest`, `_cipher` and
`artifact_readback`, and the surrounding Infrastructure probe CI job. Official
PyCA/PyPI release metadata and AEAD documentation were checked. No local test,
dependency installation, build, workflow dispatch, provider request, secret
read or production change was performed.

## Evidence

* `ten_address_requirements.txt` pins the actual PyCA-owned
  `cryptography==50.0.1` release. PyPI lists Python 3.12 support and Linux
  CPython 3.11+ abi3 wheels, including a 4.7 MB manylinux x86-64 wheel. Its
  Trusted Publishing metadata points to `pyca/cryptography` and its release
  publishing workflow. The CI command requires binary distributions, so a
  missing compatible wheel fails instead of starting a Rust/OpenSSL source
  build. This checks published provenance, not runtime wheel attestation or a
  fully hash-locked transitive dependency graph.
* `.github/workflows/ci.yml` installs the two requirement files together once
  in the existing Ubuntu/Python 3.12 Infrastructure job. The explicit
  `python infra/tests/staging_ten_address_crypto_check.py -v` step follows
  installation, has no conditional skip or `continue-on-error`, and precedes
  the unchanged full synthetic discovery suites. The script's deliberately
  non-`test_*` name avoids a second run via ordinary discovery.
* The script's three tests use actual `target._cipher` without mocking it.
  Importing the fixture module does not start its tests or globally patch the
  cipher. Each test requires exact installed package metadata `50.0.1`;
  absence/mismatch fails through unittest rather than skipping. Actual
  roundtrip and exact artifact byte readback, ciphertext privacy against
  synthetic private strings, fresh nonce output, nonce/body/tag tamper and
  wrong root key/run/key-generation associated-data rejection are exercised.
  The implementation uses a 96-bit random nonce, authenticated associated
  data and the PyCA AESGCM API; authentication failure becomes a fixed
  source-owned error code.
* Keys, owner, username, provenance and addresses come only from committed
  synthetic in-memory fixtures. The new step has no Secret environment,
  output artifact, filesystem manifest, HTTP call or campaign mutator.
  Normal unittest failure output could expose synthetic assertion values,
  not live private metadata. No workflow input, job selection condition,
  deployment command or live provider target changes in this diff.
* Full CLI/Worker/site/source CI remains unchanged. The existing branch's
  duplicate-PR suppression and explicit live-target selection are unchanged;
  this increment does not claim the Infrastructure job runs during a
  narrow read-only diagnostic dispatch.

## Limits and next evidence

The version pin is not a claim that 50.0.1 is the newest release: official
changelog lists 50.0.2 (2026-09-30), with wheel OpenSSL and platform updates.
No documented AESGCM API correction was identified there. Ordinary dependency
maintenance can evaluate that update separately; it is not a demonstrated
blocker for this synthetic hosted integration.

Await a green exact-SHA hosted run and its explicit three-test step before
claiming real-cipher integration passed. Artifact upload/download durability,
real account/route quota, cancellation recovery, and the dormant live wrapper
are outside this review and remain independently gated. The nonoccurrence
checks of private plaintext are useful regression tests, not a proof of cipher
security or general leakage freedom.

## References

* [PyCA cryptography 50.0.1 release and wheel provenance](https://pypi.org/project/cryptography/50.0.1/)
* [PyCA AESGCM API and authentication contract](https://cryptography.io/en/latest/hazmat/primitives/aead/#cryptography.hazmat.primitives.ciphers.aead.AESGCM)
* [PyCA release changelog](https://cryptography.io/en/latest/changelog/)
