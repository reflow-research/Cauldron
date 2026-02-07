use solana_client::nonblocking::rpc_client::RpcClient;
use solana_sdk::{
    commitment_config::CommitmentConfig,
    instruction::{AccountMeta, Instruction},
    pubkey::Pubkey,
    signature::{Keypair, Signer},
    transaction::Transaction,
};
use std::env;
use std::path::PathBuf;
use std::str::FromStr;
use std::sync::Arc;

const DEFAULT_SOLANA_CONFIG: &str = "~/.config/solana/cli/config.yml";
const DEFAULT_RPC_URL: &str = "http://127.0.0.1:8899";
const DEFAULT_PAYER_KEYPAIR: &str = "~/.config/solana/id.json";
const DEFAULT_PROGRAM_ID: &str = "FRsToriMLgDc1Ud53ngzHUZvCRoazCaGeGUuzkwoha7m";

const OP_CLEAR_SEGMENT_SEEDED: u8 = 46;
const OP_CLOSE_SEGMENT_SEEDED: u8 = 47;
const OP_CLOSE_VM_SEEDED: u8 = 48;

const SEEDED_VM_PREFIX: &str = "fbv1:vm:";
const SEEDED_SEG_PREFIX: &str = "fbv1:sg:";

const SEGMENT_KIND_WEIGHTS: u8 = 1;
const SEGMENT_KIND_RAM: u8 = 2;

enum Command {
    ClearSegment {
        vm_seed: u64,
        kind: u8,
        slot: u8,
        payload_offset: u32,
        clear_len: u32,
    },
    CloseSegment {
        vm_seed: u64,
        kind: u8,
        slot: u8,
        recipient: Pubkey,
    },
    CloseVm {
        vm_seed: u64,
        recipient: Pubkey,
    },
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let solana_config_path =
        env::var("SOLANA_CONFIG").unwrap_or_else(|_| DEFAULT_SOLANA_CONFIG.to_string());
    let cli_config = load_solana_cli_config(&solana_config_path);
    let rpc_url = env::var("FROSTBITE_RPC_URL")
        .ok()
        .or_else(|| cli_config.as_ref().and_then(|cfg| cfg.rpc_url.clone()))
        .unwrap_or_else(|| DEFAULT_RPC_URL.to_string());
    let payer_keypair_path = env::var("FROSTBITE_PAYER_KEYPAIR")
        .ok()
        .or_else(|| cli_config.as_ref().and_then(|cfg| cfg.keypair_path.clone()))
        .unwrap_or_else(|| DEFAULT_PAYER_KEYPAIR.to_string());
    let payer_keypair_path = expand_path(&payer_keypair_path);

    let client = RpcClient::new_with_commitment(rpc_url.clone(), CommitmentConfig::confirmed());
    let payer = Arc::new(
        solana_sdk::signature::read_keypair_file(&payer_keypair_path)
            .map_err(|_| format!("Could not find payer keypair at {}", payer_keypair_path))?,
    );

    let authority_keypair_path = env::var("FROSTBITE_AUTHORITY_KEYPAIR")
        .ok()
        .map(|path| expand_path(&path));
    let authority = if let Some(path) = authority_keypair_path.as_ref() {
        Arc::new(
            solana_sdk::signature::read_keypair_file(path)
                .map_err(|_| format!("Could not find authority keypair at {}", path))?,
        )
    } else {
        payer.clone()
    };
    if let Ok(authority_pubkey_hint) = env::var("FROSTBITE_AUTHORITY_PUBKEY") {
        let hinted = Pubkey::from_str(&authority_pubkey_hint)?;
        if hinted != authority.pubkey() {
            return Err(format!(
                "FROSTBITE_AUTHORITY_PUBKEY mismatch: signer={}, provided={}",
                authority.pubkey(),
                hinted
            )
            .into());
        }
    }

    let command = parse_args(payer.pubkey())?;
    let program_id = detect_program_id()?;

    println!("RPC: {}", rpc_url);
    println!("Program: {}", program_id);
    println!("Payer: {}", payer.pubkey());
    println!("Authority: {}", authority.pubkey());

