---
name: frostbite-cauldron
version: 1.0.0
description: Deploy and invoke AI models on-chain with verifiable inference. Train off-chain, execute on Solana.
homepage: https://github.com/reflow-labs/cauldron
metadata: {"emoji":"🔮","category":"on-chain-ai","author":"Reflow Labs"}
---

# Frostbite + Cauldron

**On-chain AI inference.** Train models off-chain, deploy weights to Solana, run inference inside transactions.

## What This Is

**Frostbite** — On-chain compute environment for AI inference. Models execute at transaction time with access to current chain state. Deterministic, verifiable, atomic.

**Cauldron** — SDK and CLI for the full pipeline: train → quantize → upload → invoke.

## Why It Matters

| Off-chain AI | On-chain AI (Frostbite) |
|--------------|-------------------------|
| Inference is a black box | Inference is verifiable |
| Weights are private | Weights are public, auditable |
| Decision then action (state can drift) | Atomic (same transaction) |
| Trust the agent's logs | Consensus verifies execution |

**The key insight:** Training is non-deterministic. Inference is deterministic. Same weights + same inputs = same output — and anyone can verify.

---

## Supported Model Architectures

| Template | Use case |
|----------|----------|
| `linear` | Simple regression, scoring |
| `softmax` | Multi-class classification |
| `naive_bayes` | Probabilistic classification |
| `mlp` | Single hidden layer |
| `mlp2` / `mlp3` | 2-3 hidden layers |
| `cnn1d` | Time series, sequences |
| `tiny_cnn` | Small image classification |
| `two_tower` | Similarity/embedding models |
| `tree` | Decision trees, GBDT |
| `custom` | Define your own schema |

Real architectures, not toy demos.

---

## Quick Start

### Hello World (8 Commands)

Deploy your first on-chain model in under 5 minutes:

```bash
# 1. Install
pip install frostbite-modelkit

# 2. Create linear regression model
cauldron init credit-scorer --template linear
cd credit-scorer

# 3. Train (or use sample weights)
cauldron train --data samples/credit_data.csv --epochs 10

# 4. Convert & upload
cauldron convert --input weights.pt --pack
cauldron upload --file weights.bin --cluster devnet

# 5. Test inference
cauldron input-write --data '{"income": 50000, "debt": 10000}'
cauldron invoke --instructions 10000
cauldron output
```

**Expected output:** Credit score between 300-850, computed on-chain, verifiable by anyone.

---

### 1. Install Cauldron

```bash
# Python (pip)
pip install frostbite-modelkit

# Or clone for development
git clone https://github.com/reflow-labs/cauldron
cd cauldron
pip install -e .
```

### 2. Initialize a Model Project

```bash
cauldron init my-model --template mlp
cd my-model
```

This creates:
- `frostbite-model.toml` — manifest defining schema, weights, build config
- `guest/` — guest program template
- `weights.bin` — placeholder for your weights

### 3. Train Your Model (Off-chain)

Use any training framework. Export weights to JSON, NPZ, PyTorch, or SafeTensors.

```python
# Example: simple MLP training with PyTorch
model = nn.Sequential(
    nn.Linear(input_dim, hidden_dim),
    nn.ReLU(),
    nn.Linear(hidden_dim, output_dim)
)
# ... train ...
torch.save(model.state_dict(), "weights.pt")
```

Or use Cauldron's built-in training harness:

```bash
cauldron train --manifest frostbite-model.toml --data data.csv \
  --template mlp --epochs 50 --calibrate-percentile 99.5
```

### 4. Convert and Pack Weights

```bash
# Convert from PyTorch/JSON/NPZ to quantized binary
cauldron convert --manifest frostbite-model.toml --input weights.pt --pack

# Optional: specify key mapping for state_dict
cauldron convert --manifest frostbite-model.toml --input weights.pt \
  --keymap w1=layer1.weight --keymap b1=layer1.bias
```

Cauldron quantizes weights to fixed-point and packs them for on-chain storage.

### 5. Build the Guest Program

```bash
cauldron build-guest --manifest frostbite-model.toml
```

Compiles the guest program for on-chain execution.

### 6. Upload to Solana

```bash
# Chunk weights if needed (for large models)
cauldron chunk --manifest frostbite-model.toml

# Upload to devnet
cauldron upload --file weights.bin --cluster devnet
```

For devnet testing, use the shared VM/RAM accounts (no SOL cost):

```bash
cauldron accounts init --manifest frostbite-model.toml \
  --vm EZcnmSFyxdm7qNHdt1xjVcgNh3GEs5cBErJRDWdcVvfq \
  --ram-file ram_accounts_devnet.txt
```

### 7. Invoke On-Chain

