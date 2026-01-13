# Frostbite VM - Syscall Reference

This document describes all syscalls available in the Frostbite RISC-V VM.

## Calling Convention

Syscalls use the RISC-V `ecall` instruction:
- `a7` (x17): syscall id
- `a0`-`a6`: arguments
- `a0`: return value

## Syscall Ranges

| Range | Category |
|-------|----------|
| 0-99 | System |
| 110-144 | LLM Accelerators |
| 7000-7019 | AI/ML Accelerators |
| 8000-8999 | Fused Kernels |
| 9000+ | Quantum |

## Full Syscall Table

| ID | Name | Args | Return | Notes |
|----|------|------|--------|-------|
| 60 | PUTCHAR | `a0=char` | `a0` | Write one byte to the VM log. |
| 64 | WRITE | `a0=fd (ignored)`<br>`a1=buf_ptr`<br>`a2=len` | `a0=bytes` | Write to Solana log (stdout). |
| 93 | EXIT | `a0=code` | - | Halt the VM. |
| 123 | YIELD | `a0=state_ptr` | `a0=0` | Yield execution (see State Layouts). |
| 110 | MATMUL | `a0=out_ptr`<br>`a1=x_ptr`<br>`a2=w_ptr`<br>`a3=n`<br>`a4=d` | `a0=0` | Deprecated; returns InvalidInstruction. |
| 111 | RMSNORM | `a0=out_ptr`<br>`a1=x_ptr`<br>`a2=weight_ptr`<br>`a3=size` | `a0=0` | RMS normalization on f32. |
| 112 | SOFTMAX | `a0=x_ptr`<br>`a1=size` | `a0=0` | In-place f32 softmax. |
| 113 | SILU | `a0=x_ptr`<br>`a1=size` | `a0=0` | In-place f32 SiLU. |
| 114 | ROPE | `a0=q_ptr`<br>`a1=k_ptr`<br>`a2=pos`<br>`a3=dim`<br>`a4=head_size` | `a0=0` | Rotary embeddings. |
| 115 | MATMUL_Q8 | `a0=out_ptr`<br>`a1=x_ptr`<br>`a2=w_ptr`<br>`a3=scale_ptr`<br>`a4=n_or_flags`<br>`a5=d` | `a0=0` | See Q8 flags. |
| 116 | ACCUM | `a0=out_ptr`<br>`a1=x_ptr`<br>`a2=size` | `a0=0` | Element-wise add on f32. |
| 117 | READ_F32 | `a0=addr` | `a0=bits` | Reads f32 bits from VM addr. |
| 118 | WRITE_F32 | `a0=addr`<br>`a1=bits` | `a0=0` | Writes f32 bits to VM addr. |
| 119 | MEMCPY_F32 | `a0=dst`<br>`a1=src`<br>`a2=count` | `a0=0` | Copy f32 array by count. |
| 120 | MATMUL_Q8_PARTIAL | `a0=out_ptr`<br>`a1=x_ptr`<br>`a2=w_ptr`<br>`a3=scale_ptr`<br>`a4=n_or_flags`<br>`a5=d`<br>`a6=state_ptr` | `a0=0` | Resumable rows (see State Layouts). |
| 121 | ARGMAX_PARTIAL | `a0=ptr`<br>`a1=count`<br>`a2=state_ptr` | `a0=max_idx` | Resumable f32 argmax. |
| 122 | DEBUG_LOG | `a0=tag`<br>`a1=a`<br>`a2=b`<br>`a3=c`<br>`a4=d` | `a0=0` | Debug log with 4 values. |
| 130 | MATMUL_I8_I32 | `a0=out_ptr`<br>`a1=x_ptr`<br>`a2=w_ptr`<br>`a3=scale_q16`<br>`a4=n`<br>`a5=d` | `a0=0` | Int8 weights, i32 activations. |
| 131 | SOFTMAX_I32 | `a0=x_ptr`<br>`a1=len` | `a0=0` | Q16 i32 softmax. |
| 132 | DOT_I32 | `a0=a_ptr`<br>`a1=b_ptr`<br>`a2=len`<br>`a3=shift` | `a0=result` | Sum(a[i]*b[i]) >> shift. |
| 133 | WEIGHTED_SUM_I32 | `a0=out_ptr`<br>`a1=src_ptr`<br>`a2=weight`<br>`a3=len`<br>`a4=shift` | `a0=0` | out[i] += (weight * src[i]) >> shift. |
| 134 | MATMUL_I8_I32_PARTIAL | `a0=out_ptr`<br>`a1=x_ptr`<br>`a2=w_ptr`<br>`a3=scale_q16`<br>`a4=n`<br>`a5=d`<br>`a6=state_ptr` | `a0=0` | Resumable rows. |
| 135 | ARGMAX_I32_PARTIAL | `a0=ptr`<br>`a1=count`<br>`a2=state_ptr` | `a0=max_idx` | Resumable i32 argmax. |
| 136 | SOFTMAX_I32_F32 | `a0=x_ptr`<br>`a1=len` | `a0=0` | Q16 i32 softmax using f32 math. |
| 137 | SILU_MUL_I32 | `a0=hb_ptr`<br>`a1=hb2_ptr`<br>`a2=size` | `a0=0` | SiLU gate multiply (Q16). |
| 138 | RMSNORM_I32 | `a0=out_ptr`<br>`a1=x_ptr`<br>`a2=weight_addr`<br>`a3=dim` | `a0=0` | Weight layout uses i16 scale + i16 weights. |
| 139 | MATMUL_I8_I8 | `a0=out_ptr`<br>`a1=x_ptr`<br>`a2=w_ptr`<br>`a3=w_scale_q16`<br>`a4=n`<br>`a5=d` | `a0=0` | Prequant buffer (see Q8 flags). |
| 140 | MATMUL_I8_I8_PARTIAL | `a0=out_ptr`<br>`a1=x_ptr`<br>`a2=w_ptr`<br>`a3=w_scale_q16`<br>`a4=n`<br>`a5=d`<br>`a6=state_ptr` | `a0=0` | Resumable rows. |
| 141 | MATMUL_I8_I8_QKV | `a0=cfg_ptr` | `a0=0` | Fused Q/K/V (see Config Layouts). |
| 142 | MATMUL_I8_I8_W1W3 | `a0=cfg_ptr` | `a0=0` | Fused W1/W3 (see Config Layouts). |
| 143 | MATMUL_I8_I8_ARGMAX_PARTIAL | `a0=x_ptr`<br>`a1=w_ptr`<br>`a2=w_scale_q16`<br>`a3=n`<br>`a4=d`<br>`a5=state_ptr` | `a0=max_idx` | Resumable argmax with shortlist (see State Layouts). |
| 144 | MATMUL_I8_I8_W1W3_SILU | `a0=cfg_ptr` | `a0=0` | Fused W1/W3 + SiLU (see Config Layouts). |
| 7001 | DOT_I8 | `a0=a_ptr`<br>`a1=b_ptr`<br>`a2=len` | `a0=sum` | Sum of int8 dot product. |
| 7003 | VEC_ADD | `a0=dst_ptr`<br>`a1=src_ptr`<br>`a2=len` | `a0=0` | In-place int8 add. |
| 7010 | ACTIVATION | `a0=data_ptr`<br>`a1=len`<br>`a2=type` | `a0=0` | Type: 0=ReLU, 1=Sigmoid. |
| 8001 | GRAPH_SEARCH | `a0=input_ptr`<br>`a1=graph_idx`<br>`a2=output_ptr`<br>`a3=min_score` | `a0=count` | Graph edge search. |
| 8002 | GRAPH_SEARCH_ALT | `a0=input_ptr`<br>`a1=graph_idx`<br>`a2=output_ptr`<br>`a3=min_score` | `a0=count` | Alias of GRAPH_SEARCH. |
| 8005 | ARB_SEARCH | `a0=input_mint_ptr`<br>`a1=graph_idx`<br>`a2=output_ptr`<br>`a3=min_amount`<br>`a4=mask_ptr` | `a0=count` | Arbitrage search in graph. |
| 8010 | ARB_SCORE | `a0=graph_idx`<br>`a1=weights_ptr`<br>`a2=threshold`<br>`a3=mask_ptr` | `a0=count` | Graph edge scoring. |
| 8020 | AGGREGATE | `a0=graph_idx`<br>`a1=table_ptr`<br>`a2=features_ptr`<br>`a3=max_nodes` | `a0=count` | GNN message passing. |
| 9000 | QUANTUM_OP | `a0=op`<br>`a1=target`<br>`a2=control`<br>`a3=state_ptr` | `a0=result` | 7-qubit state ops (see Quantum Opcodes). |

