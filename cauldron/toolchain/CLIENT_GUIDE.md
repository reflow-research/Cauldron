# Frostbite Client Development Guide

This guide explains how to write Solana clients that interact with the Frostbite VM, including the multi-transaction execution pattern used for long-running programs like LLM inference.

## Overview

The Frostbite VM runs RISC-V programs on Solana. Due to Solana's compute unit (CU) limits (~1.4M per transaction), long-running programs must be executed across multiple transactions.

## Basic Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Your Client    │────▶│  Frostbite      │────▶│   VM Account    │
│  (Rust/JS/etc)  │     │  Program        │     │   (State)       │
└─────────────────┘     └─────────────────┘     └─────────────────┘
        │                       │                       │
        │   Instructions:       │   Executes:           │
        │   - Initialize        │   - RISC-V code       │
        │   - LoadProgram       │   - Syscalls          │
        │   - Execute           │   - State updates     │
        │   - Reset             │                       │
        └───────────────────────┴───────────────────────┘
```

## Instruction Types

| Discriminator | Name | Description |
|---------------|------|-------------|
| 0 | `INITIALIZE` | Create and initialize a new VM |
| 1 | `LOAD_PROGRAM` | Load code into VM memory |
| 2 | `EXECUTE` | Run N instructions |
| 3 | `RESET` | Reset VM state (keep memory) |
| 5 | `WRITE_ACCOUNT` | Write data to VM memory |
| 6 | `COPY_VM_OUTPUT` | Copy output from VM |

## Basic Pattern: Single-Transaction Execution

For small programs that complete within one transaction:

```rust
use frostbite::sdk::instruction::discriminator;

// 1. Create VM account
let create_ix = system_instruction::create_account(...);
let init_ix = Instruction::new_with_bytes(
    program_id,
    &[discriminator::INITIALIZE],
    vec![
        AccountMeta::new(payer.pubkey(), true),
        AccountMeta::new(vm_pubkey, false),
    ],
);

// 2. Load program
let mut load_data = vec![discriminator::LOAD_PROGRAM];
load_data.extend_from_slice(&0u32.to_le_bytes());  // Load at address 0
load_data.extend_from_slice(&program_bytes);
let load_ix = Instruction::new_with_bytes(program_id, &load_data, ...);

// 3. Execute
let cu_ix = ComputeBudgetInstruction::set_compute_unit_limit(1_400_000);
let mut exec_data = vec![discriminator::EXECUTE];
exec_data.extend_from_slice(&max_instructions.to_le_bytes());
let exec_ix = Instruction::new_with_bytes(program_id, &exec_data, ...);

// Send all in one transaction
let tx = Transaction::new_signed_with_payer(
    &[create_ix, init_ix, load_ix, cu_ix, exec_ix],
    ...
);
```

## Multi-Transaction Pattern

For programs that need more instructions than one transaction allows:

```rust
// After creating VM and loading program...

let mut tx_count = 0;
let instructions_per_tx = 50_000;  // Tune based on CU usage

loop {
    tx_count += 1;

    // Build execute instruction
    let cu_ix = ComputeBudgetInstruction::set_compute_unit_limit(1_400_000);
    let mut exec_data = vec![discriminator::EXECUTE];
    exec_data.extend_from_slice(&instructions_per_tx.to_le_bytes());
    let exec_ix = Instruction::new_with_bytes(program_id, &exec_data, accounts.clone());

    // Send transaction
    let tx = Transaction::new_signed_with_payer(&[cu_ix, exec_ix], ...);
    client.send_and_confirm_transaction(&tx)?;

    // Check if VM halted
    let account = client.get_account(&vm_pubkey)?;
    let halted = account.data[offsets::HALTED] != 0;

    if halted {
        println!("Program completed after {} transactions", tx_count);
        break;
    }

    // Optional: Check progress
    let pc = read_u64(&account.data, offsets::PC);
    let instr_count = read_u64(&account.data, offsets::INSTR_COUNT);
    println!("TX {}: PC=0x{:x}, instructions={}", tx_count, pc, instr_count);
}

// Read final exit code
let exit_code = read_u64(&account.data, offsets::EXIT_CODE);
```

## CLI Runner (Stop/Resume Testing)

The `frostbite-run-onchain` binary implements this multi-transaction flow with retries,
preflight simulation, and resume support.

```bash
# Create VM + RAM accounts and save for reuse
frostbite-run-onchain program.elf \
  --ram-count 2 --ram-save frostbite_ram_accounts.txt \
  --vm-save frostbite_vm_accounts.txt

# Resume later (same VM + RAM accounts)
frostbite-run-onchain --vm-file frostbite_vm_accounts.txt \
  --ram-file frostbite_ram_accounts.txt --instructions 50000
```

Use `--max-tx` to intentionally stop early, then resume with `--vm` or `--vm-file`.
By default `frostbite-run-onchain` creates one RAM account; pass `--ram-count 0`
to disable.

## Advanced: Dynamic Instruction Budgeting

For complex programs (like LLM inference), you may want to adjust instructions-per-transaction based on the current execution phase:

```rust
struct ExecutionBudget {
    base_instructions: u64,
    current_instructions: u64,
    consecutive_successes: u64,
}

