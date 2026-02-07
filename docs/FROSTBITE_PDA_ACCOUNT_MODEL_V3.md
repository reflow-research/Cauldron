# Frostbite Deterministic Seeded Account Model (v3)

Status: Active
Date: 2026-02-07
Applies to: Frostbite on-chain program, Cauldron CLI, Cauldron Rust tools

This document keeps the legacy filename for continuity, but the current model is
seeded deterministic accounts (`create_with_seed`), not `find_program_address`
PDA allocation.

## Goals

1. Deterministic, per-authority VM and segment addresses.
2. No per-account keypair management for users.
3. Strong authority ownership and close/drain lifecycle controls.
4. Stable segment slot mapping for multi-user safety.

## Address Derivation

Addresses are derived with `create_with_seed(authority, seed, program_id)`.

Seed strings:

```text
VM seed string:
  "fbv1:vm:<vm_seed_hex16>"

Segment seed string:
  "fbv1:sg:<vm_seed_hex16>:<kind_hex2><slot_hex2>"
```

Where:

- `vm_seed_hex16` is zero-padded lowercase hex for `u64 vm_seed`.
- `kind` is `1` (`weights`) or `2` (`ram`).
- `slot` is `1..15`.

## Segment Rules

- Slot `1`: weights segment (readonly in execute mapping).
- Slots `2..15`: RAM segments (writable in execute mapping).
- Mapped execution requires contiguous slots starting at `1`.

## Segment Data Layout

```text
0..4   magic       = "RVCD"
4..8   payload_len = u32 LE
8..12  reserved    = 0
12..   payload bytes
```

Total account size: `12 + payload_len` bytes.

## Current Opcode Assignments

```text
40 = INIT_VM_SEEDED
41 = INIT_SEGMENT_SEEDED
42 = LOAD_PROGRAM_V3
43 = EXECUTE_V3
44 = RESET_V3
45 = WRITE_SEGMENT_SEEDED
46 = CLEAR_SEGMENT_SEEDED
47 = CLOSE_SEGMENT_SEEDED
48 = CLOSE_VM_SEEDED
49 = EXECUTE_RESTART_V3
```

Legacy opcodes remain for backward compatibility, but new Cauldron flows default
to seeded v3 operations.

### Execute Modes

- `EXECUTE_RESTART_V3` (`49`): fresh runtime restart. Resets VM runtime state,
  sets PC to entry, then executes with seeded segment checks. This is the
  Cauldron default for seeded account files.
- `EXECUTE_V3` (`43`): resume mode. Continues from existing runtime state.
  Use only when persistent execution state is intentional.

## Authority Model

- The authority signer determines derivation namespace.
- VM and segments are bound to `(authority, vm_seed)`.
- Mutating and closing seeded accounts requires the same authority domain.
- If payer and authority differ, Cauldron requires explicit
  `vm.authority_keypair` (or matching signer overrides).

## Cauldron Operational Mapping

Cauldron account file:

```toml
[vm]
seed = 1234567890123456789
account_model = "seeded"
authority_keypair = "~/.config/solana/id.json"

[[segments]]
index = 1
slot = 1
kind = "weights"
writable = false
bytes = 60

[[segments]]
index = 2
slot = 2
kind = "ram"
writable = true
bytes = 262144
```

Lifecycle commands:

```bash
cauldron accounts create --accounts frostbite-accounts.toml
cauldron accounts clear --accounts frostbite-accounts.toml --kind ram --slot 2 --offset 0 --length 0
cauldron accounts close-segment --accounts frostbite-accounts.toml --kind ram --slot 2
cauldron accounts close-segment --accounts frostbite-accounts.toml --kind weights --slot 1
cauldron accounts close-vm --accounts frostbite-accounts.toml
```

## Notes

- `cauldron invoke` auto-disables temporary RAM creation when mapped writable
  segments are already present.
- Default fallback temporary RAM size is `256 KiB` per segment when implicit RAM
  creation is enabled.
- For JS/TOML workflows, quote large seeds to avoid precision loss in toolchains
  that use IEEE-754 numbers.