```bash
# Stage input
cauldron input-write --manifest frostbite-model.toml \
  --accounts frostbite-accounts.toml --data input.json

# Invoke inference
cauldron invoke --accounts frostbite-accounts.toml --instructions 50000

# Read output
cauldron output --manifest frostbite-model.toml \
  --accounts frostbite-accounts.toml
```

For low-latency execution (program + input pre-staged):

```bash
cauldron invoke --accounts frostbite-accounts.toml --fast --instructions 50000
```

---

## Manifest Reference

`frostbite-model.toml` defines your model:

```toml
[schema]
kind = "vector"           # vector, time_series, graph, custom
input_shape = [32]        # input dimensions
output_shape = [1]        # output dimensions

[weights]
path = "weights.bin"
quantization = "q16"      # q8, q16, q32, custom
scales = [1.0]            # quantization scales

[build]
template = "mlp"
hidden_dim = 64           # for MLP
has_bias = true

[abi]
entry = 16384             # guest entry point (>= 0x4000)
```

---

## Input Formats

**Vector/time_series:** JSON array or nested array

```json
[0.1, 0.2, 0.3, 0.4]
```

**Graph:** Nodes + edges

```json
{
  "nodes": [[0.1, 0.2], [0.3, 0.4]],
  "edges": [[0, 1], [1, 0]],
  "edge_features": [[1.0], [1.0]]
}
```

**Custom:** Raw bytes via `--input-bin` or `payload_hex`/`payload_base64` in JSON.

Pack input payloads:

```bash
cauldron input --manifest frostbite-model.toml --data input.json
```

---

## Devnet Resources

Shared accounts for testing (no SOL cost):

**VM accounts:**
- `EZcnmSFyxdm7qNHdt1xjVcgNh3GEs5cBErJRDWdcVvfq`
- `9b9ogpfyfpNejyA9Jzq8YSW8v2XepiPrSWbnZ9qS3LrY`
- `FgBoEPRtV31VerkVtAqYYMn53n9uxx1o9Rimjz8F5CdV`

**RAM accounts (writable):**
- `rw:CZq7wPvvQYaFiVXn6MTS1ZAAJathYH8N8a9UJTzkgnSP`
- `rw:ZHLUK4zdMKm3LgJqVo9fcb93g3dDUGzgrmQToeuK2cE`
- `rw:CaZNX6z3K8PBpcbduoiHsaVn6tw4itgAQKbNkygXSJJd`

⚠️ **Important:** These are shared, program-owned accounts. Anyone can read/write. **Data may be wiped at any time.** Don't store secrets, persistent state, or anything you can't recreate. This is scratch space for testing only.

---

## What You Can Build

**Verifiable scoring:** Deploy a model that evaluates inputs and produces auditable scores. Anyone can verify the computation.

**Gated execution:** Use inference as a precondition — transaction proceeds only if model output meets criteria.

**Atomic decisions:** Model sees current chain state, makes decision, action executes — all in one transaction.

**Auditable strategies:** Weights are on-chain. The logic is transparent. Trust comes from verifiability.

---

## Safety First

**Start on devnet.** Never test with real money.

**Use dry-run mode.** Simulate transactions before executing:
```bash
cauldron invoke --dry-run --instructions 50000
```

**Start small.** First deployment should be:
- Tiny model (< 1000 parameters)
- Minimal input (2-3 features)
- Low stakes (no real funds at risk)

**Verify before trusting.** Even "working" models can have edge cases. Test with:
- Boundary inputs (zeros, max values)
- Adversarial examples
- Real chain state (not just test data)

**Have an escape hatch.** Before deploying:
- Know how to pause/stop the model
- Keep backup of weights offline
- Document how to revert to previous version

**Rule of thumb:** If you wouldn't bet your own money on it, don't deploy it to mainnet.

---

## Troubleshooting

**"Weights too large"**

Chunk the weights:
```bash
cauldron chunk --manifest frostbite-model.toml --chunk-size 9000
cauldron upload --all "weights_chunk*.bin" --cluster devnet
```

**"Guest build failed"**

Ensure toolchain is installed:
```bash
rustup target add riscv64imac-unknown-none-elf
```

**"Transaction simulation failed"**

- Check wallet has SOL for fees
- Verify accounts exist and are initialized
- Review compute budget with `--instructions` flag

---

## Getting Access

Frostbite is currently on Solana devnet. Mainnet deployment coming soon.

For early access, integration support, or questions:

**Contact:** @12g8ge (X/Twitter)

---

## The Vision

Train with all your TDD, property tests, and feedback loops. Deploy weights on-chain. Execute with cryptographic verification.

**Non-deterministic training. Deterministic inference. Verifiable by anyone.**

🔮