    let instruction = match command {
        Command::ClearSegment {
            vm_seed,
            kind,
            slot,
            payload_offset,
            clear_len,
        } => {
            let vm_pda = derive_vm_pda(&program_id, &authority.pubkey(), vm_seed)?;
            let segment_pda = derive_segment_pda(&program_id, &authority.pubkey(), vm_seed, kind, slot)?;
            println!(
                "CLEAR_SEGMENT_SEEDED vm_seed={} kind={} slot={} vm={} segment={} offset={} len={}",
                vm_seed,
                kind_name(kind),
                slot,
                vm_pda,
                segment_pda,
                payload_offset,
                clear_len
            );

            let mut data = Vec::with_capacity(1 + 8 + 1 + 1 + 4 + 4);
            data.push(OP_CLEAR_SEGMENT_SEEDED);
            data.extend_from_slice(&vm_seed.to_le_bytes());
            data.push(kind);
            data.push(slot);
            data.extend_from_slice(&payload_offset.to_le_bytes());
            data.extend_from_slice(&clear_len.to_le_bytes());

            Instruction {
                program_id,
                accounts: vec![
                    AccountMeta::new_readonly(authority.pubkey(), true),
                    AccountMeta::new_readonly(vm_pda, false),
                    AccountMeta::new(segment_pda, false),
                ],
                data,
            }
        }
        Command::CloseSegment {
            vm_seed,
            kind,
            slot,
            recipient,
        } => {
            let vm_pda = derive_vm_pda(&program_id, &authority.pubkey(), vm_seed)?;
            let segment_pda = derive_segment_pda(&program_id, &authority.pubkey(), vm_seed, kind, slot)?;
            println!(
                "CLOSE_SEGMENT_SEEDED vm_seed={} kind={} slot={} vm={} segment={} recipient={}",
                vm_seed,
                kind_name(kind),
                slot,
                vm_pda,
                segment_pda,
                recipient
            );

            let mut data = Vec::with_capacity(1 + 8 + 1 + 1);
            data.push(OP_CLOSE_SEGMENT_SEEDED);
            data.extend_from_slice(&vm_seed.to_le_bytes());
            data.push(kind);
            data.push(slot);

            Instruction {
                program_id,
                accounts: vec![
                    AccountMeta::new_readonly(authority.pubkey(), true),
                    AccountMeta::new_readonly(vm_pda, false),
                    AccountMeta::new(segment_pda, false),
                    AccountMeta::new(recipient, false),
                ],
                data,
            }
        }
        Command::CloseVm {
            vm_seed,
            recipient,
        } => {
            let vm_pda = derive_vm_pda(&program_id, &authority.pubkey(), vm_seed)?;
            println!(
                "CLOSE_VM_SEEDED vm_seed={} vm={} recipient={}",
                vm_seed, vm_pda, recipient
            );

            let mut data = Vec::with_capacity(1 + 8);
            data.push(OP_CLOSE_VM_SEEDED);
            data.extend_from_slice(&vm_seed.to_le_bytes());

            Instruction {
                program_id,
                accounts: vec![
                    AccountMeta::new_readonly(authority.pubkey(), true),
                    AccountMeta::new(vm_pda, false),
                    AccountMeta::new(recipient, false),
                ],
                data,
            }
        }
    };

    send_instruction(&client, payer.as_ref(), authority.as_ref(), instruction).await?;
    println!("Success");
    Ok(())
}

