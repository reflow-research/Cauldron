use solana_client::rpc_client::RpcClient;
use solana_sdk::{
    compute_budget::ComputeBudgetInstruction,
    instruction::{AccountMeta, Instruction},
    pubkey::Pubkey,
    signature::{read_keypair_file, Signer},
    transaction::Transaction,
};
use std::env;
use std::fs;
use std::str::FromStr;

const MMU_VM_HEADER_SIZE: usize = 545;
const EXECUTE_OP: u8 = 2;

fn read_u32_le(buf: &[u8], offset: usize) -> u32 {
    u32::from_le_bytes(buf[offset..offset + 4].try_into().unwrap())
}

fn decode_i32(buf: &[u8]) -> Vec<i32> {
    let mut out = Vec::new();
    let mut i = 0usize;
    while i + 4 <= buf.len() {
        out.push(i32::from_le_bytes(buf[i..i + 4].try_into().unwrap()));
        i += 4;
    }
    out
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = env::args().collect();
    let mut manifest_path: Option<String> = None;
    let mut accounts_path: Option<String> = None;
    let mut instructions: u64 = 50_000;
    let mut rpc_override: Option<String> = None;
    let mut program_override: Option<String> = None;
    let mut payer_override: Option<String> = None;
    let mut use_max = false;

    let mut i = 1;
    while i < args.len() {
        match args[i].as_str() {
            "--manifest" => {
                manifest_path = args.get(i + 1).cloned();
                i += 2;
            }
            "--accounts" => {
                accounts_path = args.get(i + 1).cloned();
                i += 2;
            }
            "--instructions" => {
                if let Some(val) = args.get(i + 1) {
                    instructions = val.parse()?;
                }
                i += 2;
            }
            "--rpc-url" => {
                rpc_override = args.get(i + 1).cloned();
                i += 2;
            }
            "--program-id" => {
                program_override = args.get(i + 1).cloned();
                i += 2;
            }
            "--payer" => {
                payer_override = args.get(i + 1).cloned();
                i += 2;
            }
            "--use-max" => {
                use_max = true;
                i += 1;
            }
            _ => {
                i += 1;
            }
        }
    }

    let manifest_path = manifest_path.ok_or("--manifest required")?;
    let accounts_path = accounts_path.ok_or("--accounts required")?;

    let accounts_toml: toml::Value = fs::read_to_string(&accounts_path)?.parse()?;
    let manifest_toml: toml::Value = fs::read_to_string(&manifest_path)?.parse()?;

    let cluster = accounts_toml.get("cluster").and_then(|v| v.as_table());
    let rpc_url = rpc_override
        .or_else(|| cluster.and_then(|c| c.get("rpc_url")).and_then(|v| v.as_str().map(|s| s.to_string())))
        .unwrap_or_else(|| "http://127.0.0.1:8899".to_string());

    let program_id_str = program_override
        .or_else(|| cluster.and_then(|c| c.get("program_id")).and_then(|v| v.as_str().map(|s| s.to_string())))
        .ok_or("Missing program_id in accounts file")?;

    let payer_path = payer_override
        .or_else(|| cluster.and_then(|c| c.get("payer")).and_then(|v| v.as_str().map(|s| s.to_string())))
        .ok_or("Missing payer in accounts file")?;

    let vm_pubkey_str = accounts_toml
        .get("vm")
        .and_then(|v| v.as_table())
        .and_then(|v| v.get("pubkey"))
        .and_then(|v| v.as_str())
        .ok_or("Missing vm.pubkey in accounts file")?;

    let program_id = Pubkey::from_str(&program_id_str)?;
    let vm_pubkey = Pubkey::from_str(vm_pubkey_str)?;
    let payer = read_keypair_file(&payer_path)?;

    let mut metas = Vec::new();
    metas.push(AccountMeta::new_readonly(payer.pubkey(), true));
    metas.push(AccountMeta::new(vm_pubkey, false));

    if let Some(segments) = accounts_toml.get("segments").and_then(|v| v.as_array()) {
        let mut segs = segments.clone();
        segs.sort_by_key(|v| v.get("index").and_then(|i| i.as_integer()).unwrap_or(0));
        for seg in segs {
            let table = match seg.as_table() {
                Some(t) => t,
                None => continue,
            };
            let pubkey = table.get("pubkey").and_then(|v| v.as_str());
            let writable = table.get("writable").and_then(|v| v.as_bool()).unwrap_or(false);
            if let Some(pubkey) = pubkey {
                let key = Pubkey::from_str(pubkey)?;
                if writable {
                    metas.push(AccountMeta::new(key, false));
                } else {
                    metas.push(AccountMeta::new_readonly(key, false));
                }
            }
        }
    }

    let mut data = Vec::with_capacity(9);
    data.push(EXECUTE_OP);
    data.extend_from_slice(&instructions.to_le_bytes());
    let exec_ix = Instruction {
        program_id,
        accounts: metas,
        data,
    };

    let cu_ix = ComputeBudgetInstruction::set_compute_unit_limit(1_400_000);
    let client = RpcClient::new(rpc_url);
    let recent = client.get_latest_blockhash()?;
    let tx = Transaction::new_signed_with_payer(
        &[cu_ix, exec_ix],
        Some(&payer.pubkey()),
        &[&payer],
        recent,
    );
    client.send_and_confirm_transaction(&tx)?;

    let account = client.get_account(&vm_pubkey)?;
    if account.data.len() < MMU_VM_HEADER_SIZE {
        return Err("VM account data too small".into());
    }
    let scratch = &account.data[MMU_VM_HEADER_SIZE..];
    let abi = manifest_toml.get("abi").and_then(|v| v.as_table()).ok_or("Missing abi")?;
    let control_offset = abi.get("control_offset").and_then(|v| v.as_integer()).unwrap_or(0) as usize;
    let output_offset = abi.get("output_offset").and_then(|v| v.as_integer()).unwrap_or(0) as usize;
    let output_max = abi.get("output_max").and_then(|v| v.as_integer()).unwrap_or(0) as usize;

    let status = read_u32_le(scratch, control_offset + 12);
    let mut output_len = read_u32_le(scratch, control_offset + 28) as usize;
    if output_len == 0 && use_max {
        output_len = output_max;
    }
    let output_end = output_offset + output_len;
    let output = if output_end <= scratch.len() {
        &scratch[output_offset..output_end]
    } else {
        &[]
    };

    println!("Status: {}", status);
    if output.is_empty() {
        println!("Output: <empty>");
    } else {
        println!("Output (i32): {:?}", decode_i32(output));
    }
    Ok(())
}