## Flags

### Q8 Flags (used by MATMUL_Q8 and MATMUL_Q8_PARTIAL)

| Flag | Meaning |
|------|---------|
| `1 << 63` | Prequant input buffer at `x_ptr`. |
| `1 << 62` | Tensor scale: `scale_ptr` is a single f32. |

## State Layouts

### Row Cursor State (u32 words)

Used by MATMUL_Q8_PARTIAL, MATMUL_I8_I32_PARTIAL, MATMUL_I8_I8_PARTIAL,
MATMUL_I8_I8_QKV, MATMUL_I8_I8_W1W3, MATMUL_I8_I8_W1W3_SILU, and YIELD.

| Word | Field | Notes |
|------|-------|-------|
| 0 | cursor | Current row. For YIELD, 0 means yield, 1 means clear. |
| 1 | max_rows | Max rows per call (0 means all). |

### Argmax State (f32, u32 words)

| Word | Field | Notes |
|------|-------|-------|
| 0 | cursor | Current index. |
| 1 | max_idx | Current max index. |
| 2 | max_bits | f32 bits for current max. |
| 3 | max_per_call | Max elements per call (0 means all). |

### Argmax State (i32, u32 words)

| Word | Field | Notes |
|------|-------|-------|
| 0 | cursor | Current index. |
| 1 | max_idx | Current max index. |
| 2 | max_val | i32 max value. |
| 3 | max_per_call | Max elements per call (0 means all). |