fn parse_args(default_recipient: Pubkey) -> Result<Command, Box<dyn std::error::Error>> {
    let args: Vec<String> = env::args().collect();
    if args.len() < 4 {
        eprintln!(
            "Usage:\n  pda_account_ops clear-segment --vm-seed <u64> --kind <weights|ram> --slot <u8> [--offset <u32>] [--len <u32>]\n  pda_account_ops close-segment --vm-seed <u64> --kind <weights|ram> --slot <u8> [--recipient <pubkey>]\n  pda_account_ops close-vm --vm-seed <u64> [--recipient <pubkey>]"
        );
        return Err("missing required args".into());
    }

    let action = args[1].trim().to_ascii_lowercase();
    let mut vm_seed: Option<u64> = None;
    let mut kind: Option<u8> = None;
    let mut slot: Option<u8> = None;
    let mut payload_offset: u32 = 0;
    let mut clear_len: u32 = 0;
    let mut recipient: Pubkey = default_recipient;

    let mut idx = 2usize;
    while idx < args.len() {
        match args[idx].as_str() {
            "--vm-seed" => {
                idx += 1;
                if idx >= args.len() {
                    return Err("missing value for --vm-seed".into());
                }
                vm_seed = Some(parse_u64_value(&args[idx])?);
            }
            "--kind" => {
                idx += 1;
                if idx >= args.len() {
                    return Err("missing value for --kind".into());
                }
                kind = Some(parse_segment_kind(&args[idx])?);
            }
            "--slot" => {
                idx += 1;
                if idx >= args.len() {
                    return Err("missing value for --slot".into());
                }
                let parsed_slot = parse_u64_value(&args[idx])?;
                if !(1..=15).contains(&parsed_slot) {
                    return Err("slot must be in 1..=15".into());
                }
                slot = Some(parsed_slot as u8);
            }
            "--offset" => {
                idx += 1;
                if idx >= args.len() {
                    return Err("missing value for --offset".into());
                }
                let parsed = parse_u64_value(&args[idx])?;
                if parsed > u32::MAX as u64 {
                    return Err("offset exceeds u32::MAX".into());
                }
                payload_offset = parsed as u32;
            }
            "--len" => {
                idx += 1;
                if idx >= args.len() {
                    return Err("missing value for --len".into());
                }
                let parsed = parse_u64_value(&args[idx])?;
                if parsed > u32::MAX as u64 {
                    return Err("len exceeds u32::MAX".into());
                }
                clear_len = parsed as u32;
            }
            "--recipient" => {
                idx += 1;
                if idx >= args.len() {
                    return Err("missing value for --recipient".into());
                }
                recipient = Pubkey::from_str(&args[idx])?;
            }
            other => return Err(format!("unknown argument: {}", other).into()),
        }
        idx += 1;
    }

    let vm_seed = vm_seed.ok_or("missing --vm-seed")?;
    match action.as_str() {
        "clear-segment" => Ok(Command::ClearSegment {
            vm_seed,
            kind: kind.ok_or("missing --kind for clear-segment")?,
            slot: slot.ok_or("missing --slot for clear-segment")?,
            payload_offset,
            clear_len,
        }),
        "close-segment" => Ok(Command::CloseSegment {
            vm_seed,
            kind: kind.ok_or("missing --kind for close-segment")?,
            slot: slot.ok_or("missing --slot for close-segment")?,
            recipient,
        }),
        "close-vm" => Ok(Command::CloseVm { vm_seed, recipient }),
        _ => Err(format!("unknown action '{}'", action).into()),
    }
}

fn parse_segment_kind(raw: &str) -> Result<u8, Box<dyn std::error::Error>> {
    let lowered = raw.trim().to_ascii_lowercase();
    match lowered.as_str() {
        "1" | "weights" => Ok(SEGMENT_KIND_WEIGHTS),
        "2" | "ram" => Ok(SEGMENT_KIND_RAM),
        _ => Err(format!("unsupported segment kind '{}'", raw).into()),
    }
}

fn kind_name(kind: u8) -> &'static str {
    match kind {
        SEGMENT_KIND_WEIGHTS => "weights",
        SEGMENT_KIND_RAM => "ram",
        _ => "unknown",
    }
}

fn parse_u64_value(raw: &str) -> Result<u64, Box<dyn std::error::Error>> {
    let trimmed = raw.trim();
    if trimmed.is_empty() {
        return Err("numeric value cannot be empty".into());
    }
    if let Some(hex) = trimmed
        .strip_prefix("0x")
        .or_else(|| trimmed.strip_prefix("0X"))
    {
        return Ok(u64::from_str_radix(hex, 16)?);
    }
    Ok(trimmed.parse::<u64>()?)
}

fn vm_seed_string(vm_seed: u64) -> String {
    format!("{}{vm_seed:016x}", SEEDED_VM_PREFIX)
}

fn derive_segment_pda(
    program_id: &Pubkey,
    authority: &Pubkey,
    vm_seed: u64,
    kind: u8,
    slot: u8,
) -> Result<Pubkey, Box<dyn std::error::Error>> {
    let seed = segment_seed_string(vm_seed, kind, slot);
    derive_seeded_address(authority, &seed, program_id)
}

fn segment_seed_string(vm_seed: u64, kind: u8, slot: u8) -> String {
    format!("{}{vm_seed:016x}:{kind:02x}{slot:02x}", SEEDED_SEG_PREFIX)
}

fn derive_vm_pda(
    program_id: &Pubkey,
    authority: &Pubkey,
    vm_seed: u64,
) -> Result<Pubkey, Box<dyn std::error::Error>> {
    let seed = vm_seed_string(vm_seed);
    derive_seeded_address(authority, &seed, program_id)
}

