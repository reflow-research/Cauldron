use solana_client::rpc_client::RpcClient;
use solana_sdk::{
    commitment_config::CommitmentConfig,
    instruction::{AccountMeta, Instruction},
    pubkey::Pubkey,
    signature::{Keypair, Signer},
    transaction::Transaction,
};
use std::env;
use std::fs;
use std::path::PathBuf;
use std::str::FromStr;

const DEFAULT_SOLANA_CONFIG: &str = "~/.config/solana/cli/config.yml";
const DEFAULT_RPC_URL: &str = "http://127.0.0.1:8899";
const DEFAULT_PAYER_KEYPAIR: &str = "~/.config/solana/id.json";
const DEFAULT_PROGRAM_ID: &str = "FRsToriMLgDc1Ud53ngzHUZvCRoazCaGeGUuzkwoha7m";
const DEFAULT_CHUNK_SIZE: usize = 900;

const WRITE_ACCOUNT: u8 = 5;

#[derive(Default)]
struct CliConfig {
    rpc_url: Option<String>,
    keypair_path: Option<String>,
}

fn load_solana_cli_config(path: &str) -> Option<CliConfig> {
    let path = expand_path(path);
    let contents = fs::read_to_string(&path).ok()?;
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
        if let Ok(home) = env::var("HOME") {
            return format!("{}/{}", home, stripped);
        }
    }
    path.to_string()
}

fn parse_offset(value: &str) -> Result<u32, Box<dyn std::error::Error>> {
    if let Some(hex) = value.strip_prefix("0x") {
        Ok(u32::from_str_radix(hex, 16)?)
    } else {
        Ok(value.parse::<u32>()?)
    }
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = env::args().collect();
    if args.len() < 4 {
        eprintln!("Usage: write_account <account_pubkey> <offset> <file> [--chunk-size N]");
        return Ok(());
    }

    let mut positional = Vec::new();
    let mut chunk_size = DEFAULT_CHUNK_SIZE;
    let mut i = 1;
    while i < args.len() {
        if args[i] == "--chunk-size" {
            if i + 1 >= args.len() {
                return Err("--chunk-size requires a value".into());
            }
            chunk_size = args[i + 1].parse()?;
            i += 2;
            continue;
        }
        positional.push(args[i].clone());
        i += 1;
    }

    if positional.len() < 3 {
        return Err("Missing required arguments".into());
    }

    let target_pubkey = Pubkey::from_str(&positional[0])?;
    let base_offset = parse_offset(&positional[1])?;
    let file_path = &positional[2];

    let solana_config_path = env::var("SOLANA_CONFIG").unwrap_or_else(|_| DEFAULT_SOLANA_CONFIG.to_string());
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

    let frostbite_id = detect_program_id()?;

    let client = RpcClient::new_with_commitment(rpc_url.clone(), CommitmentConfig::confirmed());
    let payer = solana_sdk::signature::read_keypair_file(&payer_keypair_path)?;

    let data = fs::read(file_path)?;
    let total = data.len();
    if total == 0 {
        eprintln!("No data to write");
        return Ok(());
    }

    let mut offset = base_offset as usize;
    let mut start = 0usize;
    let mut _chunk_idx = 0u64;

    while start < total {
        let end = usize::min(start + chunk_size, total);
        let chunk = &data[start..end];

        let mut ix_data = Vec::with_capacity(1 + 4 + chunk.len());
        ix_data.push(WRITE_ACCOUNT);
        ix_data.extend_from_slice(&(offset as u32).to_le_bytes());
        ix_data.extend_from_slice(chunk);

        let ix = Instruction {
            program_id: frostbite_id,
            accounts: vec![
                AccountMeta::new_readonly(payer.pubkey(), true),
                AccountMeta::new(target_pubkey, false),
            ],
            data: ix_data,
        };

        let tx = Transaction::new_signed_with_payer(
            &[ix],
            Some(&payer.pubkey()),
            &[&payer as &dyn Signer],
            client.get_latest_blockhash()?,
        );
        client.send_and_confirm_transaction(&tx)?;

        _chunk_idx += 1;
        start = end;
        offset += chunk.len();
    }

    println!("Wrote {} bytes to {}", total, target_pubkey);
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
    let data = fs::read_to_string(path)?;
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
