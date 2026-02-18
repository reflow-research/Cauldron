use futures::stream::{FuturesUnordered, StreamExt};
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
use std::path::{Path, PathBuf};
use std::str::FromStr;
use std::sync::Arc;
use tokio::sync::Semaphore;

const DEFAULT_SOLANA_CONFIG: &str = "~/.config/solana/cli/config.yml";
const DEFAULT_RPC_URL: &str = "http://127.0.0.1:8899";
const DEFAULT_PAYER_KEYPAIR: &str = "~/.config/solana/id.json";
const DEFAULT_PROGRAM_ID: &str = "FRsToriMLgDc1Ud53ngzHUZvCRoazCaGeGUuzkwoha7m";
const CHUNK_SIZE: usize = 900;
const CONCURRENCY: usize = 100;

const BINARY_HEADER_SIZE: usize = 12;
const BINARY_MAGIC: [u8; 4] = *b"RVCD";

const OP_WRITE_ACCOUNT: u8 = 5;
const OP_INIT_VM_PDA: u8 = 40;
const OP_INIT_SEGMENT_PDA: u8 = 41;
const OP_WRITE_SEGMENT_PDA: u8 = 45;

const SEEDED_VM_PREFIX: &str = "fbv1:vm:";
const SEEDED_SEG_PREFIX: &str = "fbv1:sg:";
const VM_MEMORY_SIZE: usize = 262_144;
const VM_MEMORY_OFFSET: usize = 552;
const VM_ACCOUNT_SIZE: usize = VM_MEMORY_OFFSET + VM_MEMORY_SIZE;

const SEGMENT_KIND_WEIGHTS: u8 = 1;
const SEGMENT_KIND_RAM: u8 = 2;

#[derive(Clone, Copy)]
enum UploadMode {
    Legacy {
        target_account: Pubkey,
    },
    Pda {
        target_account: Pubkey,
        vm_pda: Pubkey,
        vm_seed: u64,
        kind: u8,
        slot: u8,
    },
}

impl UploadMode {
    fn target_account(self) -> Pubkey {
        match self {
            UploadMode::Legacy { target_account } => target_account,
            UploadMode::Pda { target_account, .. } => target_account,
        }
    }
}

#[derive(Clone, Copy)]
struct PdaUploadConfig {
    vm_seed: u64,
    kind: u8,
    slot: u8,
    vm_pda: Pubkey,
    segment_pda: Pubkey,
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    println!("--- Frostbite Parallel Model Upload ---");

    let args: Vec<String> = env::args().collect();
    if args.len() < 2 {
        println!("Usage: cargo run --bin upload_model -- <chunk_file_path>");
        return Ok(());
    }
    let chunk_path = expand_path(&args[1]);

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

    let client = Arc::new(RpcClient::new_with_commitment(
        rpc_url.clone(),
        CommitmentConfig::confirmed(),
    ));
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

    println!("RPC: {}", rpc_url);
    println!("Payer keypair: {}", payer_keypair_path);
    println!("Authority: {}", authority.pubkey());
    if let Some(path) = authority_keypair_path.as_ref() {
        println!("Authority keypair: {}", path);
    }

    let frostbite_id = detect_program_id()?;

    let data = tokio::fs::read(&chunk_path).await?;
    let file_len = data.len();
    if file_len > u32::MAX as usize {
        return Err("Chunk file exceeds max supported payload length (u32)".into());
    }
    println!("File size: {} bytes", file_len);

