import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from cauldron.accounts import (
    _resolve_pubkey_from_keypair,
    derive_segment_pda,
    derive_vm_pda,
    parse_vm_seed,
    segment_seed_string,
    vm_seed_string,
)


class AccountsPathTests(unittest.TestCase):
    def test_resolve_pubkey_expands_user_path(self) -> None:
        with patch("cauldron.accounts.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="AuthPubkey1111111111111111111111111111111\n",
                stderr="",
            )
            _resolve_pubkey_from_keypair("~/.config/solana/id.json")

        called_cmd = mock_run.call_args.args[0]
        self.assertEqual(called_cmd[0], "solana-keygen")
        self.assertEqual(called_cmd[1], "pubkey")
        self.assertEqual(called_cmd[2], str(Path("~/.config/solana/id.json").expanduser()))

    def test_parse_vm_seed_rejects_out_of_range(self) -> None:
        with self.assertRaises(ValueError):
            parse_vm_seed({"seed": -1})
        with self.assertRaises(ValueError):
            parse_vm_seed({"seed": 2**64})
        with self.assertRaises(ValueError):
            parse_vm_seed({"seed": hex(2**64)})

    def test_vm_seed_string_format(self) -> None:
        self.assertEqual(vm_seed_string(0x0123_4567_89AB_CDEF), "fbv1:vm:0123456789abcdef")

    def test_segment_seed_string_format(self) -> None:
        self.assertEqual(
            segment_seed_string(0x0102_0304_0506_0708, 0xAA, 0x05),
            "fbv1:sg:0102030405060708:aa05",
        )

    def test_derive_vm_pda_uses_seeded_address_cli(self) -> None:
        with patch("cauldron.accounts.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="VmSeeded111111111111111111111111111111111\n",
                stderr="",
            )
            result = derive_vm_pda(
                "Prog1111111111111111111111111111111111111",
                "Auth111111111111111111111111111111111111",
                7,
            )
        self.assertEqual(result, "VmSeeded111111111111111111111111111111111")
        called = mock_run.call_args.args[0]
        self.assertEqual(called[0:2], ["solana", "create-address-with-seed"])
        self.assertIn("--from", called)
        self.assertIn("fbv1:vm:0000000000000007", called)

    def test_derive_segment_pda_uses_seeded_address_cli(self) -> None:
        with patch("cauldron.accounts.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="SegSeeded11111111111111111111111111111111\n",
                stderr="",
            )
            result = derive_segment_pda(
                "Prog1111111111111111111111111111111111111",
                "Auth111111111111111111111111111111111111",
                7,
                1,
                1,
            )
        self.assertEqual(result, "SegSeeded11111111111111111111111111111111")
        called = mock_run.call_args.args[0]
        self.assertEqual(called[0:2], ["solana", "create-address-with-seed"])
        self.assertIn("fbv1:sg:0000000000000007:0101", called)


if __name__ == "__main__":
    unittest.main()
