use solana_client::nonblocking::rpc_client::RpcClient;
use solana_sdk::{
    commitment_config::CommitmentConfig,
    instruction::{AccountMeta, Instruction},
    pubkey::Pubkey,
    signature::{Keypair, Signer},
    system_instruction,
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

const OP_INIT_VM_SEEDED: u8 = 40;
const OP_INIT_SEGMENT_SEEDED: u8 = 41;

const SEEDED_VM_PREFIX: &str = "fbv1:vm:";
const SEEDED_SEG_PREFIX: &str = "fbv1:sg:";

const SEGMENT_KIND_WEIGHTS: u8 = 1;
const SEGMENT_KIND_RAM: u8 = 2;

const VM_MEMORY_SIZE: usize = 262_144;
const VM_MEMORY_OFFSET: usize = 545;
const VM_ACCOUNT_SIZE: usize = VM_MEMORY_OFFSET + VM_MEMORY_SIZE;
const SEGMENT_HEADER_SIZE: usize = 12;

#[derive(Clone, Copy)]
struct SegmentSpec {
    kind: u8,
    slot: u8,
    payload_len: u32,
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let (vm_seed, segments) = parse_args()?;

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
    let program_id = detect_program_id()?;

    let vm_seed_string = vm_seed_string(vm_seed);
    let vm_pubkey = derive_seeded_address(&authority.pubkey(), &vm_seed_string, &program_id)?;

    println!("RPC: {}", rpc_url);
    println!("Program: {}", program_id);
    println!("Payer: {}", payer.pubkey());
    println!("Authority: {}", authority.pubkey());
    if let Some(path) = authority_keypair_path.as_ref() {
        println!("Authority keypair: {}", path);
    }
    println!("Seeded VM: {}", vm_pubkey);

    ensure_seeded_program_account(
        &client,
        payer.as_ref(),
        authority.as_ref(),
        &program_id,
        vm_pubkey,
        &vm_seed_string,
        VM_ACCOUNT_SIZE,
    )
    .await?;

    let mut vm_data = Vec::with_capacity(1 + 8);
    vm_data.push(OP_INIT_VM_SEEDED);
    vm_data.extend_from_slice(&vm_seed.to_le_bytes());
    let vm_ix = Instruction {
        program_id,
        accounts: vec![
            AccountMeta::new_readonly(authority.pubkey(), true),
            AccountMeta::new(vm_pubkey, false),
        ],
        data: vm_data,
    };
    send_instruction(&client, payer.as_ref(), authority.as_ref(), vm_ix).await?;

    let has_segments = !segments.is_empty();
    for segment in segments {
        let segment_seed = segment_seed_string(vm_seed, segment.kind, segment.slot);
        let segment_pubkey =
            derive_seeded_address(&authority.pubkey(), &segment_seed, &program_id)?;
        let payload_len = segment.payload_len as usize;
        let required_space = SEGMENT_HEADER_SIZE
            .checked_add(payload_len)
            .ok_or("segment size overflow")?;

        ensure_seeded_program_account(
            &client,
            payer.as_ref(),
            authority.as_ref(),
            &program_id,
            segment_pubkey,
            &segment_seed,
            required_space,
        )
        .await?;

        let mut seg_data = Vec::with_capacity(1 + 8 + 1 + 1 + 4);
        seg_data.push(OP_INIT_SEGMENT_SEEDED);
        seg_data.extend_from_slice(&vm_seed.to_le_bytes());
        seg_data.push(segment.kind);
        seg_data.push(segment.slot);
        seg_data.extend_from_slice(&segment.payload_len.to_le_bytes());

        let seg_ix = Instruction {
            program_id,
            accounts: vec![
                AccountMeta::new_readonly(authority.pubkey(), true),
                AccountMeta::new_readonly(vm_pubkey, false),
                AccountMeta::new(segment_pubkey, false),
            ],
            data: seg_data,
        };
        send_instruction(&client, payer.as_ref(), authority.as_ref(), seg_ix).await?;

        println!(
            "Seeded segment: kind={} slot={} bytes={} pubkey={}",
            kind_name(segment.kind),
            segment.slot,
            segment.payload_len,
            segment_pubkey
        );
    }

    if !has_segments {
        println!("No segment specs provided; initialized VM seeded account only.");
    }
    Ok(())
}

fn parse_args() -> Result<(u64, Vec<SegmentSpec>), Box<dyn std::error::Error>> {
    let args: Vec<String> = env::args().collect();
    if args.len() < 3 {
        eprintln!(
            "Usage: cargo run --bin init_pda_accounts -- --vm-seed <u64> [--segment kind:slot:bytes]..."
        );
        return Err("missing required args".into());
    }

    let mut idx = 1usize;
    let mut vm_seed: Option<u64> = None;
    let mut segments: Vec<SegmentSpec> = Vec::new();

    while idx < args.len() {
        match args[idx].as_str() {
            "--vm-seed" => {
                idx += 1;
                if idx >= args.len() {
                    return Err("missing value for --vm-seed".into());
                }
                vm_seed = Some(parse_u64_value(&args[idx])?);
            }
            "--segment" => {
                idx += 1;
                if idx >= args.len() {
                    return Err("missing value for --segment".into());
                }
                segments.push(parse_segment_spec(&args[idx])?);
            }
            other => {
                return Err(format!("unknown argument: {}", other).into());
            }
        }
        idx += 1;
    }

    let vm_seed = vm_seed.ok_or("missing --vm-seed")?;
    Ok((vm_seed, segments))
}

fn parse_segment_spec(raw: &str) -> Result<SegmentSpec, Box<dyn std::error::Error>> {
    let parts: Vec<&str> = raw.split(':').collect();
    if parts.len() != 3 {
        return Err("segment spec must be kind:slot:bytes".into());
    }
    let kind = parse_segment_kind(parts[0])?;
    let slot = parse_u64_value(parts[1])?;
    if !(1..=15).contains(&slot) {
        return Err("segment slot must be in 1..=15".into());
    }
    let payload_len = parse_u64_value(parts[2])?;
    if payload_len > u32::MAX as u64 {
        return Err("segment payload bytes exceed u32::MAX".into());
    }
    Ok(SegmentSpec {
        kind,
        slot: slot as u8,
        payload_len: payload_len as u32,
    })
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

fn segment_seed_string(vm_seed: u64, kind: u8, slot: u8) -> String {
    format!("{}{vm_seed:016x}:{kind:02x}{slot:02x}", SEEDED_SEG_PREFIX)
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

async fn ensure_seeded_program_account(
    client: &RpcClient,
    fee_payer: &Keypair,
    authority: &Keypair,
    program_id: &Pubkey,
    account: Pubkey,
    seed: &str,
    space: usize,
) -> Result<(), Box<dyn std::error::Error>> {
    if let Ok(existing) = client.get_account(&account).await {
        if existing.owner != *program_id {
            return Err(format!(
                "seeded account {} already exists with owner {} (expected {})",
                account, existing.owner, program_id
            )
            .into());
        }
        if existing.data.len() < space {
            return Err(format!(
                "seeded account {} is smaller than required size: {} < {}",
                account,
                existing.data.len(),
                space
            )
            .into());
        }
        return Ok(());
    }

    let lamports = client.get_minimum_balance_for_rent_exemption(space).await?;
    let create_ix = system_instruction::create_account_with_seed(
        &fee_payer.pubkey(),
        &account,
        &authority.pubkey(),
        seed,
        lamports,
        space as u64,
        program_id,
    );
    send_instruction(client, fee_payer, authority, create_ix).await
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