    let upload_mode = if pda_mode_enabled() {
        let cfg = configure_pda_mode(authority.pubkey(), &frostbite_id)?;
        println!("Upload mode: seeded deterministic");
        println!("VM PDA: {}", cfg.vm_pda);
        println!(
            "Segment PDA: {} (kind={}, slot={})",
            cfg.segment_pda, cfg.kind, cfg.slot
        );
        init_vm_pda(
            &client,
            payer.as_ref(),
            authority.as_ref(),
            &frostbite_id,
            cfg.vm_seed,
            cfg.vm_pda,
        )
        .await?;
        ensure_segment_header_for_upload(
            &client,
            payer.as_ref(),
            authority.as_ref(),
            &frostbite_id,
            cfg,
            file_len,
        )
        .await?;
        UploadMode::Pda {
            target_account: cfg.segment_pda,
            vm_pda: cfg.vm_pda,
            vm_seed: cfg.vm_seed,
            kind: cfg.kind,
            slot: cfg.slot,
        }
    } else {
        println!("Upload mode: legacy keypair account");
        if authority.pubkey() != payer.pubkey() {
            return Err(
                "Legacy upload does not support authority != payer. Use PDA mode or unset FROSTBITE_AUTHORITY_KEYPAIR."
                    .into(),
            );
        }
        let chunk_kp_path = env::var("FROSTBITE_CHUNK_KEYPAIR")
            .or_else(|_| env::var("FROSTBITE_WEIGHTS_KEYPAIR"))
            .unwrap_or_else(|_| format!("{}.json", chunk_path));
        let chunk_kp = if Path::new(&chunk_kp_path).exists() {
            solana_sdk::signature::read_keypair_file(&chunk_kp_path)?
        } else {
            let kp = Keypair::new();
            solana_sdk::signature::write_keypair_file(&kp, &chunk_kp_path)?;
            kp
        };
        let chunk_pubkey = chunk_kp.pubkey();
        println!("Target Account: {}", chunk_pubkey);

        if let Ok(existing) = client.get_account(&chunk_pubkey).await {
            if existing.owner != frostbite_id {
                return Err(format!(
                    "Target account {} is owned by {}, expected {}",
                    chunk_pubkey, existing.owner, frostbite_id
                )
                .into());
            }
        } else {
            let account_size = file_len + BINARY_HEADER_SIZE;
            println!("Creating Account ({} bytes)...", account_size);

            let rent = client
                .get_minimum_balance_for_rent_exemption(account_size)
                .await?;

            let create_ix = system_instruction::create_account(
                &payer.pubkey(),
                &chunk_pubkey,
                rent,
                account_size as u64,
                &frostbite_id,
            );
            let mut init_data = Vec::with_capacity(1 + 4 + BINARY_HEADER_SIZE);
            init_data.push(OP_WRITE_ACCOUNT);
            init_data.extend_from_slice(&0u32.to_le_bytes());
            init_data.extend_from_slice(&BINARY_MAGIC);
            init_data.extend_from_slice(&(file_len as u32).to_le_bytes());
            init_data.extend_from_slice(&0u32.to_le_bytes());
            let init_ix = Instruction {
                program_id: frostbite_id,
                accounts: vec![
                    AccountMeta::new(payer.pubkey(), true),
                    AccountMeta::new(chunk_pubkey, false),
                ],
                data: init_data,
            };

            let tx = Transaction::new_signed_with_payer(
                &[create_ix, init_ix],
                Some(&payer.pubkey()),
                &[&payer.as_ref(), &chunk_kp],
                client.get_latest_blockhash().await?,
            );
            client.send_and_confirm_transaction(&tx).await?;
            println!("Account initialized.");
        }

        UploadMode::Legacy {
            target_account: chunk_pubkey,
        }
    };

    let target_account = upload_mode.target_account();

    let semaphore = Arc::new(Semaphore::new(CONCURRENCY));
    let data_ref = Arc::new(data);

    loop {
        println!("Verifying on-chain state...");
        let acc = client.get_account(&target_account).await?;
        if acc.data.len() < BINARY_HEADER_SIZE + data_ref.len() {
            return Err("Account size mismatch".into());
        }
        if acc.data[0..4] != BINARY_MAGIC {
            return Err("Target account header magic mismatch".into());
        }
        let header_len = u32::from_le_bytes(
            acc.data[4..8]
                .try_into()
                .map_err(|_| "Header parse error")?,
        ) as usize;
        if header_len < data_ref.len() {
            return Err("Target account header payload_len is smaller than upload file".into());
        }

        let on_chain_data = &acc.data[BINARY_HEADER_SIZE..BINARY_HEADER_SIZE + data_ref.len()];

        let mut dirty_chunks = Vec::new();
        let total_chunks = (data_ref.len() + CHUNK_SIZE - 1) / CHUNK_SIZE;

        for i in 0..total_chunks {
            let start = i * CHUNK_SIZE;
            let end = std::cmp::min(start + CHUNK_SIZE, data_ref.len());
            let file_slice = &data_ref[start..end];
            let on_chain_slice = &on_chain_data[start..end];

            if file_slice != on_chain_slice {
                dirty_chunks.push(i);
            }
        }

        if dirty_chunks.is_empty() {
            println!(
                "SUCCESS: Integrity Verified. All {} chunks match.",
                total_chunks
            );
            break;
        }

        println!(
            "Uploading {}/{} dirty chunks...",
            dirty_chunks.len(),
            total_chunks
        );

        let mut futures = FuturesUnordered::new();
        for chunk_idx in dirty_chunks {
            let permit = semaphore.clone().acquire_owned().await?;
            let client = client.clone();
            let payer = payer.clone();
            let authority = authority.clone();
            let data = data_ref.clone();
            let mode = upload_mode;
            let program_id = frostbite_id;

            futures.push(tokio::spawn(async move {
                let start = chunk_idx * CHUNK_SIZE;
                let end = std::cmp::min(start + CHUNK_SIZE, data.len());
                let chunk_data = &data[start..end];

                let ix = build_chunk_write_instruction(
                    program_id,
                    authority.pubkey(),
                    mode,
                    start,
                    chunk_data,
                );
                let bh = client.get_latest_blockhash().await.unwrap_or_default();
                let tx = if payer.pubkey() == authority.pubkey() {
                    Transaction::new_signed_with_payer(
                        &[ix],
                        Some(&payer.pubkey()),
                        &[payer.as_ref()],
                        bh,
                    )
                } else {
                    Transaction::new_signed_with_payer(
                        &[ix],
                        Some(&payer.pubkey()),
                        &[payer.as_ref(), authority.as_ref()],
                        bh,
                    )
                };
                let res = client.send_and_confirm_transaction(&tx).await;
                drop(permit);
                res
            }));
        }

        while let Some(res) = futures.next().await {
            match res {
                Ok(Ok(_)) => print!("."),
                Ok(Err(_)) => print!("x"),
                Err(_) => print!("!"),
            }
            use std::io::Write;
            std::io::stdout().flush().ok();
        }
        println!();
    }