impl ExecutionBudget {
    fn on_success(&mut self) {
        self.consecutive_successes += 1;
        // Ramp up after consistent successes
        if self.consecutive_successes % 10 == 0 {
            self.current_instructions = (self.current_instructions * 11 / 10)
                .min(self.base_instructions);
        }
    }

    fn on_failure(&mut self) {
        self.consecutive_successes = 0;
        // Back off on failure
        self.current_instructions = (self.current_instructions * 8 / 10)
            .max(1000);
    }
}
```

## Reading VM State

The VM account data layout:

```rust
// State offsets (from frostbite::vm::offsets)
pub const MAGIC: usize = 0;           // 4 bytes: "FBVM"
pub const REGISTERS: usize = 4;       // 256 bytes: x0-x31 (8 bytes each)
pub const PC: usize = 260;            // 8 bytes: Program Counter
pub const HALTED: usize = 268;        // 1 byte: Halted flag
pub const EXIT_CODE: usize = 269;     // 8 bytes: Exit code
pub const INSTR_COUNT: usize = 277;   // 8 bytes: Instructions executed
pub const MEMORY: usize = 285;        // Rest: VM memory (256KB)

// Helper function
fn read_u64(data: &[u8], offset: usize) -> u64 {
    u64::from_le_bytes(data[offset..offset+8].try_into().unwrap())
}

// Read state
let halted = account.data[offsets::HALTED] != 0;
let exit_code = read_u64(&account.data, offsets::EXIT_CODE);
let pc = read_u64(&account.data, offsets::PC);
let instr_count = read_u64(&account.data, offsets::INSTR_COUNT);

// Read register (e.g., a0 = x10)
let a0 = read_u64(&account.data, offsets::REGISTERS + 10 * 8);

// Read VM memory
let memory_start = offsets::MEMORY;
let byte = account.data[memory_start + address];
```

## Mapped Accounts (MMU)

For programs that need more than 256KB of data (like LLM weights), you can map additional Solana accounts as memory segments:

```rust
// Segments 1-15 map to additional accounts
// Address 0x1XXXXXXX = Segment 1, offset XXXXXXX
// Address 0x2XXXXXXX = Segment 2, offset XXXXXXX
// etc.

let exec_accounts = vec![
    AccountMeta::new(payer.pubkey(), true),
    AccountMeta::new(vm_pubkey, false),
    AccountMeta::new(weights_account_1, false),  // Segment 1
    AccountMeta::new(weights_account_2, false),  // Segment 2
    // ... up to 15 additional accounts
];
```

Segments are assigned in the order the accounts are passed. The CLI runner
prints the segment mapping and supports `--ram`, `--ram-file`, and `--ram-save`
to make RAM accounts reusable across runs.

## Transaction Retry Logic

For production use, implement retry logic:

```rust
const MAX_RETRIES: usize = 5;
const RETRY_DELAY_MS: u64 = 100;

fn send_with_retry(
    client: &RpcClient,
    tx: &Transaction,
) -> Result<Signature, Box<dyn Error>> {
    for attempt in 0..MAX_RETRIES {
        match client.send_and_confirm_transaction(tx) {
            Ok(sig) => return Ok(sig),
            Err(e) => {
                if attempt < MAX_RETRIES - 1 {
                    eprintln!("Attempt {} failed: {}, retrying...", attempt + 1, e);
                    std::thread::sleep(Duration::from_millis(
                        RETRY_DELAY_MS * (1 << attempt)
                    ));
                } else {
                    return Err(e.into());
                }
            }
        }
    }
    unreachable!()
}
```

## Complete Example Structure

```rust
fn main() -> Result<(), Box<dyn Error>> {
    // 1. Setup
    let client = RpcClient::new(...);
    let payer = load_keypair()?;
    let program_id = get_program_id()?;

    // 2. Create VM
    let vm_keypair = Keypair::new();
    create_and_init_vm(&client, &payer, &vm_keypair, &program_id)?;

    // 3. Upload program
    upload_program(&client, &payer, &vm_keypair.pubkey(), &program_bytes)?;

    // 4. Execute loop
    let result = execute_until_halt(&client, &payer, &vm_keypair.pubkey())?;

    // 5. Read results
    println!("Exit code: {}", result.exit_code);

    Ok(())
}
```

## Examples

- `examples/simple_client.rs` - Basic single-transaction execution
- `examples/multi_tx_client.rs` - Multi-transaction loop pattern
- `examples/run_inference.rs` - Full LLM inference with dynamic budgeting

## Debugging Tips

1. **Check PC on error**: The final PC value shows where execution stopped
2. **Use RESET**: After errors, reset the VM to try again without recreating
3. **Start small**: Use low instruction counts first, then increase
4. **Monitor CU usage**: Use `solana logs` to see compute unit consumption
5. **Check halted flag**: A program might "complete" without halting (infinite loop)