### MATMUL_I8_I8_ARGMAX_PARTIAL State (u32 words)

| Word | Field | Notes |
|------|-------|-------|
| 0 | cursor | Current row cursor. |
| 1 | max_idx | Current max index. |
| 2 | max_val | i32 max value. |
| 3 | max_rows_per_call | Max rows per call. |
| 4 | topk2 | Size of shortlist 2 (0 disables). |
| 5 | filled2 | Entries filled in shortlist 2. |
| 6 | min_val2 | Current min value in shortlist 2. |
| 7 | min_pos2 | Index of min in shortlist 2. |
| 8 | short_n2 | Shortlist 2 width (0 disables). |
| 9 | topk1 | Size of shortlist 1 (0 disables). |
| 10 | filled1 | Entries filled in shortlist 1. |
| 11 | min_val1 | Current min value in shortlist 1. |
| 12 | min_pos1 | Index of min in shortlist 1. |
| 13 | short_n1 | Shortlist 1 width (0 disables). |
| 14 | stage2_cursor | Stage2 cursor. |
| 15 | full_cursor | Full scan cursor. |
| 16 | stage2_max | Stage2 max rows (0 uses max_rows_per_call). |
| 17 | full_max | Full scan max rows (0 uses max_rows_per_call). |
| 18.. | arrays | topk2_idx, topk2_score, topk1_idx, topk1_score. |

## Config Layouts

### MATMUL_I8_I8_QKV Config (bytes)

| Offset | Field | Type | Notes |
|--------|-------|------|-------|
| 0 | out_q | u64 | Output Q (i32). |
| 8 | out_k | u64 | Output K (i32). |
| 16 | out_v | u64 | Output V (i32). |
| 24 | x_ptr | u64 | Prequant buffer. |
| 32 | wq_ptr | u64 | Q weights. |
| 40 | wk_ptr | u64 | K weights. |
| 48 | wv_ptr | u64 | V weights. |
| 56 | wq_scale | u32 | Q scale (Q16). |
| 60 | wk_scale | u32 | K scale (Q16). |
| 64 | wv_scale | u32 | V scale (Q16). |
| 68 | n | u32 | Input dim. |
| 72 | d_q | u32 | Q rows. |
| 76 | d_k | u32 | K rows. |
| 80 | d_v | u32 | V rows. |
| 88 | state_ptr | u64 | Row cursor state. |

### MATMUL_I8_I8_W1W3 Config (bytes)

| Offset | Field | Type | Notes |
|--------|-------|------|-------|
| 0 | out_a | u64 | Output W1 (i32). |
| 8 | out_b | u64 | Output W3 (i32). |
| 16 | x_ptr | u64 | Prequant buffer. |
| 24 | w1_ptr | u64 | W1 weights. |
| 32 | w3_ptr | u64 | W3 weights. |
| 40 | w1_scale | u32 | W1 scale (Q16). |
| 44 | w3_scale | u32 | W3 scale (Q16). |
| 48 | n | u32 | Input dim. |
| 52 | d | u32 | Output rows. |
| 56 | state_ptr | u64 | Row cursor state. |

### MATMUL_I8_I8_W1W3_SILU Config (bytes)

| Offset | Field | Type | Notes |
|--------|-------|------|-------|
| 0 | out_ptr | u64 | Output (i32). |
| 8 | x_ptr | u64 | Prequant buffer. |
| 16 | w1_ptr | u64 | W1 weights. |
| 24 | w3_ptr | u64 | W3 weights. |
| 32 | w1_scale | u32 | W1 scale (Q16). |
| 36 | w3_scale | u32 | W3 scale (Q16). |
| 40 | n | u32 | Input dim. |
| 44 | d | u32 | Output rows. |
| 48 | state_ptr | u64 | Row cursor state. |

## Quantum Opcodes

| Op | Name | Notes |
|----|------|-------|
| 0 | INIT | Zero state, set `ket(0...0)` = 1.0. |
| 1 | H | Hadamard on target. |
| 2 | CNOT | Controlled-NOT (control -> target). |
| 3 | MEASURE | Measure target, control is RNG seed. |
| 4 | RX | X rotation (control is angle index). |
| 5 | RZ | Z rotation (control is angle index). |
| 6 | PHASE | Phase shift (control is angle index). |