    Ok(())
}

fn build_chunk_write_instruction(
    program_id: Pubkey,
    authority: Pubkey,
    mode: UploadMode,
    payload_offset: usize,
    chunk_data: &[u8],
) -> Instruction {
    match mode {
        UploadMode::Legacy { target_account } => {
            let mut ix_data = Vec::with_capacity(5 + chunk_data.len());
            ix_data.push(OP_WRITE_ACCOUNT);
            ix_data
                .extend_from_slice(&((payload_offset + BINARY_HEADER_SIZE) as u32).to_le_bytes());
            ix_data.extend_from_slice(chunk_data);
            Instruction {
                program_id,
                accounts: vec![
                    AccountMeta::new(authority, true),
                    AccountMeta::new(target_account, false),
                ],
                data: ix_data,
            }
        }
        UploadMode::Pda {
            target_account,
            vm_pda,
            vm_seed,
            kind,
            slot,
        } => {
            let mut ix_data = Vec::with_capacity(1 + 8 + 1 + 1 + 4 + chunk_data.len());
            ix_data.push(OP_WRITE_SEGMENT_PDA);
            ix_data.extend_from_slice(&vm_seed.to_le_bytes());
            ix_data.push(kind);
            ix_data.push(slot);
            ix_data.extend_from_slice(&(payload_offset as u32).to_le_bytes());
            ix_data.extend_from_slice(chunk_data);
            Instruction {
                program_id,
                accounts: vec![
                    AccountMeta::new_readonly(authority, true),
                    AccountMeta::new_readonly(vm_pda, false),
                    AccountMeta::new(target_account, false),
                ],
                data: ix_data,
            }
        }
    }
}

fn configure_pda_mode(
    authority: Pubkey,
    program_id: &Pubkey,
) -> Result<PdaUploadConfig, Box<dyn std::error::Error>> {
    let vm_seed_raw = env::var("FROSTBITE_VM_SEED")
        .map_err(|_| "FROSTBITE_VM_SEED is required for PDA upload mode")?;
    let vm_seed = parse_u64_value(&vm_seed_raw)?;

    let kind_raw = env::var("FROSTBITE_SEGMENT_KIND").unwrap_or_else(|_| "weights".to_string());
    let kind = parse_segment_kind(&kind_raw)?;

    let slot_raw = env::var("FROSTBITE_SEGMENT_SLOT").unwrap_or_else(|_| "1".to_string());
    let slot_u64 = parse_u64_value(&slot_raw)?;
    if !(1..=15).contains(&slot_u64) {
        return Err("FROSTBITE_SEGMENT_SLOT must be in range 1..=15".into());
    }
    let slot = slot_u64 as u8;

    let vm_pda = derive_vm_pda(program_id, &authority, vm_seed)?;
    let segment_pda = derive_segment_pda(program_id, &authority, vm_seed, kind, slot)?;

    if let Ok(vm_hint) = env::var("FROSTBITE_VM_PUBKEY") {
        let hinted = Pubkey::from_str(&vm_hint)?;
        if hinted != vm_pda {
            return Err(format!(
                "FROSTBITE_VM_PUBKEY mismatch: derived={}, provided={}",
                vm_pda, hinted
            )
            .into());
        }
    }

    if let Ok(seg_hint) = env::var("FROSTBITE_SEGMENT_PUBKEY") {
        let hinted = Pubkey::from_str(&seg_hint)?;
        if hinted != segment_pda {
            return Err(format!(
                "FROSTBITE_SEGMENT_PUBKEY mismatch: derived={}, provided={}",
                segment_pda, hinted
            )
            .into());
        }
    }

    Ok(PdaUploadConfig {
        vm_seed,
        kind,
        slot,
        vm_pda,
        segment_pda,
    })
}

