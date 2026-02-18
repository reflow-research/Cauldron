use solana_client::rpc_client::RpcClient;
use solana_sdk::{
    compute_budget::ComputeBudgetInstruction,
    instruction::{AccountMeta, Instruction},
    pubkey::Pubkey,
    signature::{read_keypair_file, Keypair, Signer},
    transaction::Transaction,
};
use std::env;
use std::fs;
use std::path::{Path, PathBuf};
use std::str::FromStr;
use toml::value::Table;

const VM_HEADER_SIZE: usize = 552;
const MMU_VM_HEADER_SIZE: usize = VM_HEADER_SIZE;
const VM_ACCOUNT_SIZE_MIN: usize = 262_696;
const EXECUTE_OP: u8 = 2;
const EXECUTE_V3_OP: u8 = 43;
const SEGMENT_KIND_WEIGHTS: u8 = 1;
const SEGMENT_KIND_RAM: u8 = 2;

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

fn parse_u64_value(raw: &str) -> Result<u64, Box<dyn std::error::Error>> {
    let value = if let Some(hex) = raw.strip_prefix("0x").or_else(|| raw.strip_prefix("0X")) {
        u64::from_str_radix(hex, 16)?
    } else {
        raw.parse::<u64>()?
    };
    Ok(value)
}

fn parse_vm_seed(vm: Option<&Table>) -> Result<Option<u64>, Box<dyn std::error::Error>> {
    let Some(vm) = vm else {
        return Ok(None);
    };
    let Some(seed) = vm.get("seed") else {
        return Ok(None);
    };
    let parsed = if let Some(value) = seed.as_integer() {
        if value < 0 {
            return Err("vm.seed must be within u64 range".into());
        }
        value as u64
    } else if let Some(value) = seed.as_str() {
        let text = value.trim();
        if text.is_empty() {
            return Ok(None);
        }
        parse_u64_value(text)?
    } else {
        return Err("vm.seed must be an integer or string".into());
    };
    Ok(Some(parsed))
}

fn resolve_accounts_path(accounts_path: &str, value: &str) -> String {
    let expanded = if let Some(home_relative) = value.strip_prefix("~/") {
        if let Ok(home) = env::var("HOME") {
            Path::new(&home)
                .join(home_relative)
                .to_string_lossy()
                .into_owned()
        } else {
            value.to_string()
        }
    } else {
        value.to_string()
    };

    let path = PathBuf::from(&expanded);
    if path.is_absolute() {
        return expanded;
    }
    let parent = Path::new(accounts_path)
        .parent()
        .unwrap_or_else(|| Path::new("."));
    parent.join(path).to_string_lossy().into_owned()
}

fn segment_kind_code(kind: &str) -> Option<u8> {
    match kind.trim().to_ascii_lowercase().as_str() {
        "weights" => Some(SEGMENT_KIND_WEIGHTS),
        "ram" => Some(SEGMENT_KIND_RAM),
        _ => None,
    }
}

fn vm_seed_string(vm_seed: u64) -> String {
    format!("fbv1:vm:{vm_seed:016x}")
}

fn segment_seed_string(vm_seed: u64, kind: u8, slot: u8) -> String {
    format!("fbv1:sg:{vm_seed:016x}:{kind:02x}{slot:02x}")
}

#[derive(Clone)]
struct PdaSegmentMeta {
    slot: u8,
    kind: u8,
    pubkey: Pubkey,
    writable: bool,
}

