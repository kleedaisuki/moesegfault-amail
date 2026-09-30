"""Run real AES-GCM manifest integration on hosted CI with pinned PyCA cryptography.

Missing or mismatched dependency fails, never skips. No live account, provider,
mail, local token store or filesystem is used. Run explicitly after installing
infra/tests/ten_address_requirements.txt on a GitHub runner.
"""

import importlib.metadata
import unittest

import staging_ten_address_manifest as target
from test_staging_ten_address_manifest import KEY, RUN, GEN, plan


class RealCryptoTests(unittest.TestCase):
    """Exercise actual encrypted manifest interoperability and tamper boundaries."""

    def setUp(self):
        """A missing/mismatched pinned provider is a test failure, not a skip."""
        self.assertEqual(importlib.metadata.version("cryptography"), "50.0.1")

    def test_private_roundtrip_and_exact_artifact_readback(self):
        """Actual ciphertext roundtrips without exposing username/owner/addresses."""
        value = plan()
        blob = target.seal(value, KEY, RUN, GEN)
        self.assertEqual(target.artifact_readback(blob, blob, "123", KEY, RUN, GEN), value)
        for private in (value["owner_sub"], value["provenance"]["verified_username"],
                        *value["allowed"]):
            self.assertNotIn(private.encode(), blob)
        self.assertNotEqual(blob, target.seal(value, KEY, RUN, GEN))

    def test_real_cipher_roundtrip_through_bounded_sqlite_escrow(self):
        """Verify real AEAD survives insert/seal/readback/arm without provider calls."""
        from staging_ten_address_escrow import Escrow
        from test_staging_ten_address_escrow import Database
        database = Database()
        try:
            blob = target.seal(plan(), KEY, RUN, GEN)
            client = Escrow("a" * 32, "synthetic-token", query=database.query)
            client.put(blob, KEY, RUN, GEN)
            client.attach(RUN, KEY, GEN, "123", blob)
            client.arm(RUN, KEY, GEN, "123", blob)
            self.assertEqual(client.read(RUN, KEY, GEN)[1], blob)
            payload = repr(database.calls)
            self.assertNotIn(KEY, payload)
            self.assertNotIn(plan()["provenance"]["verified_username"], payload)
        finally:
            database.db.close()

    def test_nonce_ciphertext_and_tag_tamper_are_rejected(self):
        """All authenticated cryptographic envelope boundaries fail closed."""
        blob = target.seal(plan(), KEY, RUN, GEN)
        for index in (len(b"AMAIL-TEN-V2\x00"), len(b"AMAIL-TEN-V2\x00") + 12, len(blob) - 1):
            changed = bytearray(blob)
            changed[index] ^= 1
            with self.assertRaisesRegex(target.ContractFailure, "manifest_authentication_failed"):
                target.open_manifest(bytes(changed), KEY, RUN, GEN)

    def test_wrong_root_key_run_and_generation_are_rejected(self):
        """Repository/run/key-generation associated data cannot be relabeled."""
        blob = target.seal(plan(), KEY, RUN, GEN)
        for key, run, generation in (("cd" * 32, RUN, GEN), (KEY, "7654321", GEN),
                                     (KEY, RUN, "another-generation")):
            with self.assertRaisesRegex(target.ContractFailure, "manifest_authentication_failed"):
                target.open_manifest(blob, key, run, generation)


if __name__ == "__main__":
    unittest.main()
