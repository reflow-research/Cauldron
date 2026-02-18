#![no_std]

use solana_program::{
    account_info::{next_account_info, AccountInfo},
    entrypoint,
    entrypoint::ProgramResult,
    msg,
    program_error::ProgramError,
    pubkey::Pubkey,
};

const VM_HEADER_SIZE: usize = 552;
const MMU_VM_HEADER_SIZE: usize = VM_HEADER_SIZE;
const VM_ACCOUNT_SIZE_MIN: usize = 262_696;
const FBM1_MAGIC: u32 = 0x314D_4246;
const ABI_VERSION: u32 = 1;

const ERR_INVALID_INPUT: u32 = 0x2000;
const ERR_INVALID_CONTROL: u32 = 0x2001;
const ERR_OUTPUT_BOUNDS: u32 = 0x2002;
const ERR_BELOW_THRESHOLD: u32 = 0x2003;

entrypoint!(process_instruction);

fn read_u32_le(buf: &[u8], offset: usize) -> Result<u32, ProgramError> {
    if offset + 4 > buf.len() {
        return Err(ProgramError::Custom(ERR_INVALID_CONTROL));
    }
    Ok(u32::from_le_bytes(
        buf[offset..offset + 4].try_into().unwrap(),
    ))
}

fn read_i32_le(buf: &[u8], offset: usize) -> Result<i32, ProgramError> {
    if offset + 4 > buf.len() {
        return Err(ProgramError::Custom(ERR_INVALID_CONTROL));
    }
    Ok(i32::from_le_bytes(
        buf[offset..offset + 4].try_into().unwrap(),
    ))
}

pub fn process_instruction(
    _program_id: &Pubkey,
    accounts: &[AccountInfo],
    ix_data: &[u8],
) -> ProgramResult {
    if ix_data.len() < 8 {
        return Err(ProgramError::InvalidInstructionData);
    }

    let control_offset = u32::from_le_bytes(ix_data[0..4].try_into().unwrap()) as usize;
    let threshold = i32::from_le_bytes(ix_data[4..8].try_into().unwrap());
    let output_index = if ix_data.len() >= 12 {
        u32::from_le_bytes(ix_data[8..12].try_into().unwrap()) as usize
    } else {
        0
    };

    let mut account_iter = accounts.iter();
    let authority = next_account_info(&mut account_iter)?;
    let vm_account = next_account_info(&mut account_iter)?;

    if !authority.is_signer {
        return Err(ProgramError::MissingRequiredSignature);
    }

    let data = vm_account.try_borrow_data()?;
    if data.len() < VM_ACCOUNT_SIZE_MIN {
        return Err(ProgramError::AccountDataTooSmall);
    }
    let scratch = &data[MMU_VM_HEADER_SIZE..];

    if control_offset + 64 > scratch.len() {
        return Err(ProgramError::Custom(ERR_INVALID_CONTROL));
    }

    let magic = read_u32_le(scratch, control_offset)?;
    let abi_version = read_u32_le(scratch, control_offset + 4)?;
    let status = read_u32_le(scratch, control_offset + 12)?;
    let output_ptr = read_u32_le(scratch, control_offset + 24)? as usize;
    let output_len = read_u32_le(scratch, control_offset + 28)? as usize;

    if magic != FBM1_MAGIC || abi_version != ABI_VERSION {
        return Err(ProgramError::Custom(ERR_INVALID_CONTROL));
    }
    if status != 0 {
        return Err(ProgramError::Custom(status));
    }

    if output_len < 4 {
        return Err(ProgramError::Custom(ERR_OUTPUT_BOUNDS));
    }

    let output_offset = output_ptr + output_index * 4;
    let output_end = output_ptr.saturating_add(output_len);
    if output_offset + 4 > scratch.len() || output_offset + 4 > output_end {
        return Err(ProgramError::Custom(ERR_OUTPUT_BOUNDS));
    }

    let value = read_i32_le(scratch, output_offset)?;
    msg!(
        "gatekeeper: output[{}]={} threshold={}",
        output_index,
        value,
        threshold
    );
    if value < threshold {
        return Err(ProgramError::Custom(ERR_BELOW_THRESHOLD));
    }

    Ok(())
}