fn parse_pda_segments(
    segments: &[toml::Value],
    vm_seed: u64,
    authority_pubkey: &Pubkey,
    program_id: &Pubkey,
) -> Result<Vec<PdaSegmentMeta>, Box<dyn std::error::Error>> {
    let mut parsed = Vec::new();

    for (idx, seg) in segments.iter().enumerate() {
        let table = seg
            .as_table()
            .ok_or_else(|| format!("segment {} must be a table", idx + 1))?;

        let configured_pubkey = if let Some(value) = table.get("pubkey") {
            let pubkey = value.as_str().ok_or_else(|| {
                format!(
                    "segment {} pubkey must be a base58 string when provided",
                    idx + 1
                )
            })?;
            if pubkey.trim().is_empty() {
                return Err(format!(
                    "segment {} pubkey must be a base58 string when provided",
                    idx + 1
                )
                .into());
            }
            Some(pubkey)
        } else {
            None
        };

        let kind_str = table
            .get("kind")
            .and_then(|v| v.as_str())
            .ok_or_else(|| {
                format!(
                    "segment {} missing kind in deterministic account mode",
                    idx + 1
                )
            })?;
        let kind = segment_kind_code(kind_str).ok_or_else(|| {
            format!(
                "segment {} has unsupported kind '{}' (expected weights|ram)",
                idx + 1,
                kind_str
            )
        })?;

        let slot_raw = if let Some(slot_value) = table.get("slot") {
            if let Some(value) = slot_value.as_integer() {
                value
            } else if let Some(value) = slot_value.as_str() {
                let parsed = parse_u64_value(value)?;
                if parsed > i64::MAX as u64 {
                    return Err(format!("segment {} slot is out of range", idx + 1).into());
                }
                parsed as i64
            } else {
                return Err(
                    format!("segment {} slot must be an integer or string", idx + 1).into(),
                );
            }
        } else if let Some(index_value) = table.get("index") {
            if let Some(value) = index_value.as_integer() {
                value
            } else if let Some(value) = index_value.as_str() {
                let parsed = parse_u64_value(value)?;
                if parsed > i64::MAX as u64 {
                    return Err(format!("segment {} index is out of range", idx + 1).into());
                }
                parsed as i64
            } else {
                return Err(
                    format!("segment {} index must be an integer or string", idx + 1).into(),
                );
            }
        } else {
            (idx + 1) as i64
        };
        if !(1..=15).contains(&slot_raw) {
            return Err(format!(
                "segment {} has invalid slot {} (expected 1..15)",
                idx + 1,
                slot_raw
            )
            .into());
        }
        let slot = slot_raw as u8;

        let writable = table
            .get("writable")
            .and_then(|v| v.as_bool())
            .unwrap_or(false);
        let expected_writable = kind == SEGMENT_KIND_RAM;
        if writable != expected_writable {
            let access_mode = if expected_writable {
                "writable"
            } else {
                "readonly"
            };
            return Err(format!(
                "segment {} ({}) must be {} in deterministic account mode",
                idx + 1,
                kind_str,
                access_mode
            )
            .into());
        }

        let derived_pubkey = Pubkey::create_with_seed(
            authority_pubkey,
            &segment_seed_string(vm_seed, kind, slot),
            program_id,
        )?;
        if let Some(pubkey_str) = configured_pubkey {
            if pubkey_str != derived_pubkey.to_string() {
                return Err(format!(
                    "segment {} pubkey does not match deterministic derived address for vm.seed/authority/slot; remove segment pubkey or fix metadata",
                    idx + 1
                )
                .into());
            }
        }

        parsed.push(PdaSegmentMeta {
            slot,
            kind,
            pubkey: derived_pubkey,
            writable: expected_writable,
        });
    }

    if parsed.is_empty() {
        return Err("deterministic execute requires at least one mapped segment".into());
    }
    parsed.sort_by_key(|entry| entry.slot);
    for (idx, segment) in parsed.iter().enumerate() {
        if idx > 0 && parsed[idx - 1].slot == segment.slot {
            return Err(
                format!(
                    "duplicate segment slot {} in deterministic account mode",
                    segment.slot
                )
                .into(),
            );
        }
        let expected_slot = (idx + 1) as u8;
        if segment.slot != expected_slot {
            return Err(format!(
                "deterministic execute requires contiguous slots starting at 1; missing slot {} before slot {}",
                expected_slot, segment.slot
            )
            .into());
        }
    }
    if parsed[0].kind != SEGMENT_KIND_WEIGHTS {
        return Err("deterministic execute requires a weights segment at slot 1".into());
    }

    Ok(parsed)
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = env::args().collect();
    let mut manifest_path: Option<String> = None;
    let mut accounts_path: Option<String> = None;
    let mut instructions: u64 = 50_000;
    let mut rpc_override: Option<String> = None;
    let mut program_override: Option<String> = None;
    let mut payer_override: Option<String> = None;
    let mut authority_override: Option<String> = None;
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
            "--authority-keypair" => {
                authority_override = args.get(i + 1).cloned();
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
        .or_else(|| {
            cluster
                .and_then(|c| c.get("rpc_url"))
                .and_then(|v| v.as_str().map(|s| s.to_string()))
        })
        .unwrap_or_else(|| "http://127.0.0.1:8899".to_string());

    let program_id_str = program_override
        .or_else(|| {
            cluster
                .and_then(|c| c.get("program_id"))
                .and_then(|v| v.as_str().map(|s| s.to_string()))
        })
        .ok_or("Missing program_id in accounts file")?;

    let payer_path = payer_override
        .or_else(|| {
            cluster
                .and_then(|c| c.get("payer"))
                .and_then(|v| v.as_str().map(|s| s.to_string()))
        })
        .ok_or("Missing payer in accounts file")?;

    let vm = accounts_toml.get("vm").and_then(|v| v.as_table());
    let configured_vm_pubkey = vm
        .and_then(|v| v.get("pubkey"))
        .and_then(|v| v.as_str())
        .map(Pubkey::from_str)
        .transpose()?;
    let vm_seed = parse_vm_seed(vm)?;

    let program_id = Pubkey::from_str(&program_id_str)?;
    let payer = read_keypair_file(&payer_path)?;
    let authority_path = authority_override.or_else(|| {
        vm.and_then(|entry| {
            entry
                .get("authority_keypair")
                .and_then(|v| v.as_str())
                .map(|value| resolve_accounts_path(&accounts_path, value))
        })
    });
    let authority_keypair: Option<Keypair> = match authority_path {
        Some(path) => Some(read_keypair_file(path)?),
        None => None,
    };
    let authority_pubkey = authority_keypair
        .as_ref()
        .map(|kp| kp.pubkey())
        .unwrap_or_else(|| payer.pubkey());
    if vm_seed.is_some() {
        if let Some(expected_authority) = vm
            .and_then(|entry| entry.get("authority"))
            .and_then(|v| v.as_str())
        {
            if authority_pubkey.to_string() != expected_authority {
            return Err(
                "authority signer pubkey does not match vm.authority; provide matching --authority-keypair or update accounts file"
                        .into(),
                );
            }
        }
    }
    let authority_derivation_pubkey = if let Some(expected_authority) = vm
        .and_then(|entry| entry.get("authority"))
        .and_then(|v| v.as_str())
    {
        Pubkey::from_str(expected_authority)?
    } else {
        authority_pubkey
    };
    let vm_pubkey = if let Some(vm_seed) = vm_seed {
        let derived_vm = Pubkey::create_with_seed(
            &authority_derivation_pubkey,
            &vm_seed_string(vm_seed),
            &program_id,
        )?;
        if let Some(configured_vm) = configured_vm_pubkey {
            if configured_vm != derived_vm {
                return Err(
                    "vm.pubkey does not match deterministic derived VM address for vm.seed/authority; remove vm.pubkey or fix metadata"
                        .into(),
                );
            }
        }
        derived_vm
    } else {
        configured_vm_pubkey.ok_or("Missing vm.pubkey in accounts file")?
    };

    let mut metas = Vec::new();
    metas.push(AccountMeta::new_readonly(
        if vm_seed.is_some() {
            authority_pubkey
        } else {
            payer.pubkey()
        },
        true,
    ));
    metas.push(AccountMeta::new(vm_pubkey, false));

    let data = if let Some(vm_seed) = vm_seed {
        let segments = accounts_toml
            .get("segments")
            .and_then(|v| v.as_array())
            .ok_or("accounts file has no segments in deterministic account mode")?;
        let pda_segments = parse_pda_segments(
            segments,
            vm_seed,
            &authority_derivation_pubkey,
            &program_id,
        )?;
        if pda_segments.len() > 15 {
            return Err("deterministic execute supports at most 15 mapped segments".into());
        }
        for seg in &pda_segments {
            if seg.writable {
                metas.push(AccountMeta::new(seg.pubkey, false));
            } else {
                metas.push(AccountMeta::new_readonly(seg.pubkey, false));
            }
        }

        let mut data = Vec::with_capacity(1 + 8 + 8 + 1 + 1 + pda_segments.len());
        data.push(EXECUTE_V3_OP);
        data.extend_from_slice(&vm_seed.to_le_bytes());
        data.extend_from_slice(&instructions.to_le_bytes());
        data.push(0); // flags
        data.push(pda_segments.len() as u8);
        for seg in &pda_segments {
            data.push(seg.kind);
        }
        data
    } else {
        let segments = accounts_toml
            .get("segments")
            .and_then(|v| v.as_array())
            .cloned()
            .unwrap_or_default();
        let mut segs = segments.clone();
        segs.sort_by_key(|v| v.get("index").and_then(|i| i.as_integer()).unwrap_or(0));
        for seg in segs {
            let table = match seg.as_table() {
                Some(t) => t,
                None => continue,
            };
            let pubkey = table.get("pubkey").and_then(|v| v.as_str());
            let writable = table
                .get("writable")
                .and_then(|v| v.as_bool())
                .unwrap_or(false);
            if let Some(pubkey) = pubkey {
                let key = Pubkey::from_str(pubkey)?;
                if writable {
                    metas.push(AccountMeta::new(key, false));
                } else {
                    metas.push(AccountMeta::new_readonly(key, false));
                }
            }
        }
        let mut data = Vec::with_capacity(9);
        data.push(EXECUTE_OP);
        data.extend_from_slice(&instructions.to_le_bytes());
        data
    };
    let exec_ix = Instruction {
        program_id,
        accounts: metas,
        data,
    };

    let cu_ix = ComputeBudgetInstruction::set_compute_unit_limit(1_400_000);
    let client = RpcClient::new(rpc_url);
    let recent = client.get_latest_blockhash()?;
    let mut signers: Vec<&dyn Signer> = vec![&payer];
    if let Some(authority) = authority_keypair.as_ref() {
        if authority.pubkey() != payer.pubkey() {
            signers.push(authority);
        }
    }
    let tx = Transaction::new_signed_with_payer(
        &[cu_ix, exec_ix],
        Some(&payer.pubkey()),
        &signers,
        recent,
    );
    client.send_and_confirm_transaction(&tx)?;

    let account = client.get_account(&vm_pubkey)?;
    if account.data.len() < VM_ACCOUNT_SIZE_MIN {
        return Err(
            format!(
                "VM account data too small: {} < {}",
                account.data.len(),
                VM_ACCOUNT_SIZE_MIN
            )
            .into(),
        );
    }
    let scratch = &account.data[MMU_VM_HEADER_SIZE..];
    let abi = manifest_toml
        .get("abi")
        .and_then(|v| v.as_table())
        .ok_or("Missing abi")?;
    let control_offset = abi
        .get("control_offset")
        .and_then(|v| v.as_integer())
        .unwrap_or(0) as usize;
    let output_offset = abi
        .get("output_offset")
        .and_then(|v| v.as_integer())
        .unwrap_or(0) as usize;
    let output_max = abi
        .get("output_max")
        .and_then(|v| v.as_integer())
        .unwrap_or(0) as usize;

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
