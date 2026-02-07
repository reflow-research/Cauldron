import argparse
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

from cauldron.accounts import Segment
from cauldron.cli import (
    _accounts_segment_metas,
    _apply_accounts_env,
    _cmd_accounts_clear,
    _cmd_accounts_close_segment,
    _cmd_accounts_close_vm,
    _cmd_accounts_init,
    _cmd_invoke,
    _cmd_upload,
    _cmd_accounts_show,
    _resolve_accounts_path,
)


class CliPdaHardeningTests(unittest.TestCase):
    def _make_accounts_init_args(self, **overrides: object) -> argparse.Namespace:
        base = {
            "manifest": None,
            "out": None,
            "rpc_url": None,
            "program_id": None,
            "payer": None,
            "pda": False,
            "legacy_accounts": False,
            "vm_seed": None,
            "authority": None,
            "authority_keypair": None,
            "vm": None,
            "vm_keypair": None,
            "vm_file": None,
            "weights": None,
            "weights_keypair": None,
            "ram": None,
            "ram_keypair": None,
            "ram_file": None,
            "ram_count": None,
            "ram_bytes": None,
        }
        base.update(overrides)
        return argparse.Namespace(**base)

    def _make_upload_args(self, **overrides: object) -> argparse.Namespace:
        base = {
            "file": None,
            "all": None,
            "cluster": None,
            "rpc_url": None,
            "payer": None,
            "program_id": None,
            "accounts": None,
            "allow_raw_upload": False,
            "extra_args": None,
        }
        base.update(overrides)
        return argparse.Namespace(**base)

    def test_upload_rejects_source_json_without_override(self) -> None:
        args = self._make_upload_args(file="weights.json")
        with patch("cauldron.cli._build_upload_env", return_value={"FROSTBITE_PROGRAM_ID": "Prog"}), patch(
            "cauldron.cli.upload_model_chunk"
        ) as upload_mock:
            with self.assertRaisesRegex(ValueError, "upload expects a binary payload"):
                _cmd_upload(args)
        upload_mock.assert_not_called()

    def test_upload_allows_source_json_with_override(self) -> None:
        args = self._make_upload_args(file="weights.json", allow_raw_upload=True)
        with patch("cauldron.cli._build_upload_env", return_value={"FROSTBITE_PROGRAM_ID": "Prog"}), patch(
            "cauldron.cli.upload_model_chunk", return_value=0
        ) as upload_mock:
            rc = _cmd_upload(args)
        self.assertEqual(rc, 0)
        upload_mock.assert_called_once()

    def test_upload_all_rejects_source_pattern_without_override(self) -> None:
        args = self._make_upload_args(all="chunks/*.json")
        with patch("cauldron.cli._build_upload_env", return_value={"FROSTBITE_PROGRAM_ID": "Prog"}), patch(
            "cauldron.cli.upload_all_chunks"
        ) as upload_mock:
            with self.assertRaisesRegex(ValueError, "source-format files"):
                _cmd_upload(args)
        upload_mock.assert_not_called()

    def test_resolve_accounts_path_expands_tilde(self) -> None:
        resolved = _resolve_accounts_path("/tmp/project/frostbite-accounts.toml", "~/.config/solana/id.json")
        self.assertEqual(resolved, str(Path("~/.config/solana/id.json").expanduser()))

    def test_resolve_accounts_path_relative(self) -> None:
        resolved = _resolve_accounts_path("/tmp/project/frostbite-accounts.toml", "keys/auth.json")
        self.assertEqual(resolved, "/tmp/project/keys/auth.json")

    def test_accounts_init_pda_rejects_ram_overflow(self) -> None:
        args = self._make_accounts_init_args(pda=True, vm_seed=123, ram_count=20)
        with patch("cauldron.cli._load_solana_cli_config", return_value={}):
            with self.assertRaises(ValueError):
                _cmd_accounts_init(args)

    def test_accounts_init_pda_rejects_total_ram_overflow_mixed(self) -> None:
        args = self._make_accounts_init_args(
            pda=True,
            vm_seed=123,
            ram=["A"] * 10,
            ram_keypair=["K"] * 3,
            ram_count=2,
        )
        with patch("cauldron.cli._load_solana_cli_config", return_value={}):
            with self.assertRaises(ValueError):
                _cmd_accounts_init(args)

    def test_accounts_init_defaults_to_seeded_mode(self) -> None:
        args = self._make_accounts_init_args()
        with tempfile.TemporaryDirectory() as td:
            out_path = Path(td) / "frostbite-accounts.toml"
            args.out = str(out_path)
            with patch("cauldron.cli._load_solana_cli_config", return_value={}), patch(
                "cauldron.cli.secrets.randbits", return_value=42
            ):
                rc = _cmd_accounts_init(args)
            self.assertEqual(rc, 0)
            text = out_path.read_text()
            self.assertIn("account_model = \"seeded\"", text)
            self.assertIn("seed = 42", text)
            self.assertNotIn("pubkey = \"REPLACE_ME\"", text)

    def test_accounts_init_legacy_override_uses_placeholder_accounts(self) -> None:
        args = self._make_accounts_init_args(legacy_accounts=True, ram_count=1)
        with tempfile.TemporaryDirectory() as td:
            out_path = Path(td) / "frostbite-accounts.toml"
            args.out = str(out_path)
            with patch("cauldron.cli._load_solana_cli_config", return_value={}):
                rc = _cmd_accounts_init(args)
            self.assertEqual(rc, 0)
            text = out_path.read_text()
            self.assertNotIn("account_model = \"seeded\"", text)
            self.assertNotIn("seed =", text)
            self.assertIn("pubkey = \"REPLACE_ME\"", text)

    def test_accounts_init_rejects_conflicting_seeded_and_legacy_flags(self) -> None:
        args = self._make_accounts_init_args(pda=True, legacy_accounts=True)
        with patch("cauldron.cli._load_solana_cli_config", return_value={}):
            with self.assertRaisesRegex(ValueError, "mutually exclusive"):
                _cmd_accounts_init(args)

    def test_accounts_init_rejects_seed_specific_fields_in_legacy_mode(self) -> None:
        args = self._make_accounts_init_args(legacy_accounts=True, vm_seed=7)
        with patch("cauldron.cli._load_solana_cli_config", return_value={}):
            with self.assertRaisesRegex(ValueError, "--vm-seed is only valid"):
                _cmd_accounts_init(args)

    def test_apply_accounts_env_rejects_authority_without_signer(self) -> None:
        accounts = {
            "cluster": {"program_id": "Prog1111111111111111111111111111111111111"},
            "vm": {"seed": 99, "authority": "Auth111111111111111111111111111111111111"},
            "segments": [],
        }
        weights_segment = Segment(
            index=1,
            slot=1,
            kind="weights",
            pubkey=None,
            keypair=None,
            writable=False,
            bytes=None,
        )
        with patch("cauldron.cli.load_accounts", return_value=accounts), \
             patch("cauldron.cli.parse_segments", return_value=[weights_segment]), \
             patch("cauldron.cli.resolve_authority_pubkey", return_value="Auth111111111111111111111111111111111111"), \
             patch("cauldron.cli.resolve_pubkey", return_value="Payer11111111111111111111111111111111111"), \
             patch("cauldron.cli.derive_vm_pda", return_value="VmPda1111111111111111111111111111111111"), \
             patch("cauldron.cli.derive_segment_pda", return_value="SegPda111111111111111111111111111111111"):
            with self.assertRaisesRegex(ValueError, "authority differs from payer signer"):
                _apply_accounts_env(
                    {
                        "FROSTBITE_PROGRAM_ID": "Prog1111111111111111111111111111111111111",
                        "FROSTBITE_PAYER_KEYPAIR": "/tmp/payer.json",
                    },
                    "/tmp/project/frostbite-accounts.toml",
                    require_weights_keypair=True,
                )

    def test_apply_accounts_env_sets_authority_keypair_for_pda(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            accounts_path = Path(td) / "frostbite-accounts.toml"
            accounts = {
                "cluster": {"program_id": "Prog1111111111111111111111111111111111111"},
                "vm": {"seed": 7, "authority_keypair": "keys/auth.json"},
                "segments": [],
            }
            weights_segment = Segment(
                index=1,
                slot=1,
                kind="weights",
                pubkey=None,
                keypair=None,
                writable=False,
                bytes=None,
            )
            with patch("cauldron.cli.load_accounts", return_value=accounts), \
                 patch("cauldron.cli.parse_segments", return_value=[weights_segment]), \
                 patch("cauldron.cli.resolve_authority_pubkey", return_value="Auth111111111111111111111111111111111111"), \
                 patch("cauldron.cli.derive_vm_pda", return_value="VmPda1111111111111111111111111111111111"), \
                 patch("cauldron.cli.derive_segment_pda", return_value="SegPda111111111111111111111111111111111"):
                env = _apply_accounts_env(
                    {"FROSTBITE_PAYER_KEYPAIR": "/tmp/payer.json"},
                    str(accounts_path),
                    require_weights_keypair=True,
                )
            self.assertEqual(env["FROSTBITE_UPLOAD_MODE"], "pda")
            self.assertEqual(env["FROSTBITE_AUTHORITY_PUBKEY"], "Auth111111111111111111111111111111111111")
            self.assertTrue(env["FROSTBITE_AUTHORITY_KEYPAIR"].endswith("keys/auth.json"))

    def test_apply_accounts_env_accepts_legacy_env_override(self) -> None:
        accounts = {
            "cluster": {"program_id": "Prog1111111111111111111111111111111111111"},
            "vm": {},
            "segments": [],
        }
        weights_segment = Segment(
            index=1,
            slot=1,
            kind="weights",
            pubkey=None,
            keypair=None,
            writable=False,
            bytes=None,
        )
        with patch("cauldron.cli.load_accounts", return_value=accounts), patch(
            "cauldron.cli.parse_segments", return_value=[weights_segment]
        ):
            env = _apply_accounts_env(
                {
                    "FROSTBITE_PROGRAM_ID": "Prog1111111111111111111111111111111111111",
                    "FROSTBITE_CHUNK_KEYPAIR": "/tmp/weights.json",
                },
                "/tmp/project/frostbite-accounts.toml",
                require_weights_keypair=True,
            )
        self.assertEqual(env["FROSTBITE_CHUNK_KEYPAIR"], "/tmp/weights.json")

    def test_apply_accounts_env_rejects_legacy_override_when_vm_seed_present(self) -> None:
        accounts = {
            "cluster": {"program_id": "Prog1111111111111111111111111111111111111"},
            "vm": {"seed": 7, "authority": "Auth111111111111111111111111111111111111"},
            "segments": [],
        }
        weights_segment = Segment(
            index=1,
            slot=1,
            kind="weights",
            pubkey=None,
            keypair=None,
            writable=False,
            bytes=None,
        )
        with patch("cauldron.cli.load_accounts", return_value=accounts), patch(
            "cauldron.cli.parse_segments", return_value=[weights_segment]
        ):
            with self.assertRaisesRegex(ValueError, "vm.seed enables PDA mode"):
                _apply_accounts_env(
                    {
                        "FROSTBITE_PROGRAM_ID": "Prog1111111111111111111111111111111111111",
                        "FROSTBITE_CHUNK_KEYPAIR": "/tmp/weights.json",
                    },
                    "/tmp/project/frostbite-accounts.toml",
                    require_weights_keypair=True,
                )

    def test_apply_accounts_env_rejects_weights_keypair_when_vm_seed_present(self) -> None:
        accounts = {
            "cluster": {"program_id": "Prog1111111111111111111111111111111111111"},
            "vm": {"seed": 7, "authority": "Auth111111111111111111111111111111111111"},
            "segments": [],
        }
        weights_segment = Segment(
            index=1,
            slot=1,
            kind="weights",
            pubkey=None,
            keypair="keys/weights.json",
            writable=False,
            bytes=None,
        )
        with patch("cauldron.cli.load_accounts", return_value=accounts), patch(
            "cauldron.cli.parse_segments", return_value=[weights_segment]
        ):
            with self.assertRaisesRegex(ValueError, "remove weights segment keypair"):
                _apply_accounts_env(
                    {"FROSTBITE_PROGRAM_ID": "Prog1111111111111111111111111111111111111"},
                    "/tmp/project/frostbite-accounts.toml",
                    require_weights_keypair=True,
                )

    def test_apply_accounts_env_preserves_explicit_legacy_override_over_accounts_keypair(self) -> None:
        accounts = {
            "cluster": {"program_id": "Prog1111111111111111111111111111111111111"},
            "vm": {},
            "segments": [],
        }
        weights_segment = Segment(
            index=1,
            slot=1,
            kind="weights",
            pubkey=None,
            keypair="keys/weights.json",
            writable=False,
            bytes=None,
        )
        with patch("cauldron.cli.load_accounts", return_value=accounts), patch(
            "cauldron.cli.parse_segments", return_value=[weights_segment]
        ):
            env = _apply_accounts_env(
                {
                    "FROSTBITE_PROGRAM_ID": "Prog1111111111111111111111111111111111111",
                    "FROSTBITE_CHUNK_KEYPAIR": "/tmp/override.json",
                },
                "/tmp/project/frostbite-accounts.toml",
                require_weights_keypair=True,
            )
        self.assertEqual(env["FROSTBITE_CHUNK_KEYPAIR"], "/tmp/override.json")

    def test_apply_accounts_env_rejects_vm_authority_binding_mismatch(self) -> None:
        accounts = {
            "cluster": {"program_id": "Prog1111111111111111111111111111111111111"},
            "vm": {
                "authority": "Auth111111111111111111111111111111111111",
                "authority_keypair": "keys/auth.json",
            },
            "segments": [],
        }
        with patch("cauldron.cli.load_accounts", return_value=accounts), patch(
            "cauldron.cli.resolve_pubkey", return_value="Other11111111111111111111111111111111111"
        ):
            with self.assertRaisesRegex(ValueError, "vm.authority does not match vm.authority_keypair"):
                _apply_accounts_env(
                    {"FROSTBITE_PROGRAM_ID": "Prog1111111111111111111111111111111111111"},
                    "/tmp/project/frostbite-accounts.toml",
                    require_weights_keypair=False,
                )

    def test_apply_accounts_env_rejects_missing_weights_segment_when_required(self) -> None:
        accounts = {
            "cluster": {"program_id": "Prog1111111111111111111111111111111111111"},
            "vm": {},
            "segments": [],
        }
        with patch("cauldron.cli.load_accounts", return_value=accounts), patch(
            "cauldron.cli.parse_segments", return_value=[]
        ):
            with self.assertRaisesRegex(ValueError, "missing weights segment"):
                _apply_accounts_env(
                    {"FROSTBITE_PROGRAM_ID": "Prog1111111111111111111111111111111111111"},
                    "/tmp/project/frostbite-accounts.toml",
                    require_weights_keypair=True,
                )

    def test_apply_accounts_env_rejects_weights_slot_not_one_in_pda_mode(self) -> None:
        accounts = {
            "cluster": {"program_id": "Prog1111111111111111111111111111111111111"},
            "vm": {"seed": 99, "authority": "Auth111111111111111111111111111111111111"},
            "segments": [],
        }
        weights_segment = Segment(
            index=1,
            slot=2,
            kind="weights",
            pubkey=None,
            keypair=None,
            writable=False,
            bytes=None,
        )
        with patch("cauldron.cli.load_accounts", return_value=accounts), \
             patch("cauldron.cli.parse_segments", return_value=[weights_segment]), \
             patch("cauldron.cli.resolve_authority_pubkey", return_value="Auth111111111111111111111111111111111111"), \
             patch("cauldron.cli.resolve_pubkey", return_value="Auth111111111111111111111111111111111111"):
            with self.assertRaisesRegex(ValueError, "weights segment at slot 1"):
                _apply_accounts_env(
                    {
                        "FROSTBITE_PROGRAM_ID": "Prog1111111111111111111111111111111111111",
                        "FROSTBITE_PAYER_KEYPAIR": "/tmp/payer.json",
                    },
                    "/tmp/project/frostbite-accounts.toml",
                    require_weights_keypair=True,
                )

    def test_apply_accounts_env_rejects_seeded_vm_pubkey_mismatch(self) -> None:
        accounts = {
            "cluster": {"program_id": "Prog1111111111111111111111111111111111111"},
            "vm": {
                "seed": 99,
                "authority": "Auth111111111111111111111111111111111111",
                "pubkey": "VmManual111111111111111111111111111111111",
            },
            "segments": [],
        }
        weights_segment = Segment(
            index=1,
            slot=1,
            kind="weights",
            pubkey=None,
            keypair=None,
            writable=False,
            bytes=None,
        )
        with patch("cauldron.cli.load_accounts", return_value=accounts), \
             patch("cauldron.cli.parse_segments", return_value=[weights_segment]), \
             patch("cauldron.cli.resolve_authority_pubkey", return_value="Auth111111111111111111111111111111111111"), \
             patch("cauldron.cli.derive_vm_pda", return_value="VmDerived11111111111111111111111111111111"), \
             patch("cauldron.cli.derive_segment_pda", return_value="SegDerived11111111111111111111111111111111"):
            with self.assertRaisesRegex(ValueError, "vm.pubkey does not match derived VM PDA"):
                _apply_accounts_env(
                    {"FROSTBITE_PROGRAM_ID": "Prog1111111111111111111111111111111111111"},
                    "/tmp/project/frostbite-accounts.toml",
                    require_weights_keypair=True,
                )

    def test_apply_accounts_env_rejects_seeded_weights_pubkey_mismatch(self) -> None:
        accounts = {
            "cluster": {"program_id": "Prog1111111111111111111111111111111111111"},
            "vm": {"seed": 99, "authority": "Auth111111111111111111111111111111111111"},
            "segments": [],
        }
        weights_segment = Segment(
            index=1,
            slot=1,
            kind="weights",
            pubkey="SegManual11111111111111111111111111111111",
            keypair=None,
            writable=False,
            bytes=None,
        )
        with patch("cauldron.cli.load_accounts", return_value=accounts), \
             patch("cauldron.cli.parse_segments", return_value=[weights_segment]), \
             patch("cauldron.cli.resolve_authority_pubkey", return_value="Auth111111111111111111111111111111111111"), \
             patch("cauldron.cli.derive_vm_pda", return_value="VmDerived11111111111111111111111111111111"), \
             patch("cauldron.cli.derive_segment_pda", return_value="SegDerived11111111111111111111111111111111"):
            with self.assertRaisesRegex(ValueError, "weights segment pubkey does not match derived PDA"):
                _apply_accounts_env(
                    {"FROSTBITE_PROGRAM_ID": "Prog1111111111111111111111111111111111111"},
                    "/tmp/project/frostbite-accounts.toml",
                    require_weights_keypair=True,
                )

    def test_accounts_segment_metas_rejects_seeded_vm_pubkey_mismatch(self) -> None:
        accounts = {
            "cluster": {"program_id": "Prog1111111111111111111111111111111111111"},
            "vm": {
                "seed": 7,
                "authority": "Auth111111111111111111111111111111111111",
                "pubkey": "VmManual111111111111111111111111111111111",
            },
            "segments": [],
        }
        segment = Segment(
            index=1,
            slot=1,
            kind="weights",
            pubkey="SegDerived11111111111111111111111111111111",
            keypair=None,
            writable=False,
            bytes=None,
        )
        with patch("cauldron.cli.load_accounts", return_value=accounts), \
             patch("cauldron.cli.parse_segments", return_value=[segment]), \
             patch("cauldron.cli.resolve_authority_pubkey", return_value="Auth111111111111111111111111111111111111"), \
             patch("cauldron.cli.derive_vm_pda", return_value="VmDerived11111111111111111111111111111111"):
            with self.assertRaisesRegex(ValueError, "vm.pubkey does not match derived VM PDA"):
                _accounts_segment_metas("/tmp/project/frostbite-accounts.toml")

    def test_accounts_segment_metas_rejects_seeded_segment_pubkey_mismatch(self) -> None:
        accounts = {
            "cluster": {"program_id": "Prog1111111111111111111111111111111111111"},
            "vm": {"seed": 7, "authority": "Auth111111111111111111111111111111111111"},
            "segments": [],
        }
        segment = Segment(
            index=1,
            slot=1,
            kind="weights",
            pubkey="SegManual11111111111111111111111111111111",
            keypair=None,
            writable=False,
            bytes=None,
        )
        with patch("cauldron.cli.load_accounts", return_value=accounts), \
             patch("cauldron.cli.parse_segments", return_value=[segment]), \
             patch("cauldron.cli.resolve_authority_pubkey", return_value="Auth111111111111111111111111111111111111"), \
             patch("cauldron.cli.derive_vm_pda", return_value="VmDerived11111111111111111111111111111111"), \
             patch("cauldron.cli.derive_segment_pda", return_value="SegDerived11111111111111111111111111111111"):
            with self.assertRaisesRegex(ValueError, "segment 1 pubkey does not match derived PDA"):
                _accounts_segment_metas("/tmp/project/frostbite-accounts.toml")

    def test_accounts_segment_metas_orders_seeded_segments_by_slot(self) -> None:
        accounts = {
            "cluster": {"program_id": "Prog1111111111111111111111111111111111111"},
            "vm": {"seed": 7, "authority": "Auth111111111111111111111111111111111111"},
            "segments": [],
        }
        segments = [
            Segment(
                index=10,
                slot=2,
                kind="ram",
                pubkey=None,
                keypair=None,
                writable=True,
                bytes=None,
            ),
            Segment(
                index=1,
                slot=1,
                kind="weights",
                pubkey=None,
                keypair=None,
                writable=False,
                bytes=None,
            ),
        ]

        def _derive_segment(
            _program_id: str,
            _authority: str,
            _vm_seed: int,
            _kind: int,
            slot: int,
        ) -> str:
            if slot == 1:
                return "SegSlot11111111111111111111111111111111111"
            if slot == 2:
                return "SegSlot22222222222222222222222222222222222"
            raise AssertionError(f"unexpected slot {slot}")

        with patch("cauldron.cli.load_accounts", return_value=accounts), \
             patch("cauldron.cli.parse_segments", return_value=segments), \
             patch("cauldron.cli.resolve_authority_pubkey", return_value="Auth111111111111111111111111111111111111"), \
             patch("cauldron.cli.derive_vm_pda", return_value="VmDerived11111111111111111111111111111111"), \
             patch("cauldron.cli.derive_segment_pda", side_effect=_derive_segment):
            info, mapped = _accounts_segment_metas("/tmp/project/frostbite-accounts.toml")

        self.assertEqual(info["vm_seed"], "7")
        self.assertEqual(
            mapped,
            [
                "ro:SegSlot11111111111111111111111111111111111",
                "rw:SegSlot22222222222222222222222222222222222",
            ],
        )

    def test_accounts_segment_metas_rejects_non_contiguous_seeded_slots(self) -> None:
        accounts = {
            "cluster": {"program_id": "Prog1111111111111111111111111111111111111"},
            "vm": {"seed": 7, "authority": "Auth111111111111111111111111111111111111"},
            "segments": [],
        }
        segments = [
            Segment(
                index=1,
                slot=1,
                kind="weights",
                pubkey=None,
                keypair=None,
                writable=False,
                bytes=None,
            ),
            Segment(
                index=3,
                slot=3,
                kind="ram",
                pubkey=None,
                keypair=None,
                writable=True,
                bytes=None,
            ),
        ]

        def _derive_segment(
            _program_id: str,
            _authority: str,
            _vm_seed: int,
            _kind: int,
            slot: int,
        ) -> str:
            return f"SegSlot{slot}11111111111111111111111111111111111"

        with patch("cauldron.cli.load_accounts", return_value=accounts), \
             patch("cauldron.cli.parse_segments", return_value=segments), \
             patch("cauldron.cli.resolve_authority_pubkey", return_value="Auth111111111111111111111111111111111111"), \
             patch("cauldron.cli.derive_vm_pda", return_value="VmDerived11111111111111111111111111111111"), \
             patch("cauldron.cli.derive_segment_pda", side_effect=_derive_segment):
            with self.assertRaisesRegex(ValueError, "contiguous segment slots starting at 1"):
                _accounts_segment_metas("/tmp/project/frostbite-accounts.toml")

    def test_accounts_segment_metas_rejects_seeded_writable_mismatch(self) -> None:
        accounts = {
            "cluster": {"program_id": "Prog1111111111111111111111111111111111111"},
            "vm": {"seed": 7, "authority": "Auth111111111111111111111111111111111111"},
            "segments": [],
        }
        bad_weights_segment = Segment(
            index=1,
            slot=1,
            kind="weights",
            pubkey=None,
            keypair=None,
            writable=True,
            bytes=None,
        )
        with patch("cauldron.cli.load_accounts", return_value=accounts), \
             patch("cauldron.cli.parse_segments", return_value=[bad_weights_segment]), \
             patch("cauldron.cli.resolve_authority_pubkey", return_value="Auth111111111111111111111111111111111111"), \
             patch("cauldron.cli.derive_vm_pda", return_value="VmDerived11111111111111111111111111111111"), \
             patch("cauldron.cli.derive_segment_pda", return_value="SegDerived11111111111111111111111111111111"):
            with self.assertRaisesRegex(ValueError, "must be readonly in PDA mode"):
                _accounts_segment_metas("/tmp/project/frostbite-accounts.toml")

    def test_accounts_segment_metas_requires_weights_at_slot_one(self) -> None:
        accounts = {
            "cluster": {"program_id": "Prog1111111111111111111111111111111111111"},
            "vm": {"seed": 7, "authority": "Auth111111111111111111111111111111111111"},
            "segments": [],
        }
        bad_slot_one = Segment(
            index=1,
            slot=1,
            kind="ram",
            pubkey=None,
            keypair=None,
            writable=True,
            bytes=None,
        )
        with patch("cauldron.cli.load_accounts", return_value=accounts), \
             patch("cauldron.cli.parse_segments", return_value=[bad_slot_one]), \
             patch("cauldron.cli.resolve_authority_pubkey", return_value="Auth111111111111111111111111111111111111"), \
             patch("cauldron.cli.derive_vm_pda", return_value="VmDerived11111111111111111111111111111111"):
            with self.assertRaisesRegex(ValueError, "weights segment at slot 1"):
                _accounts_segment_metas("/tmp/project/frostbite-accounts.toml")

    def test_accounts_segment_metas_rejects_weights_outside_slot_one(self) -> None:
        accounts = {
            "cluster": {"program_id": "Prog1111111111111111111111111111111111111"},
            "vm": {"seed": 7, "authority": "Auth111111111111111111111111111111111111"},
            "segments": [],
        }
        segments = [
            Segment(
                index=1,
                slot=1,
                kind="weights",
                pubkey=None,
                keypair=None,
                writable=False,
                bytes=None,
            ),
            Segment(
                index=2,
                slot=2,
                kind="weights",
                pubkey=None,
                keypair=None,
                writable=False,
                bytes=None,
            ),
        ]
        with patch("cauldron.cli.load_accounts", return_value=accounts), \
             patch("cauldron.cli.parse_segments", return_value=segments), \
             patch("cauldron.cli.resolve_authority_pubkey", return_value="Auth111111111111111111111111111111111111"), \
             patch("cauldron.cli.derive_vm_pda", return_value="VmDerived11111111111111111111111111111111"), \
             patch("cauldron.cli.derive_segment_pda", return_value="SegDerived11111111111111111111111111111111"):
            with self.assertRaisesRegex(ValueError, "weights only at slot 1"):
                _accounts_segment_metas("/tmp/project/frostbite-accounts.toml")

    def test_accounts_clear_requires_pda_seed(self) -> None:
        args = argparse.Namespace(
            accounts="/tmp/project/frostbite-accounts.toml",
            kind="ram",
            slot=2,
            offset=0,
            length=0,
            rpc_url=None,
            program_id=None,
            payer=None,
        )
        with patch("cauldron.cli._accounts_segment_metas", return_value=({"vm_seed": None}, [])):
            with self.assertRaisesRegex(ValueError, "requires vm.seed"):
                _cmd_accounts_clear(args)

    def test_accounts_clear_rejects_zero_length_with_nonzero_offset(self) -> None:
        args = argparse.Namespace(
            accounts="/tmp/project/frostbite-accounts.toml",
            kind="ram",
            slot=2,
            offset=8,
            length=0,
            rpc_url=None,
            program_id=None,
            payer=None,
        )
        with self.assertRaisesRegex(ValueError, "length=0 requires offset=0"):
            _cmd_accounts_clear(args)

    def test_accounts_clear_invokes_pda_ops_binary(self) -> None:
        args = argparse.Namespace(
            accounts="/tmp/project/frostbite-accounts.toml",
            kind="ram",
            slot=2,
            offset=4,
            length=16,
            rpc_url=None,
            program_id=None,
            payer=None,
        )
        with patch(
            "cauldron.cli._accounts_segment_metas",
            return_value=(
                {
                    "vm_seed": "7",
                    "rpc_url": "https://api.devnet.solana.com",
                    "program_id": "FRsToriMLgDc1Ud53ngzHUZvCRoazCaGeGUuzkwoha7m",
                    "payer": "/tmp/payer.json",
                },
                [],
            ),
        ), patch("cauldron.cli._apply_accounts_env", side_effect=lambda env, *_args, **_kwargs: env), patch(
            "cauldron.cli.subprocess.run", return_value=Mock(returncode=0)
        ) as run_mock:
            rc = _cmd_accounts_clear(args)
        self.assertEqual(rc, 0)
        cmd = run_mock.call_args.kwargs["args"] if "args" in run_mock.call_args.kwargs else run_mock.call_args[0][0]
        self.assertIn("pda_account_ops", cmd)
        self.assertIn("clear-segment", cmd)
        self.assertIn("--vm-seed", cmd)
        self.assertIn("7", cmd)
        self.assertIn("--offset", cmd)
        self.assertIn("4", cmd)
        self.assertIn("--len", cmd)
        self.assertIn("16", cmd)

    def test_accounts_close_segment_invokes_pda_ops_binary(self) -> None:
        args = argparse.Namespace(
            accounts="/tmp/project/frostbite-accounts.toml",
            kind="weights",
            slot=1,
            recipient="Recip1111111111111111111111111111111111111",
            rpc_url=None,
            program_id=None,
            payer=None,
        )
        with patch(
            "cauldron.cli._accounts_segment_metas",
            return_value=(
                {
                    "vm_seed": "9",
                    "rpc_url": "https://api.devnet.solana.com",
                    "program_id": "FRsToriMLgDc1Ud53ngzHUZvCRoazCaGeGUuzkwoha7m",
                    "payer": "/tmp/payer.json",
                },
                [],
            ),
        ), patch("cauldron.cli._apply_accounts_env", side_effect=lambda env, *_args, **_kwargs: env), patch(
            "cauldron.cli.subprocess.run", return_value=Mock(returncode=0)
        ) as run_mock:
            rc = _cmd_accounts_close_segment(args)
        self.assertEqual(rc, 0)
        cmd = run_mock.call_args.kwargs["args"] if "args" in run_mock.call_args.kwargs else run_mock.call_args[0][0]
        self.assertIn("close-segment", cmd)
        self.assertIn("--kind", cmd)
        self.assertIn("weights", cmd)
        self.assertIn("--slot", cmd)
        self.assertIn("1", cmd)
        self.assertIn("--recipient", cmd)

    def test_accounts_close_vm_invokes_pda_ops_binary(self) -> None:
        args = argparse.Namespace(
            accounts="/tmp/project/frostbite-accounts.toml",
            recipient="Recip1111111111111111111111111111111111111",
            rpc_url=None,
            program_id=None,
            payer=None,
        )
        with patch(
            "cauldron.cli._accounts_segment_metas",
            return_value=(
                {
                    "vm_seed": "11",
                    "rpc_url": "https://api.devnet.solana.com",
                    "program_id": "FRsToriMLgDc1Ud53ngzHUZvCRoazCaGeGUuzkwoha7m",
                    "payer": "/tmp/payer.json",
                },
                [],
            ),
        ), patch("cauldron.cli._apply_accounts_env", side_effect=lambda env, *_args, **_kwargs: env), patch(
            "cauldron.cli.subprocess.run", return_value=Mock(returncode=0)
        ) as run_mock:
            rc = _cmd_accounts_close_vm(args)
        self.assertEqual(rc, 0)
        cmd = run_mock.call_args.kwargs["args"] if "args" in run_mock.call_args.kwargs else run_mock.call_args[0][0]
        self.assertIn("close-vm", cmd)
        self.assertIn("--vm-seed", cmd)
        self.assertIn("11", cmd)
        self.assertIn("--recipient", cmd)

    def test_invoke_disables_temp_ram_when_writable_segments_mapped(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            mapped_out = Path(td) / "mapped_accounts.txt"
            args = argparse.Namespace(
                accounts="/tmp/project/frostbite-accounts.toml",
                program_path=None,
                rpc_url=None,
                program_id=None,
                payer=None,
                instructions=50000,
                ram_count=None,
                ram_bytes=None,
                compute_limit=None,
                max_tx=None,
                mapped_out=str(mapped_out),
                fast=False,
                no_simulate=False,
                verbose=False,
            )
            with patch(
                "cauldron.cli._accounts_segment_metas",
                return_value=(
                    {
                        "vm_pubkey": "Vm11111111111111111111111111111111111111111",
                        "rpc_url": "https://api.devnet.solana.com",
                        "program_id": "FRsToriMLgDc1Ud53ngzHUZvCRoazCaGeGUuzkwoha7m",
                        "payer": "/tmp/payer.json",
                    },
                    [
                        "ro:Weight111111111111111111111111111111111111",
                        "rw:Ram111111111111111111111111111111111111111",
                    ],
                ),
            ), patch(
                "cauldron.cli._resolve_run_onchain", return_value="/tmp/frostbite-run-onchain"
            ), patch("cauldron.cli.subprocess.run", return_value=Mock(returncode=0)) as run_mock:
                rc = _cmd_invoke(args)

            self.assertEqual(rc, 0)
            cmd = run_mock.call_args.kwargs["args"] if "args" in run_mock.call_args.kwargs else run_mock.call_args[0][0]
            self.assertIn("--ram-count", cmd)
            self.assertIn("0", cmd)

    def test_invoke_keeps_default_ram_when_only_readonly_segments_mapped(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            mapped_out = Path(td) / "mapped_accounts.txt"
            args = argparse.Namespace(
                accounts="/tmp/project/frostbite-accounts.toml",
                program_path=None,
                rpc_url=None,
                program_id=None,
                payer=None,
                instructions=50000,
                ram_count=None,
                ram_bytes=None,
                compute_limit=None,
                max_tx=None,
                mapped_out=str(mapped_out),
                fast=False,
                no_simulate=False,
                verbose=False,
            )
            with patch(
                "cauldron.cli._accounts_segment_metas",
                return_value=(
                    {
                        "vm_pubkey": "Vm11111111111111111111111111111111111111111",
                        "rpc_url": "https://api.devnet.solana.com",
                        "program_id": "FRsToriMLgDc1Ud53ngzHUZvCRoazCaGeGUuzkwoha7m",
                        "payer": "/tmp/payer.json",
                    },
                    ["ro:Weight111111111111111111111111111111111111"],
                ),
            ), patch(
                "cauldron.cli._resolve_run_onchain", return_value="/tmp/frostbite-run-onchain"
            ), patch("cauldron.cli.subprocess.run", return_value=Mock(returncode=0)) as run_mock:
                rc = _cmd_invoke(args)

            self.assertEqual(rc, 0)
            cmd = run_mock.call_args.kwargs["args"] if "args" in run_mock.call_args.kwargs else run_mock.call_args[0][0]
            self.assertNotIn("--ram-count", cmd)

    def test_invoke_respects_explicit_ram_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            mapped_out = Path(td) / "mapped_accounts.txt"
            args = argparse.Namespace(
                accounts="/tmp/project/frostbite-accounts.toml",
                program_path=None,
                rpc_url=None,
                program_id=None,
                payer=None,
                instructions=50000,
                ram_count=2,
                ram_bytes=131072,
                compute_limit=None,
                max_tx=None,
                mapped_out=str(mapped_out),
                fast=False,
                no_simulate=False,
                verbose=False,
            )
            with patch(
                "cauldron.cli._accounts_segment_metas",
                return_value=(
                    {
                        "vm_pubkey": "Vm11111111111111111111111111111111111111111",
                        "rpc_url": "https://api.devnet.solana.com",
                        "program_id": "FRsToriMLgDc1Ud53ngzHUZvCRoazCaGeGUuzkwoha7m",
                        "payer": "/tmp/payer.json",
                    },
                    [
                        "ro:Weight111111111111111111111111111111111111",
                        "rw:Ram111111111111111111111111111111111111111",
                    ],
                ),
            ), patch(
                "cauldron.cli._resolve_run_onchain", return_value="/tmp/frostbite-run-onchain"
            ), patch("cauldron.cli.subprocess.run", return_value=Mock(returncode=0)) as run_mock:
                rc = _cmd_invoke(args)

            self.assertEqual(rc, 0)
            cmd = run_mock.call_args.kwargs["args"] if "args" in run_mock.call_args.kwargs else run_mock.call_args[0][0]
            ram_count_idx = cmd.index("--ram-count")
            self.assertEqual(cmd[ram_count_idx + 1], "2")
            ram_bytes_idx = cmd.index("--ram-bytes")
            self.assertEqual(cmd[ram_bytes_idx + 1], "131072")

    def test_accounts_show_handles_invalid_vm_seed(self) -> None:
        args = argparse.Namespace(accounts="/tmp/project/frostbite-accounts.toml")
        accounts = {
            "cluster": {"program_id": "Prog1111111111111111111111111111111111111"},
            "vm": {"seed": "not-a-number"},
            "segments": [],
        }
        with patch("cauldron.cli.load_accounts", return_value=accounts), patch(
            "cauldron.cli.parse_segments", return_value=[]
        ):
            with redirect_stdout(io.StringIO()):
                rc = _cmd_accounts_show(args)
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