fn derive_seeded_address(
    authority: &Pubkey,
    seed: &str,
    program_id: &Pubkey,
) -> Result<Pubkey, Box<dyn std::error::Error>> {
    if seed.len() > 32 {
        return Err(format!("seed exceeds 32 bytes: {}", seed).into());
    }
    Ok(Pubkey::create_with_seed(authority, seed, program_id)?)
}

async fn send_instruction(
    client: &RpcClient,
    fee_payer: &Keypair,
    authority: &Keypair,
    instruction: Instruction,
) -> Result<(), Box<dyn std::error::Error>> {
    let signers = build_signers(fee_payer, authority);
    let tx = Transaction::new_signed_with_payer(
        &[instruction],
        Some(&fee_payer.pubkey()),
        &signers,
        client.get_latest_blockhash().await?,
    );
    client.send_and_confirm_transaction(&tx).await?;
    Ok(())
}

fn build_signers<'a>(fee_payer: &'a Keypair, authority: &'a Keypair) -> Vec<&'a dyn Signer> {
    let mut signers: Vec<&dyn Signer> = vec![fee_payer];
    if authority.pubkey() != fee_payer.pubkey() {
        signers.push(authority);
    }
    signers
}

fn detect_program_id() -> Result<Pubkey, Box<dyn std::error::Error>> {
    if let Ok(id) = env::var("FROSTBITE_PROGRAM_ID") {
        return Ok(Pubkey::from_str(&id)?);
    }
    if let Ok(path) = env::var("FROSTBITE_PROGRAM_KEYPAIR") {
        return Ok(read_program_keypair(&path)?);
    }
    if let Some(path) = find_program_keypair() {
        return Ok(read_program_keypair(path.to_str().unwrap_or_default())?);
    }
    Ok(Pubkey::from_str(DEFAULT_PROGRAM_ID)?)
}

fn read_program_keypair(path: &str) -> Result<Pubkey, Box<dyn std::error::Error>> {
    let data = std::fs::read_to_string(path)?;
    let bytes: Vec<u8> = serde_json::from_str(&data)?;
    let keypair = Keypair::from_bytes(&bytes)?;
    Ok(keypair.pubkey())
}

fn find_program_keypair() -> Option<PathBuf> {
    let mut candidates = Vec::new();
    if let Ok(home) = env::var("FROSTBITE_HOME") {
        candidates.push(PathBuf::from(format!(
            "{}/target/deploy/frostbite-keypair.json",
            home.trim_end_matches('/')
        )));
    }

    if let Ok(cwd) = env::current_dir() {
        for rel in [
            "target/deploy/frostbite-keypair.json",
            "../target/deploy/frostbite-keypair.json",
            "../../target/deploy/frostbite-keypair.json",
            "../../../target/deploy/frostbite-keypair.json",
        ] {
            candidates.push(cwd.join(rel));
        }
    }

    for path in candidates {
        if path.exists() {
            return Some(path);
        }
    }
    None
}

#[derive(Default)]
struct CliConfig {
    rpc_url: Option<String>,
    keypair_path: Option<String>,
}

fn load_solana_cli_config(path: &str) -> Option<CliConfig> {
    let path = expand_path(path);
    let contents = std::fs::read_to_string(&path).ok()?;
    let mut cfg = CliConfig::default();
    for raw_line in contents.lines() {
        let line = raw_line.trim();
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        if let Some(value) = parse_yaml_value(line, "json_rpc_url") {
            cfg.rpc_url = Some(value);
            continue;
        }
        if let Some(value) = parse_yaml_value(line, "keypair_path") {
            cfg.keypair_path = Some(value);
        }
    }
    Some(cfg)
}

fn parse_yaml_value(line: &str, key: &str) -> Option<String> {
    let mut parts = line.splitn(2, ':');
    let left = parts.next()?.trim();
    if left != key {
        return None;
    }
    let value = parts.next()?.trim();
    if value.is_empty() {
        return None;
    }
    Some(value.trim_matches('"').trim_matches('\'').to_string())
}

fn expand_path(path: &str) -> String {
    if let Some(stripped) = path.strip_prefix("~/") {
        if let Ok(home) = std::env::var("HOME") {
            return format!("{}/{}", home, stripped);
        }
    }
    path.to_string()
}