fn pda_mode_enabled() -> bool {
    if env::var("FROSTBITE_VM_SEED").is_ok() {
        return true;
    }
    match env::var("FROSTBITE_UPLOAD_MODE") {
        Ok(value) => value.eq_ignore_ascii_case("pda") || value.eq_ignore_ascii_case("seeded"),
        Err(_) => false,
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

fn parse_segment_kind(raw: &str) -> Result<u8, Box<dyn std::error::Error>> {
    let lowered = raw.trim().to_ascii_lowercase();
    match lowered.as_str() {
        "1" | "weights" => Ok(SEGMENT_KIND_WEIGHTS),
        "2" | "ram" => Ok(SEGMENT_KIND_RAM),
        _ => Err(format!(
            "Unsupported FROSTBITE_SEGMENT_KIND '{}'; expected weights|ram|1|2",
            raw
        )
        .into()),
    }
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

async fn init_vm_pda(
    client: &RpcClient,
    fee_payer: &Keypair,
    authority: &Keypair,
    program_id: &Pubkey,
    vm_seed: u64,
    vm_pda: Pubkey,
) -> Result<(), Box<dyn std::error::Error>> {
    ensure_seeded_program_account(
        client,
        fee_payer,
        authority,
        program_id,
        vm_pda,
        &vm_seed_string(vm_seed),
        VM_ACCOUNT_SIZE,
    )
    .await?;

    let mut data = Vec::with_capacity(1 + 8);
    data.push(OP_INIT_VM_PDA);
    data.extend_from_slice(&vm_seed.to_le_bytes());

    let ix = Instruction {
        program_id: *program_id,
        accounts: vec![
            AccountMeta::new_readonly(authority.pubkey(), true),
            AccountMeta::new(vm_pda, false),
        ],
        data,
    };

    send_instruction(client, fee_payer, authority, ix).await
}

async fn ensure_segment_header_for_upload(
    client: &RpcClient,
    fee_payer: &Keypair,
    authority: &Keypair,
    program_id: &Pubkey,
    cfg: PdaUploadConfig,
    file_len: usize,
) -> Result<(), Box<dyn std::error::Error>> {
    let required_space = BINARY_HEADER_SIZE
        .checked_add(file_len)
        .ok_or("segment size overflow")?;
    ensure_seeded_program_account(
        client,
        fee_payer,
        authority,
        program_id,
        cfg.segment_pda,
        &segment_seed_string(cfg.vm_seed, cfg.kind, cfg.slot),
        required_space,
    )
    .await?;

    if let Ok(acc) = client.get_account(&cfg.segment_pda).await {
        if acc.owner != *program_id {
            return Err("Segment PDA exists but is not owned by Frostbite program".into());
        }
        if acc.data.len() < required_space {
            return Err(
                "Segment PDA exists but is smaller than required payload length; close and recreate it"
                    .into(),
            );
        }
        if acc.data.len() >= BINARY_HEADER_SIZE
            && acc.data[0..4] == BINARY_MAGIC
            && u32::from_le_bytes(
                acc.data[4..8]
                    .try_into()
                    .map_err(|_| "Header parse error")?,
            ) as usize
                == file_len
        {
            return Ok(());
        }
    }

    let mut data = Vec::with_capacity(1 + 8 + 1 + 1 + 4);
    data.push(OP_INIT_SEGMENT_PDA);
    data.extend_from_slice(&cfg.vm_seed.to_le_bytes());
    data.push(cfg.kind);
    data.push(cfg.slot);
    data.extend_from_slice(&(file_len as u32).to_le_bytes());

    let ix = Instruction {
        program_id: *program_id,
        accounts: vec![
            AccountMeta::new_readonly(authority.pubkey(), true),
            AccountMeta::new_readonly(cfg.vm_pda, false),
            AccountMeta::new(cfg.segment_pda, false),
        ],
        data,
    };

    send_instruction(client, fee_payer, authority, ix).await
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
                "seeded account {} already exists with owner {}, expected {}",
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
    ix: Instruction,
) -> Result<(), Box<dyn std::error::Error>> {
    let bh = client.get_latest_blockhash().await?;
    let tx = if fee_payer.pubkey() == authority.pubkey() {
        Transaction::new_signed_with_payer(&[ix], Some(&fee_payer.pubkey()), &[fee_payer], bh)
    } else {
        Transaction::new_signed_with_payer(
            &[ix],
            Some(&fee_payer.pubkey()),
            &[fee_payer, authority],
            bh,
        )
    };
    client.send_and_confirm_transaction(&tx).await?;
    Ok(())
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
