"""CLI entrypoint for ModelKit."""

from __future__ import annotations

import argparse
import base64
import json
import os
import platform
import secrets
import shutil
import subprocess
import sys
import struct
import tempfile
import urllib.request
from pathlib import Path

from .manifest import load_manifest
from .validate import raise_on_errors, validate_manifest, ValidationError
from .pack import pack_manifest
from .convert import load_and_convert
from .upload import upload_model_chunk, upload_all_chunks
from .input import write_input, load_payload_from_path, pack_input
from .guest import write_guest_config, build_guest
from .chunk import chunk_manifest, chunk_file
from .schema import schema_hash32, format_hash32, update_manifest_schema_hash
from .accounts import (
    load_accounts,
    write_accounts,
    parse_segments,
    resolve_pubkey,
    parse_vm_seed,
    resolve_authority_pubkey,
    segment_kind_code,
    derive_vm_pda,
    derive_segment_pda,
)
from .constants import MMU_VM_HEADER_SIZE, FBM1_MAGIC, ABI_VERSION, DTYPE_SIZES, DEFAULT_PROGRAM_ID

_TEMPLATE_LINEAR = """
[model]
id = "liquidity-linear"
version = "0.1.0"
abi_version = "fb-abi-1"
arch = "rv64imac"
endianness = "little"
vaddr_bits = 32
profile = "finance-int"

[abi]
entry = 0x4000
control_offset = 0x0000
control_size = 64
input_offset = 0x1000
input_max = 4096
output_offset = 0x2000
output_max = 256
scratch_min = 262144
alignment = 8
reserved_tail = 32

[schema]
type = "vector"

[schema.vector]
input_dtype = "i32"
input_shape = [64]
output_dtype = "i32"
output_shape = [1]

[validation]
mode = "minimal"

[build]
has_bias = true
stack_guard = 16384

[weights]
layout = "linear_i8_q16_v1"
quantization = "q8"
dtype = "i8"
scale = "q16"
header_format = "rvcd-v1"

[weights.scales]
w_scale_q16 = 65536

[[weights.blobs]]
name = "main"
file = "weights.bin"
hash = "sha256:REPLACE_ME"
size_bytes = 68
chunk_size = 9500000
data_offset = 12
segment_index = 1

[[segments]]
index = 0
kind = "scratch"
access = "rw"
source = "scratch"

[[segments]]
index = 1
kind = "weights"
access = "ro"
source = "weights:main"

[limits]
max_instructions = 1000000
cu_budget = 1400000
""".lstrip()


_TEMPLATE_SOFTMAX = """
[model]
id = "softmax-regression"
version = "0.1.0"
abi_version = "fb-abi-1"
arch = "rv64imac"
endianness = "little"
vaddr_bits = 32
profile = "finance-int"

[abi]
entry = 0x4000
control_offset = 0x0000
control_size = 64
input_offset = 0x1000
input_max = 4096
output_offset = 0x2000
output_max = 256
scratch_min = 262144
alignment = 8
reserved_tail = 32

[schema]
type = "vector"

[schema.vector]
input_dtype = "i32"
input_shape = [64]
output_dtype = "i32"
output_shape = [2]

[validation]
mode = "minimal"

[build]
has_bias = true
apply_softmax = true
stack_guard = 16384

[weights]
layout = "softmax_i8_q16_v1"
quantization = "q8"
dtype = "i8"
scale = "q16"
header_format = "rvcd-v1"

[weights.scales]
w_scale_q16 = 65536

[[weights.blobs]]
name = "main"
file = "weights.bin"
hash = "sha256:REPLACE_ME"
# Layout: W (i8 * output_dim * input_dim) + bias (i32 * output_dim)
size_bytes = 136
chunk_size = 9500000
data_offset = 12
segment_index = 1

[[segments]]
index = 0
kind = "scratch"
access = "rw"
source = "scratch"

[[segments]]
index = 1
kind = "weights"
access = "ro"
source = "weights:main"

[limits]
max_instructions = 1000000
cu_budget = 1400000
""".lstrip()


_TEMPLATE_NAIVE_BAYES = """
[model]
id = "naive-bayes"
version = "0.1.0"
abi_version = "fb-abi-1"
arch = "rv64imac"
endianness = "little"
vaddr_bits = 32
profile = "finance-int"

[abi]
entry = 0x4000
control_offset = 0x0000
control_size = 64
input_offset = 0x1000
input_max = 4096
output_offset = 0x2000
output_max = 256
scratch_min = 262144
alignment = 8
reserved_tail = 32

[schema]
type = "vector"

[schema.vector]
input_dtype = "i32"
input_shape = [64]
output_dtype = "i32"
output_shape = [2]

[validation]
mode = "minimal"

[build]
has_bias = true
apply_softmax = true
stack_guard = 16384

[weights]
layout = "naive_bayes_i8_q16_v1"
quantization = "q8"
dtype = "i8"
scale = "q16"
header_format = "rvcd-v1"

[weights.scales]
w_scale_q16 = 65536

[[weights.blobs]]
name = "main"
file = "weights.bin"
hash = "sha256:REPLACE_ME"
# Layout: W (i8 * output_dim * input_dim) + bias (i32 * output_dim)
size_bytes = 136
chunk_size = 9500000
data_offset = 12
segment_index = 1

[[segments]]
index = 0
kind = "scratch"
access = "rw"
source = "scratch"

[[segments]]
index = 1
kind = "weights"
access = "ro"
source = "weights:main"

[limits]
max_instructions = 1000000
cu_budget = 1400000
""".lstrip()


_TEMPLATE_MLP = """
[model]
id = "risk-mlp"
version = "0.1.0"
abi_version = "fb-abi-1"
arch = "rv64imac"
endianness = "little"
vaddr_bits = 32
profile = "finance-int"

[abi]
entry = 0x4000
control_offset = 0x0000
control_size = 64
input_offset = 0x1000
input_max = 4096
output_offset = 0x2000
output_max = 256
scratch_min = 262144
alignment = 8
reserved_tail = 32

[schema]
type = "vector"

[schema.vector]
input_dtype = "i32"
input_shape = [64]
output_dtype = "i32"
output_shape = [1]

[validation]
mode = "minimal"

[build]
hidden_dim = 32
hidden_offset = 0x3000
stack_guard = 16384

[weights]
layout = "mlp_i8_q16_v1"
quantization = "q8"
dtype = "i8"
scale = "q16"
header_format = "rvcd-v1"

[weights.scales]
w1_scale_q16 = 65536
w2_scale_q16 = 65536

[[weights.blobs]]
name = "main"
file = "weights.bin"
hash = "sha256:REPLACE_ME"
size_bytes = 2212
chunk_size = 9500000
data_offset = 12
segment_index = 1

[[segments]]
index = 0
kind = "scratch"
access = "rw"
source = "scratch"

[[segments]]
index = 1
kind = "weights"
access = "ro"
source = "weights:main"

[limits]
max_instructions = 1000000
cu_budget = 1400000
""".lstrip()


_TEMPLATE_MLP2 = """
[model]
id = "mlp-2"
version = "0.1.0"
abi_version = "fb-abi-1"
arch = "rv64imac"
endianness = "little"
vaddr_bits = 32
profile = "finance-int"

[abi]
entry = 0x4000
control_offset = 0x0000
control_size = 64
input_offset = 0x1000
input_max = 4096
output_offset = 0x2000
output_max = 256
scratch_min = 262144
alignment = 8
reserved_tail = 32

[schema]
type = "vector"

[schema.vector]
input_dtype = "i32"
input_shape = [64]
output_dtype = "i32"
output_shape = [1]

[validation]
mode = "minimal"

[build]
hidden_dim1 = 32
hidden_dim2 = 16
hidden_offset1 = 0x3000
hidden_offset2 = 0x3080
has_bias = true
stack_guard = 16384

[weights]
layout = "mlp2_i8_q16_v1"
quantization = "q8"
dtype = "i8"
scale = "q16"
header_format = "rvcd-v1"

[weights.scales]
w1_scale_q16 = 65536
w2_scale_q16 = 65536
w3_scale_q16 = 65536

[[weights.blobs]]
name = "main"
file = "weights.bin"
hash = "sha256:REPLACE_ME"
# Layout: W1 (i8 H1 x I) + B1 (i32 H1) + W2 (i8 H2 x H1) + B2 (i32 H2) + W3 (i8 O x H2) + B3 (i32 O)
size_bytes = 2772
chunk_size = 9500000
data_offset = 12
segment_index = 1

[[segments]]
index = 0
kind = "scratch"
access = "rw"
source = "scratch"

[[segments]]
index = 1
kind = "weights"
access = "ro"
source = "weights:main"

[limits]
max_instructions = 1000000
cu_budget = 1400000
""".lstrip()


_TEMPLATE_MLP3 = """
[model]
id = "mlp-3"
version = "0.1.0"
abi_version = "fb-abi-1"
arch = "rv64imac"
endianness = "little"
vaddr_bits = 32
profile = "finance-int"

[abi]
entry = 0x4000
control_offset = 0x0000
control_size = 64
input_offset = 0x1000
input_max = 4096
output_offset = 0x2000
output_max = 256
scratch_min = 262144
alignment = 8
reserved_tail = 32

[schema]
type = "vector"

[schema.vector]
input_dtype = "i32"
input_shape = [64]
output_dtype = "i32"
output_shape = [1]

[validation]
mode = "minimal"

[build]
hidden_dim1 = 32
hidden_dim2 = 16
hidden_dim3 = 8
hidden_offset1 = 0x3000
hidden_offset2 = 0x3080
hidden_offset3 = 0x30C0
has_bias = true
stack_guard = 16384

[weights]
layout = "mlp3_i8_q16_v1"
quantization = "q8"
dtype = "i8"
scale = "q16"
header_format = "rvcd-v1"

[weights.scales]
w1_scale_q16 = 65536
w2_scale_q16 = 65536
w3_scale_q16 = 65536
w4_scale_q16 = 65536

[[weights.blobs]]
name = "main"
file = "weights.bin"
hash = "sha256:REPLACE_ME"
# Layout: W1 (i8 H1 x I) + B1 (i32 H1) + W2 (i8 H2 x H1) + B2 (i32 H2) + W3 (i8 H3 x H2) + B3 (i32 H3) + W4 (i8 O x H3) + B4 (i32 O)
size_bytes = 2924
chunk_size = 9500000
data_offset = 12
segment_index = 1

[[segments]]
index = 0
kind = "scratch"
access = "rw"
source = "scratch"

[[segments]]
index = 1
kind = "weights"
access = "ro"
source = "weights:main"

[limits]
max_instructions = 1000000
cu_budget = 1400000
""".lstrip()


_TEMPLATE_CNN1D = """
[model]
id = "cnn1d-signal"
version = "0.1.0"
abi_version = "fb-abi-1"
arch = "rv64imac"
endianness = "little"
vaddr_bits = 32
profile = "finance-int"

[abi]
entry = 0x4000
control_offset = 0x0000
control_size = 64
input_offset = 0x1000
input_max = 4096
output_offset = 0x2000
output_max = 256
scratch_min = 262144
alignment = 8
reserved_tail = 32

[schema]
type = "time_series"

[schema.time_series]
input_dtype = "i32"
window = 32
features = 4
output_dtype = "i32"
output_shape = [1]

[validation]
mode = "minimal"

[build]
kernel_size = 3
stride = 1
out_channels = 8
conv_offset = 0x3000
has_bias = true
stack_guard = 16384

[weights]
layout = "cnn1d_i8_q16_v1"
quantization = "q8"
dtype = "i8"
scale = "q16"
header_format = "rvcd-v1"

[weights.scales]
w1_scale_q16 = 65536
w2_scale_q16 = 65536

[[weights.blobs]]
name = "main"
file = "weights.bin"
hash = "sha256:REPLACE_ME"
# Layout: W1 (i8 F x C x K) + B1 (i32 F) + W2 (i8 O x F) + B2 (i32 O)
size_bytes = 140
chunk_size = 9500000
data_offset = 12
segment_index = 1

[[segments]]
index = 0
kind = "scratch"
access = "rw"
source = "scratch"

[[segments]]
index = 1
kind = "weights"
access = "ro"
source = "weights:main"

[limits]
max_instructions = 1000000
cu_budget = 1400000
""".lstrip()


_TEMPLATE_TINY_CNN = """
[model]
id = "tiny-cnn"
version = "0.1.0"
abi_version = "fb-abi-1"
arch = "rv64imac"
endianness = "little"
vaddr_bits = 32
profile = "finance-int"

[abi]
entry = 0x4000
control_offset = 0x0000
control_size = 64
input_offset = 0x1000
input_max = 4096
output_offset = 0x2000
output_max = 256
scratch_min = 262144
alignment = 8
reserved_tail = 32

[schema]
type = "vector"

[schema.vector]
input_dtype = "i32"
input_shape = [28, 28]
output_dtype = "i32"
output_shape = [1]

[validation]
mode = "minimal"

[build]
input_height = 28
input_width = 28
kernel_size = 3
stride = 1
out_channels = 4
conv_offset = 0x3000
has_bias = true
stack_guard = 16384

[weights]
layout = "tiny_cnn_i8_q16_v1"
quantization = "q8"
dtype = "i8"
scale = "q16"
header_format = "rvcd-v1"

[weights.scales]
w1_scale_q16 = 65536
w2_scale_q16 = 65536

[[weights.blobs]]
name = "main"
file = "weights.bin"
hash = "sha256:REPLACE_ME"
# Layout: W1 (i8 F x K x K) + B1 (i32 F) + W2 (i8 O x F) + B2 (i32 O)
size_bytes = 60
chunk_size = 9500000
data_offset = 12
segment_index = 1

[[segments]]
index = 0
kind = "scratch"
access = "rw"
source = "scratch"

[[segments]]
index = 1
kind = "weights"
access = "ro"
source = "weights:main"

[limits]
max_instructions = 1000000
cu_budget = 1400000
""".lstrip()


_TEMPLATE_TREE = """
[model]
id = "tree-model"
version = "0.1.0"
abi_version = "fb-abi-1"
arch = "rv64imac"
endianness = "little"
vaddr_bits = 32
profile = "finance-int"

[abi]
entry = 0x4000
control_offset = 0x0000
control_size = 64
input_offset = 0x1000
input_max = 4096
output_offset = 0x2000
output_max = 256
scratch_min = 262144
alignment = 8
reserved_tail = 32

[schema]
type = "vector"

[schema.vector]
input_dtype = "i32"
input_shape = [64]
output_dtype = "i32"
output_shape = [1]

[validation]
mode = "minimal"

[build]
tree_count = 1
tree_node_count = 15
tree_stride = 300
stack_guard = 16384

[weights]
layout = "tree_q16_v1"
quantization = "custom"
dtype = "i32"
scale = "q16"
header_format = "rvcd-v1"

[[weights.blobs]]
name = "main"
file = "weights.bin"
hash = "sha256:REPLACE_ME"
# Layout: nodes packed as i32 (feature, threshold_q16, left, right, value_q16)
size_bytes = 300
chunk_size = 9500000
data_offset = 12
segment_index = 1

[[segments]]
index = 0
kind = "scratch"
access = "rw"
source = "scratch"

[[segments]]
index = 1
kind = "weights"
access = "ro"
source = "weights:main"

[limits]
max_instructions = 1000000
cu_budget = 1400000
""".lstrip()


_TEMPLATE_CUSTOM = """
[model]
id = "custom-model"
version = "0.1.0"
abi_version = "fb-abi-1"
arch = "rv64imac"
endianness = "little"
vaddr_bits = 32
profile = "finance-int"

[abi]
entry = 0x4000
control_offset = 0x0000
control_size = 64
input_offset = 0x1000
input_max = 4096
output_offset = 0x2000
output_max = 256
scratch_min = 262144
alignment = 8
reserved_tail = 32

[schema]
type = "custom"

[schema.custom]
input_blob_size = 1024
output_blob_size = 16
alignment = 8
layout_doc = "layout.md"

[validation]
mode = "minimal"

[build]
stack_guard = 16384

[[segments]]
index = 0
kind = "scratch"
access = "rw"
source = "scratch"

[limits]
max_instructions = 1000000
cu_budget = 1400000
""".lstrip()


_TEMPLATE_TWO_TOWER = """
[model]
id = "two-tower"
version = "0.1.0"
abi_version = "fb-abi-1"
arch = "rv64imac"
endianness = "little"
vaddr_bits = 32
profile = "finance-int"

[abi]
entry = 0x4000
control_offset = 0x0000
control_size = 64
input_offset = 0x1000
input_max = 4096
output_offset = 0x2000
output_max = 256
scratch_min = 262144
alignment = 8
reserved_tail = 32

[schema]
type = "vector"

[schema.vector]
input_dtype = "i32"
input_shape = [128]
output_dtype = "i32"
output_shape = [1]

[validation]
mode = "minimal"

[build]
tower_input_a = 64
tower_input_b = 64
embed_dim = 16
embed_offset = 0x3000
dot_shift = 16
has_bias = true
stack_guard = 16384

[weights]
layout = "two_tower_i8_q16_v1"
quantization = "q8"
dtype = "i8"
scale = "q16"
header_format = "rvcd-v1"

[weights.scales]
w1_scale_q16 = 65536
w2_scale_q16 = 65536

[[weights.blobs]]
name = "main"
file = "weights.bin"
hash = "sha256:REPLACE_ME"
# Layout: W1 (i8 E x A) + B1 (i32 E) + W2 (i8 E x B) + B2 (i32 E)
size_bytes = 2176
chunk_size = 9500000
data_offset = 12
segment_index = 1

[[segments]]
index = 0
kind = "scratch"
access = "rw"
source = "scratch"

[[segments]]
index = 1
kind = "weights"
access = "ro"
source = "weights:main"

[limits]
max_instructions = 1000000
cu_budget = 1400000
""".lstrip()


_GUEST_STUB = """
// Stub guest file. Re-run init with --copy-guest to include the full template.
""".lstrip()

_GUEST_CARGO_TOML = """
[package]
name = "frostbite-guest"
version = "0.1.0"
edition = "2021"

[profile.release]
opt-level = "z"
lto = true
panic = "abort"
""".lstrip()


_PROJECT_README = """
# Cauldron Model Project

Template: {template}

## Quickstart

{quickstart}

2) Validate the manifest
```
cauldron validate {manifest}
```

3) Build guest + upload weights
```
cauldron build-guest --manifest {manifest}
```

4) Upload weights + invoke (see repo docs/scripts)
- Upload: use Cauldron `upload` or the Rust example
- Invoke: call execute/invoke with your input payload

## Notes
- Inputs/outputs are Q16 i32 for finance-int templates
- Most templates use i8 weights with Q16 scales (tree uses i32 nodes);
  `convert` updates `[weights.scales]` when present
- `toolchain/` is vendored with the Frostbite guest SDK + linker assets
""".lstrip()

_PROJECT_QUICKSTART_CONVERT = """
1) Convert weights (JSON/NPZ/NPY/PT/Safetensors)
```
cauldron convert --manifest {manifest} --input weights.json --template {template} --pack
```
""".strip()

_PROJECT_QUICKSTART_CUSTOM = """
1) Prepare weights
- For custom schemas, build weights.bin manually or write a converter script.
- If you do have a linear/MLP weight set, use:
```
cauldron convert --manifest {manifest} --input weights.json --template linear --pack
```
""".strip()

_PROJECT_GITIGNORE = """
# Cauldron artifacts
weights.bin
weights_chunk*.bin
chunks/
guest/target/

# Common weight formats
weights.json
*.npz
*.npy
*.pt
*.pth
*.safetensors
""".lstrip()


def _write_weights_placeholder(manifest: dict, dest: "Path") -> None:
    weights = manifest.get("weights")
    if not isinstance(weights, dict):
        return
    layout = weights.get("layout")
    blobs = weights.get("blobs")
    if not isinstance(blobs, list):
        return
    for blob in blobs:
        if not isinstance(blob, dict):
            continue
        filename = blob.get("file")
        size_bytes = blob.get("size_bytes")
        if not isinstance(filename, str) or not filename:
            continue
        if not isinstance(size_bytes, int) or size_bytes <= 0:
            continue
        path = dest / filename
        if path.exists():
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            # Tree placeholders need a valid leaf sentinel (feature < 0) at node 0.
            # A zero-filled blob loops indefinitely in guest_tree and exits with ERR_SCHEMA.
            if isinstance(layout, str) and layout.startswith("tree_") and (size_bytes % 20) == 0:
                node_count = size_bytes // 20
                node = struct.pack("<iiiii", -1, 0, -1, -1, 0)
                for _ in range(node_count):
                    f.write(node)
            else:
                f.truncate(size_bytes)


def _find_template_dir(template: str) -> Path | None:
    base = Path(__file__).resolve().parent
    packaged = base / "templates" / f"guest_{template}"
    if packaged.exists():
        return packaged
    local_programs = base / "guest_programs" / f"model_{template}"
    if local_programs.exists():
        return local_programs
    repo_root = base.parent
    repo_template = repo_root / "guest_programs" / f"model_{template}"
    if repo_template.exists():
        return repo_template
    return None


def _copy_guest_template(template: str, dest: Path) -> bool:
    template_dir = _find_template_dir(template)
    if template_dir is None:
        return False
    shutil.copytree(template_dir, dest, dirs_exist_ok=True)
    return True


def _copy_toolchain_subset(dest: Path) -> bool:
    base = Path(__file__).resolve().parent
    repo_root = base.parent
    candidates = [repo_root / "toolchain", base / "toolchain"]
    toolchain = next((candidate for candidate in candidates if candidate.exists()), None)
    if toolchain is None:
        return False

    dest_toolchain = dest / "toolchain"
    if dest_toolchain.exists():
        return True

    sdk_src = toolchain / "rust" / "frostbite-sdk"
    build_src = toolchain / "scripts" / "frostbite-build.rs"
    ld_src = toolchain / "lib" / "frostbite.ld"
    crt_src = toolchain / "lib" / "crt0.c"
    alloc_src = toolchain / "lib" / "frostbite_alloc.c"
    softfloat_src = toolchain / "lib" / "frostbite_softfloat.c"

    if not sdk_src.exists() or not build_src.exists() or not ld_src.exists() or not crt_src.exists():
        return False

    (dest_toolchain / "rust").mkdir(parents=True, exist_ok=True)
    (dest_toolchain / "scripts").mkdir(parents=True, exist_ok=True)
    (dest_toolchain / "lib").mkdir(parents=True, exist_ok=True)
    (dest_toolchain / "include").mkdir(parents=True, exist_ok=True)

    shutil.copytree(sdk_src, dest_toolchain / "rust" / "frostbite-sdk", dirs_exist_ok=True)
    shutil.copy2(build_src, dest_toolchain / "scripts" / "frostbite-build.rs")
    shutil.copy2(ld_src, dest_toolchain / "lib" / "frostbite.ld")
    shutil.copy2(crt_src, dest_toolchain / "lib" / "crt0.c")
    include_src = toolchain / "include" / "frostbite.h"
    if include_src.exists():
        shutil.copy2(include_src, dest_toolchain / "include" / "frostbite.h")
    if alloc_src.exists():
        shutil.copy2(alloc_src, dest_toolchain / "lib" / "frostbite_alloc.c")
    if softfloat_src.exists():
        shutil.copy2(softfloat_src, dest_toolchain / "lib" / "frostbite_softfloat.c")
    return True

def _cmd_validate(args: argparse.Namespace) -> int:
    manifest = load_manifest(args.manifest)
    errors = validate_manifest(manifest)
    if errors:
        if args.json:
            for msg in errors:
                print(f"ERROR: {msg}")
        else:
            print("Manifest validation failed:\n")
            for msg in errors:
                print(f"- {msg}")
        return 1
    print("Manifest valid")
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    manifest = load_manifest(args.manifest)
    for key in ("model", "schema", "abi", "weights", "limits"):
        if key in manifest:
            print(f"[{key}]")
            print(manifest[key])
    return 0


def _cmd_init(args: argparse.Namespace) -> int:
    from pathlib import Path

    template = args.template
    dest = Path(args.path).resolve()
    if dest.exists() and any(dest.iterdir()):
        print(f"Destination not empty: {dest}")
        return 1

    dest.mkdir(parents=True, exist_ok=True)

    manifest_name = args.manifest
    manifest_path = dest / manifest_name

    copy_guest = True
    if args.stub:
        copy_guest = False
    elif args.copy_guest:
        copy_guest = True

    if template == "linear":
        manifest_path.write_text(_TEMPLATE_LINEAR)
    elif template == "softmax":
        manifest_path.write_text(_TEMPLATE_SOFTMAX)
    elif template == "naive_bayes":
        manifest_path.write_text(_TEMPLATE_NAIVE_BAYES)
    elif template == "two_tower":
        manifest_path.write_text(_TEMPLATE_TWO_TOWER)
    elif template == "mlp":
        manifest_path.write_text(_TEMPLATE_MLP)
    elif template == "mlp2":
        manifest_path.write_text(_TEMPLATE_MLP2)
    elif template == "mlp3":
        manifest_path.write_text(_TEMPLATE_MLP3)
    elif template == "cnn1d":
        manifest_path.write_text(_TEMPLATE_CNN1D)
    elif template == "tiny_cnn":
        manifest_path.write_text(_TEMPLATE_TINY_CNN)
    elif template == "tree":
        manifest_path.write_text(_TEMPLATE_TREE)
    elif template == "custom":
        manifest_path.write_text(_TEMPLATE_CUSTOM)
    else:
        print(f"Unknown template: {template}")
        return 1

    guest_dir = dest / "guest"
    if copy_guest:
        guest_dir.mkdir(parents=True, exist_ok=True)
        if not _copy_guest_template(template, guest_dir):
            print("Warning: guest template not packaged; writing stub instead")
            (guest_dir / "Cargo.toml").write_text(_GUEST_CARGO_TOML)
            (guest_dir / "src").mkdir(parents=True, exist_ok=True)
            (guest_dir / "src" / "main.rs").write_text(_GUEST_STUB)
        else:
            write_guest_config(manifest_path, guest_dir, template=template, schema_hash_mode="auto")
    else:
        guest_dir.mkdir(parents=True, exist_ok=True)
        (guest_dir / "Cargo.toml").write_text(_GUEST_CARGO_TOML)
        (guest_dir / "src").mkdir(parents=True, exist_ok=True)
        (guest_dir / "src" / "main.rs").write_text(_GUEST_STUB)

    readme_path = dest / "README.md"
    if not readme_path.exists():
        quickstart = _PROJECT_QUICKSTART_CONVERT
        if template == "custom":
            quickstart = _PROJECT_QUICKSTART_CUSTOM
        readme_path.write_text(
            _PROJECT_README.format(
                template=template,
                manifest=manifest_path.name,
                quickstart=quickstart.format(
                    template=template,
                    manifest=manifest_path.name,
                ),
            )
        )

    gitignore_path = dest / ".gitignore"
    if not gitignore_path.exists():
        gitignore_path.write_text(_PROJECT_GITIGNORE)

    if template == "custom":
        try:
            manifest = load_manifest(manifest_path)
            schema = manifest.get("schema", {}) if isinstance(manifest, dict) else {}
            custom = schema.get("custom", {}) if isinstance(schema, dict) else {}
            layout_doc = custom.get("layout_doc")
            if isinstance(layout_doc, str) and layout_doc:
                layout_path = dest / layout_doc
                if not layout_path.exists():
                    layout_path.parent.mkdir(parents=True, exist_ok=True)
                    layout_path.write_text("# Custom Layout\n\nDescribe your input/output blobs here.\n")
        except Exception:
            pass

    if not args.no_weights:
        manifest = load_manifest(manifest_path)
        _write_weights_placeholder(manifest, dest)

    if copy_guest:
        if not _copy_toolchain_subset(dest):
            print("Warning: toolchain subset not found; guest SDK build may fail")

    print(f"Initialized {template} model project in {dest}")
    print(f"Manifest: {manifest_path}")
    return 0


def _cmd_pack(args: argparse.Namespace) -> int:
    updates = pack_manifest(
        args.manifest,
        update_size=args.update_size,
        write=not args.dry_run,
        create_missing=args.create_missing,
    )
    if not updates:
        print("No weights blobs found; nothing to update.")
        return 0
    for update in updates:
        print(f"{update.name}: {update.file} -> {update.hash}")
        if args.update_size:
            print(f"  size_bytes = {update.size_bytes}")
    if args.dry_run:
        print("Dry run: manifest not modified")
    return 0


def _parse_keymap(items: list[str] | None) -> dict[str, str] | None:
    if not items:
        return None
    mapping: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise ValueError("--keymap entries must be in dst=src form")
        dest, src = item.split("=", 1)
        dest = dest.strip()
        src = src.strip()
        if not dest or not src:
            raise ValueError("--keymap entries must be in dst=src form")
        mapping[dest] = src
    return mapping


def _load_pubkey_file(path: str) -> str:
    contents = Path(path).read_text()
    for line in contents.splitlines():
        trimmed = line.strip()
        if not trimmed or trimmed.startswith("#"):
            continue
        key_str = trimmed.strip()
        if ":" in key_str:
            key_str = key_str.split(":", 1)[1].strip()
        if key_str:
            return key_str
    raise ValueError(f"No pubkey found in {path}")


def _load_mapped_file(path: str, default_writable: bool) -> list[dict[str, str | bool]]:
    contents = Path(path).read_text()
    out: list[dict[str, str | bool]] = []
    for line in contents.splitlines():
        trimmed = line.strip()
        if not trimmed or trimmed.startswith("#"):
            continue
        writable = default_writable
        key_str = trimmed
        if trimmed.startswith("ro:"):
            writable = False
            key_str = trimmed[3:].strip()
        elif trimmed.startswith("rw:"):
            writable = True
            key_str = trimmed[3:].strip()
        if not key_str:
            raise ValueError(f"Empty pubkey entry in {path}")
        out.append({"pubkey": key_str, "writable": writable})
    return out


def _resolve_accounts_path(accounts_path: str, raw_path: str) -> str:
    candidate = Path(raw_path).expanduser()
    if candidate.is_absolute():
        return str(candidate)
    return str((Path(accounts_path).resolve().parent / candidate).resolve())


def _validate_vm_authority_binding(accounts_path: str, vm: dict[str, object]) -> None:
    authority_raw = vm.get("authority")
    authority_keypair_raw = vm.get("authority_keypair")
    if not isinstance(authority_raw, str) or not authority_raw:
        return
    if not isinstance(authority_keypair_raw, str) or not authority_keypair_raw:
        return

    authority_keypair_pubkey = resolve_pubkey(
        {"keypair": _resolve_accounts_path(accounts_path, authority_keypair_raw)}
    )
    if authority_keypair_pubkey and authority_keypair_pubkey != authority_raw:
        raise ValueError(
            "vm.authority does not match vm.authority_keypair pubkey; "
            "update accounts file or signer path"
        )


def _apply_accounts_env(env: dict[str, str], accounts_path: str, require_weights_keypair: bool) -> dict[str, str]:
    accounts = load_accounts(accounts_path)
    cluster = accounts.get("cluster") if isinstance(accounts.get("cluster"), dict) else {}
    if isinstance(cluster.get("rpc_url"), str) and "FROSTBITE_RPC_URL" not in env:
        env["FROSTBITE_RPC_URL"] = cluster["rpc_url"]
    if isinstance(cluster.get("payer"), str) and "FROSTBITE_PAYER_KEYPAIR" not in env:
        env["FROSTBITE_PAYER_KEYPAIR"] = _resolve_accounts_path(accounts_path, cluster["payer"])
    if "FROSTBITE_PROGRAM_ID" not in env:
        if isinstance(cluster.get("program_id"), str):
            env["FROSTBITE_PROGRAM_ID"] = cluster["program_id"]
        else:
            env["FROSTBITE_PROGRAM_ID"] = DEFAULT_PROGRAM_ID

    vm = accounts.get("vm") if isinstance(accounts.get("vm"), dict) else {}
    _validate_vm_authority_binding(accounts_path, vm)
    authority_keypair_path: str | None = None
    if isinstance(vm.get("authority_keypair"), str) and vm.get("authority_keypair"):
        authority_keypair_path = _resolve_accounts_path(accounts_path, vm["authority_keypair"])
        env["FROSTBITE_AUTHORITY_KEYPAIR"] = authority_keypair_path
    if "FROSTBITE_PAYER_KEYPAIR" not in env:
        if authority_keypair_path:
            env["FROSTBITE_PAYER_KEYPAIR"] = authority_keypair_path

    segments = parse_segments(accounts)
    weights = [seg for seg in segments if seg.kind.strip().lower() == "weights"]
    if weights:
        if len(weights) > 1:
            raise ValueError("accounts file has multiple weights segments; single-account mode only")
        seg = weights[0]
        legacy_env_override = env.get("FROSTBITE_CHUNK_KEYPAIR") or env.get("FROSTBITE_WEIGHTS_KEYPAIR")
        vm_seed = parse_vm_seed(vm)
        if vm_seed is not None:
            if legacy_env_override:
                raise ValueError(
                    "vm.seed enables PDA mode; remove FROSTBITE_CHUNK_KEYPAIR/FROSTBITE_WEIGHTS_KEYPAIR override"
                )
            if seg.keypair:
                raise ValueError(
                    "vm.seed enables PDA mode; remove weights segment keypair and use derived PDA metadata"
                )
            program_id = env.get("FROSTBITE_PROGRAM_ID", DEFAULT_PROGRAM_ID)
            authority_pubkey = resolve_authority_pubkey(
                accounts,
                authority_keypair_override=authority_keypair_path or env.get("FROSTBITE_PAYER_KEYPAIR"),
            )
            if not authority_pubkey:
                raise ValueError(
                    "PDA upload requires authority pubkey; set vm.authority, vm.authority_keypair, "
                    "cluster.payer, or --payer"
                )
            payer_pubkey = None
            if authority_keypair_path is None and "FROSTBITE_PAYER_KEYPAIR" in env:
                payer_pubkey = resolve_pubkey({"keypair": env["FROSTBITE_PAYER_KEYPAIR"]})
            if authority_keypair_path is None and payer_pubkey and authority_pubkey != payer_pubkey:
                raise ValueError(
                    "PDA upload authority differs from payer signer; set vm.authority_keypair "
                    "or use --payer that matches vm.authority"
                )
            env["FROSTBITE_AUTHORITY_PUBKEY"] = authority_pubkey
            env["FROSTBITE_UPLOAD_MODE"] = "pda"
            env["FROSTBITE_VM_SEED"] = str(vm_seed)
            env["FROSTBITE_SEGMENT_KIND"] = "weights"
            if seg.slot != 1:
                raise ValueError("PDA mode requires weights segment at slot 1")
            env["FROSTBITE_SEGMENT_SLOT"] = str(seg.slot)
            derived_vm_pubkey = derive_vm_pda(program_id, authority_pubkey, vm_seed)
            configured_vm_pubkey = resolve_pubkey(vm)
            if configured_vm_pubkey and configured_vm_pubkey != derived_vm_pubkey:
                raise ValueError(
                    "vm.pubkey does not match derived VM PDA for vm.seed/authority; "
                    "remove vm.pubkey or fix vm.seed/authority"
                )
            env["FROSTBITE_VM_PUBKEY"] = derived_vm_pubkey

            seg_pubkey = seg.pubkey or (
                resolve_pubkey({"keypair": _resolve_accounts_path(accounts_path, seg.keypair)}) if seg.keypair else None
            )
            kind_code = segment_kind_code(seg.kind)
            if kind_code is None:
                raise ValueError("weights segment has unsupported kind metadata")
            derived_segment_pubkey = derive_segment_pda(
                program_id,
                authority_pubkey,
                vm_seed,
                kind_code,
                seg.slot,
            )
            if seg_pubkey and seg_pubkey != derived_segment_pubkey:
                raise ValueError(
                    "weights segment pubkey does not match derived PDA for vm.seed/authority/slot; "
                    "remove segment pubkey/keypair or fix metadata"
                )
            env["FROSTBITE_SEGMENT_PUBKEY"] = derived_segment_pubkey
            return env

        if legacy_env_override:
            return env
        if seg.keypair:
            env["FROSTBITE_CHUNK_KEYPAIR"] = _resolve_accounts_path(accounts_path, seg.keypair)
            return env
        if require_weights_keypair:
            raise ValueError("weights segment requires keypair for legacy upload or vm.seed for PDA upload")
    elif require_weights_keypair:
        raise ValueError("accounts file missing weights segment")
    return env


def _accounts_segment_metas(
    accounts_path: str,
    *,
    program_id_override: str | None = None,
    payer_override: str | None = None,
) -> tuple[dict[str, str | None], list[str]]:
    accounts = load_accounts(accounts_path)
    cluster = accounts.get("cluster") if isinstance(accounts.get("cluster"), dict) else {}
    vm = accounts.get("vm") if isinstance(accounts.get("vm"), dict) else {}
    _validate_vm_authority_binding(accounts_path, vm)
    program_id = program_id_override or (
        cluster.get("program_id") if isinstance(cluster.get("program_id"), str) else DEFAULT_PROGRAM_ID
    )
    payer_keypair = payer_override
    if not payer_keypair and isinstance(cluster.get("payer"), str):
        payer_keypair = _resolve_accounts_path(accounts_path, cluster["payer"])
    authority_override = payer_keypair
    if isinstance(vm.get("authority_keypair"), str) and vm.get("authority_keypair"):
        authority_override = _resolve_accounts_path(accounts_path, vm["authority_keypair"])

    vm_seed = parse_vm_seed(vm)
    authority_pubkey = resolve_authority_pubkey(accounts, authority_keypair_override=authority_override)
    vm_pubkey = resolve_pubkey(vm)
    if vm_seed is not None:
        if not authority_pubkey:
            raise ValueError("Unable to derive VM PDA: missing authority pubkey")
        expected_vm_pda = derive_vm_pda(program_id, authority_pubkey, vm_seed)
        if vm_pubkey and vm_pubkey != expected_vm_pda:
            raise ValueError(
                "vm.pubkey does not match derived VM PDA for vm.seed/authority; "
                "remove vm.pubkey or fix vm.seed/authority"
            )
        vm_pubkey = expected_vm_pda
    if not vm_pubkey:
        raise ValueError("accounts file missing vm pubkey/keypair (or vm.seed + authority)")

    segments = parse_segments(accounts)
    if not segments:
        raise ValueError("accounts file has no segments")

    # Return cluster info + ordered mapped account list (segment order)
    mapped: list[tuple[int, bool, str]] = []
    for seg in segments:
        pubkey = seg.pubkey or (
            resolve_pubkey({"keypair": _resolve_accounts_path(accounts_path, seg.keypair)}) if seg.keypair else None
        )
        if vm_seed is not None:
            kind_code = segment_kind_code(seg.kind)
            if kind_code is None:
                raise ValueError(
                    f"Unable to derive segment {seg.index}: unsupported kind '{seg.kind}' (expected weights|ram)"
                )
            if seg.slot == 1 and kind_code != 1:
                raise ValueError("PDA mode requires a weights segment at slot 1")
            if kind_code == 1 and seg.slot != 1:
                raise ValueError("PDA mode supports weights only at slot 1")
            if not (1 <= seg.slot <= 15):
                raise ValueError(
                    f"Unable to derive segment {seg.index}: slot {seg.slot} is out of range (1..15)"
                )
            expected_segment_pda = derive_segment_pda(program_id, authority_pubkey, vm_seed, kind_code, seg.slot)
            if pubkey and pubkey != expected_segment_pda:
                raise ValueError(
                    f"segment {seg.index} pubkey does not match derived PDA for vm.seed/authority/slot; "
                    "remove segment pubkey/keypair or fix metadata"
                )
            pubkey = expected_segment_pda
            expected_writable = kind_code == 2  # weights=1 readonly, ram=2 writable
            if seg.writable != expected_writable:
                access_mode = "writable" if expected_writable else "readonly"
                raise ValueError(
                    f"segment {seg.index} ({seg.kind}) must be {access_mode} in PDA mode; "
                    "fix segment writable metadata"
                )
        if not pubkey:
            raise ValueError(f"segment {seg.index} missing pubkey/keypair (or derivation metadata)")
        sort_key = seg.slot if vm_seed is not None else seg.index
        mapped.append((sort_key, seg.writable, pubkey))
    mapped.sort(key=lambda item: item[0])
    if vm_seed is not None:
        seen_slots: set[int] = set()
        for slot, _, _ in mapped:
            if slot in seen_slots:
                raise ValueError(
                    f"duplicate segment slot {slot} in PDA mode; each mapped account must use a unique slot"
                )
            seen_slots.add(slot)
        for expected_slot, (actual_slot, _, _) in enumerate(mapped, start=1):
            if actual_slot != expected_slot:
                raise ValueError(
                    "PDA execute requires contiguous segment slots starting at 1; "
                    f"missing slot {expected_slot} before configured slot {actual_slot}"
                )

    return {
        "rpc_url": cluster.get("rpc_url"),
        "program_id": program_id,
        "payer": payer_keypair or cluster.get("payer"),
        "vm_pubkey": vm_pubkey,
        "authority_pubkey": authority_pubkey,
        "vm_seed": str(vm_seed) if vm_seed is not None else None,
    }, [f"{'rw' if writable else 'ro'}:{pubkey}" for _, writable, pubkey in mapped]


def _cmd_convert(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest)
    input_path = Path(args.input)
    output_path = Path(args.output) if args.output else None
    keymap = _parse_keymap(args.keymap)
    load_and_convert(
        manifest_path=manifest_path,
        input_path=input_path,
        template=args.template,
        output_path=output_path,
        scale_q16=args.scale_q16,
        w1_scale_q16=args.w1_scale_q16,
        w2_scale_q16=args.w2_scale_q16,
        w3_scale_q16=args.w3_scale_q16,
        w4_scale_q16=args.w4_scale_q16,
        update_manifest=not args.no_update_manifest,
        input_dim_override=args.input_dim,
        output_dim_override=args.output_dim,
        hidden_dim_override=args.hidden_dim,
        hidden_dim1_override=args.hidden_dim1,
        hidden_dim2_override=args.hidden_dim2,
        hidden_dim3_override=args.hidden_dim3,
        bias=not args.no_bias,
        keymap=keymap,
        input_dim_a_override=args.input_dim_a,
        input_dim_b_override=args.input_dim_b,
        embed_dim_override=args.embed_dim,
        tree_count_override=args.tree_count,
        tree_node_count_override=args.tree_node_count,
    )
    if args.pack:
        pack_manifest(
            manifest_path,
            update_size=True,
            write=True,
            create_missing=False,
        )
        print("Weights written and manifest packed")
    else:
        print("Weights written")
    return 0


def _cmd_build_guest(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest)
    guest_dir = Path(args.guest) if args.guest else manifest_path.parent / "guest"
    manifest = load_manifest(manifest_path)
    errors = validate_manifest(manifest)
    if errors:
        print("Manifest validation failed:\n")
        for msg in errors:
            print(f"- {msg}")
        return 1
    write_guest_config(
        manifest_path,
        guest_dir,
        template=args.template,
        schema_hash_mode=args.schema_hash,
    )
    if args.no_build:
        print(f"Config written: {guest_dir / 'src' / 'config.rs'}")
        return 0
    rc = build_guest(guest_dir, target=args.target, release=not args.debug)
    if rc != 0:
        print(f"Guest build failed with code {rc}")
        return rc
    print("Guest build complete")
    return 0


def _cmd_chunk(args: argparse.Namespace) -> int:
    out_dir = Path(args.out_dir) if args.out_dir else None
    if args.manifest:
        results = chunk_manifest(Path(args.manifest), args.chunk_size, out_dir)
        for result in results:
            print(f"Chunked {result.source} -> {len(result.chunks)} files")
        return 0
    if args.file:
        if args.chunk_size is None:
            print("chunk requires --chunk-size when using --file")
            return 1
        if out_dir is None:
            out_dir = Path(args.file).resolve().parent
        result = chunk_file(Path(args.file), args.chunk_size, out_dir)
        print(f"Chunked {result.source} -> {len(result.chunks)} files")
        return 0
    print("chunk requires --manifest or --file")
    return 1


def _cmd_schema_hash(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest)
    manifest = load_manifest(manifest_path)
    value = schema_hash32(manifest)
    hash_str = format_hash32(value)
    print(hash_str)
    if args.update_manifest:
        update_manifest_schema_hash(manifest_path, hash_str)
        print("Updated manifest schema_hash32")
    return 0


def _resolve_input_header(manifest: dict, args: argparse.Namespace) -> bool:
    if args.header and args.no_header:
        raise ValueError("--header and --no-header are mutually exclusive")
    if args.header:
        return True
    if args.no_header:
        return False
    validation = manifest.get("validation") if isinstance(manifest, dict) else None
    return isinstance(validation, dict) and validation.get("mode") == "guest"


def _cmd_input(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest)
    manifest = load_manifest(manifest_path)

    include_header = _resolve_input_header(manifest, args)

    payload = None
    if args.input_bin:
        payload = Path(args.input_bin).read_bytes()
    elif args.data:
        payload = load_payload_from_path(Path(args.data))
    else:
        raise ValueError("input requires --data or --input-bin")

    output_path = Path(args.out) if args.out else manifest_path.parent / "input.bin"

    write_input(
        manifest_path=manifest_path,
        payload=payload,
        output_path=output_path,
        include_header=include_header,
        include_crc=args.crc,
        schema_hash_mode=args.schema_hash,
    )

    print(f"Wrote input payload: {output_path}")
    return 0


def _build_control_block(
    control_size: int,
    input_ptr: int,
    input_len: int,
    output_ptr: int,
    output_len: int,
) -> bytes:
    if control_size < 64:
        raise ValueError("abi.control_size must be >= 64")
    for name, value in (
        ("input_ptr", input_ptr),
        ("input_len", input_len),
        ("output_ptr", output_ptr),
        ("output_len", output_len),
    ):
        if value < 0 or value > 0xFFFF_FFFF:
            raise ValueError(f"{name} must fit in u32")

    buf = bytearray(control_size)
    struct.pack_into(
        "<IIIIIIIIIIIIQ",
        buf,
        0,
        FBM1_MAGIC,
        ABI_VERSION,
        0,
        0,
        input_ptr,
        input_len,
        output_ptr,
        output_len,
        0,
        0,
        0,
        0,
        0,
    )
    return bytes(buf)


def _write_account(
    env: dict[str, str],
    account_pubkey: str,
    offset: int,
    payload_path: Path,
    chunk_size: int | None,
) -> int:
    if offset < 0 or offset > 0xFFFF_FFFF:
        raise ValueError("offset must fit in u32")
    rust_tools = Path(__file__).resolve().parent / "rust_tools"
    payload_path = payload_path.resolve()
    cmd = [
        "cargo",
        "run",
        "--bin",
        "write_account",
        "--",
        account_pubkey,
        str(offset),
        str(payload_path),
    ]
    if chunk_size:
        cmd.extend(["--chunk-size", str(chunk_size)])
    print("Running:", " ".join(cmd))
    proc = subprocess.run(cmd, env=env, cwd=str(rust_tools))
    return proc.returncode


def _cmd_input_write(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest)
    manifest = load_manifest(manifest_path)

    include_header = _resolve_input_header(manifest, args)
    schema_type = None
    if isinstance(manifest.get("schema"), dict):
        schema_type = manifest["schema"].get("type")

    payload = None
    if args.input_bin:
        if schema_type != "custom":
            raise ValueError("--input-bin is only supported for custom schemas")
        payload = Path(args.input_bin).read_bytes()
    elif args.data:
        payload = load_payload_from_path(Path(args.data))
    else:
        raise ValueError("input-write requires --data or --input-bin")

    payload_bytes = pack_input(
        manifest_path,
        payload,
        include_header=include_header,
        include_crc=args.crc,
        schema_hash_mode=args.schema_hash,
    )

    abi = manifest.get("abi") if isinstance(manifest, dict) else None
    if not isinstance(abi, dict):
        raise ValueError("manifest missing abi table")

    def _require_int(key: str) -> int:
        val = abi.get(key)
        if not isinstance(val, int):
            raise ValueError(f"abi.{key} must be an integer")
        return val

    control_offset = _require_int("control_offset")
    control_size = _require_int("control_size")
    input_offset = _require_int("input_offset")
    input_max = _require_int("input_max")
    output_offset = _require_int("output_offset")
    output_max = _require_int("output_max")

    if len(payload_bytes) > input_max:
        raise ValueError(f"input payload is {len(payload_bytes)} bytes, exceeds abi.input_max {input_max}")
    if output_max <= 0:
        raise ValueError("abi.output_max must be positive")

    control_bytes = _build_control_block(
        control_size,
        input_offset,
        len(payload_bytes),
        output_offset,
        0,
    )

    info, _ = _accounts_segment_metas(
        args.accounts,
        program_id_override=args.program_id,
        payer_override=args.payer,
    )
    vm_pubkey = info.get("vm_pubkey")
    if not vm_pubkey:
        raise ValueError("accounts file missing vm pubkey")

    env = os.environ.copy()
    if args.rpc_url:
        env["FROSTBITE_RPC_URL"] = args.rpc_url
    elif info.get("rpc_url"):
        env["FROSTBITE_RPC_URL"] = info["rpc_url"]
    if args.payer:
        env["FROSTBITE_PAYER_KEYPAIR"] = args.payer
    elif info.get("payer"):
        env["FROSTBITE_PAYER_KEYPAIR"] = info["payer"]
    if args.program_id:
        env["FROSTBITE_PROGRAM_ID"] = args.program_id
    elif info.get("program_id"):
        env["FROSTBITE_PROGRAM_ID"] = info["program_id"]
    elif "FROSTBITE_PROGRAM_ID" not in env:
        env["FROSTBITE_PROGRAM_ID"] = DEFAULT_PROGRAM_ID

    control_write_offset = MMU_VM_HEADER_SIZE + control_offset
    input_write_offset = MMU_VM_HEADER_SIZE + input_offset

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        input_path = tmp_path / "input.bin"
        control_path = tmp_path / "control.bin"
        input_path.write_bytes(payload_bytes)
        control_path.write_bytes(control_bytes)

        print(
            f"Writing input ({len(payload_bytes)} bytes) to VM {vm_pubkey} "
            f"@ 0x{input_write_offset:X}"
        )
        rc = _write_account(env, vm_pubkey, input_write_offset, input_path, args.chunk_size)
        if rc != 0:
            return rc

        print(f"Writing control block ({len(control_bytes)} bytes) @ 0x{control_write_offset:X}")
        rc = _write_account(env, vm_pubkey, control_write_offset, control_path, args.chunk_size)
        if rc != 0:
            return rc

    print("Input staged in VM scratch.")
    return 0


def _rpc_request(url: str, method: str, params: list) -> dict:
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode())
    if "error" in data:
        raise ValueError(f"RPC error: {data['error']}")
    return data.get("result", {})


def _fetch_account_data(rpc_url: str, pubkey: str) -> bytes:
    result = _rpc_request(rpc_url, "getAccountInfo", [pubkey, {"encoding": "base64"}])
    value = result.get("value") if isinstance(result, dict) else None
    if value is None:
        raise ValueError("Account not found")
    data = value.get("data") if isinstance(value, dict) else None
    if not data:
        raise ValueError("Account data missing")
    if isinstance(data, list) and data:
        b64 = data[0]
    elif isinstance(data, str):
        b64 = data
    else:
        raise ValueError("Unexpected account data format")
    return base64.b64decode(b64)


def _parse_control_block(scratch: bytes, control_offset: int) -> dict[str, int]:
    if control_offset < 0 or control_offset + 64 > len(scratch):
        raise ValueError("control block out of bounds")
    fields = struct.unpack_from("<IIIIIIIIIIIIQ", scratch, control_offset)
    keys = [
        "magic",
        "abi_version",
        "flags",
        "status",
        "input_ptr",
        "input_len",
        "output_ptr",
        "output_len",
        "scratch_ptr",
        "scratch_len",
        "user_ptr",
        "user_len",
        "reserved0",
    ]
    return dict(zip(keys, fields))


def _schema_output_info(manifest: dict) -> tuple[str | None, int | None]:
    schema = manifest.get("schema")
    if not isinstance(schema, dict):
        return None, None
    stype = schema.get("type")
    if stype == "vector" and isinstance(schema.get("vector"), dict):
        out_dtype = schema["vector"].get("output_dtype")
        out_shape = schema["vector"].get("output_shape")
    elif stype == "time_series" and isinstance(schema.get("time_series"), dict):
        out_dtype = schema["time_series"].get("output_dtype")
        out_shape = schema["time_series"].get("output_shape")
    elif stype == "graph" and isinstance(schema.get("graph"), dict):
        out_dtype = schema["graph"].get("output_dtype")
        out_shape = schema["graph"].get("output_shape")
    elif stype == "custom" and isinstance(schema.get("custom"), dict):
        out_dtype = "u8"
        out_shape = [schema["custom"].get("output_blob_size")]
    else:
        return None, None

    if not isinstance(out_dtype, str):
        out_dtype = None
    count = None
    if isinstance(out_shape, list) and out_shape:
        try:
            count = 1
            for dim in out_shape:
                count *= int(dim)
        except (TypeError, ValueError):
            count = None
    return out_dtype, count


def _decode_output(data: bytes, fmt: str, count: int | None) -> str:
    if fmt == "hex":
        return data.hex()
    if fmt == "raw":
        return "<raw>"
    if fmt == "u8":
        return json.dumps(list(data))

    struct_map = {"i32": "i", "u32": "I", "f32": "f", "i16": "h", "i8": "b", "u8": "B"}
    fmt_char = struct_map.get(fmt)
    if fmt_char is None:
        return data.hex()
    item_size = DTYPE_SIZES.get(fmt)
    if not item_size:
        return data.hex()

    max_items = len(data) // item_size
    if count is None or count > max_items:
        count = max_items
    if count <= 0:
        return "[]"
    fmt_str = "<" + fmt_char * count
    values = struct.unpack_from(fmt_str, data, 0)
    return json.dumps(list(values))


def _cmd_output(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest)
    manifest = load_manifest(manifest_path)

    abi = manifest.get("abi") if isinstance(manifest, dict) else None
    if not isinstance(abi, dict):
        raise ValueError("manifest missing abi table")
    control_offset = abi.get("control_offset")
    input_offset = abi.get("input_offset")
    output_offset = abi.get("output_offset")
    output_max = abi.get("output_max")
    if not isinstance(control_offset, int) or not isinstance(output_offset, int) or not isinstance(output_max, int):
        raise ValueError("abi.control_offset/output_offset/output_max must be integers")

    info, _ = _accounts_segment_metas(args.accounts)
    rpc_url = args.rpc_url or info.get("rpc_url") or "http://127.0.0.1:8899"
    vm_pubkey = info.get("vm_pubkey")
    if not vm_pubkey:
        raise ValueError("accounts file missing vm pubkey")

    data = _fetch_account_data(rpc_url, vm_pubkey)
    if len(data) < MMU_VM_HEADER_SIZE:
        raise ValueError("VM account data too small")
    scratch = data[MMU_VM_HEADER_SIZE:]

    control = _parse_control_block(scratch, control_offset)
    output_len = int(control.get("output_len", 0))
    if output_len == 0 and args.use_max:
        output_len = int(output_max)

    output_start = output_offset
    output_end = output_start + output_len
    if output_end > len(scratch):
        raise ValueError("output buffer out of bounds")

    output_bytes = scratch[output_start:output_end]
    if args.out:
        Path(args.out).write_bytes(output_bytes)

    out_dtype, out_count = _schema_output_info(manifest)
    fmt = args.format
    if fmt == "auto":
        fmt = out_dtype or "hex"
    decoded = _decode_output(output_bytes, fmt, out_count)

    print("Output:")
    print(f"  rpc_url: {rpc_url}")
    print(f"  vm: {vm_pubkey}")
    print(f"  status: {control.get('status', 0)}")
    print(f"  output_len: {output_len}")
    print(f"  input_ptr: 0x{control.get('input_ptr', 0):X}")
    print(f"  output_ptr: 0x{control.get('output_ptr', 0):X}")
    if output_len == 0:
        print("  output: <empty>")
    else:
        print(f"  output_format: {fmt}")
        print(f"  output: {decoded}")
    return 0


_CLUSTER_URLS = {
    "localnet": "http://127.0.0.1:8899",
    "devnet": "https://api.devnet.solana.com",
    "mainnet": "https://api.mainnet-beta.solana.com",
}


def _load_solana_cli_config() -> dict[str, str]:
    path = os.environ.get("SOLANA_CONFIG") or os.environ.get("SOLANA_CONFIG_FILE")
    if path:
        cfg_path = Path(path)
    else:
        cfg_path = Path.home() / ".config" / "solana" / "cli" / "config.yml"
    try:
        text = cfg_path.read_text()
    except OSError:
        return {}
    cfg: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key:
            cfg[key] = value
    return cfg


def _resolve_run_onchain() -> str:
    env_path = os.environ.get("FROSTBITE_RUN_ONCHAIN")
    if env_path:
        return env_path
    package_dir = Path(__file__).resolve().parent
    runner = _runner_filename()
    tag = _platform_tag()
    if tag:
        bundled = package_dir / "bin" / tag / runner
        if bundled.exists():
            return str(bundled)
        toolchain_bin = package_dir / "toolchain" / "bin" / tag / runner
        if toolchain_bin.exists():
            return str(toolchain_bin)
    bundled = package_dir / "bin" / runner
    if bundled.exists():
        return str(bundled)
    toolchain_bin = package_dir / "toolchain" / "bin" / runner
    if toolchain_bin.exists():
        return str(toolchain_bin)
    return "frostbite-run-onchain"


def _platform_tag() -> str | None:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "darwin":
        if machine in {"arm64", "aarch64"}:
            return "darwin-arm64"
        if machine in {"x86_64", "amd64"}:
            return "darwin-x64"
    if system == "linux":
        if machine in {"x86_64", "amd64"}:
            return "linux-x64"
        if machine in {"arm64", "aarch64"}:
            return "linux-arm64"
    if system == "windows":
        if machine in {"x86_64", "amd64"}:
            return "windows-x64"
    return None


def _runner_filename() -> str:
    if platform.system().lower() == "windows":
        return "frostbite-run-onchain.exe"
    return "frostbite-run-onchain"


def _build_upload_env(args: argparse.Namespace) -> dict[str, str]:
    env = os.environ.copy()
    solana_cfg = _load_solana_cli_config()

    rpc_url = args.rpc_url
    if not rpc_url and args.cluster:
        if args.cluster == "surfpool":
            rpc_url = env.get("SURFPOOL_RPC_URL") or env.get("FROSTBITE_SURFPOOL_RPC_URL")
            if not rpc_url:
                raise ValueError("surfpool requires --rpc-url or SURFPOOL_RPC_URL")
        else:
            rpc_url = _CLUSTER_URLS.get(args.cluster)
    if not rpc_url:
        rpc_url = env.get("FROSTBITE_RPC_URL") or solana_cfg.get("json_rpc_url")
    if rpc_url:
        env["FROSTBITE_RPC_URL"] = rpc_url

    if args.payer:
        env["FROSTBITE_PAYER_KEYPAIR"] = args.payer
    elif solana_cfg.get("keypair_path"):
        env.setdefault("FROSTBITE_PAYER_KEYPAIR", solana_cfg["keypair_path"])
    if args.program_id:
        env["FROSTBITE_PROGRAM_ID"] = args.program_id
    elif "FROSTBITE_PROGRAM_ID" not in env:
        env["FROSTBITE_PROGRAM_ID"] = DEFAULT_PROGRAM_ID
    return env


_SOURCE_UPLOAD_SUFFIXES = {
    ".json",
    ".npz",
    ".npy",
    ".pt",
    ".pth",
    ".safetensors",
    ".toml",
    ".yaml",
    ".yml",
    ".csv",
    ".txt",
}


def _validate_upload_inputs(args: argparse.Namespace) -> None:
    if getattr(args, "allow_raw_upload", False):
        return

    if args.file:
        suffix = Path(args.file).suffix.lower()
        if suffix in _SOURCE_UPLOAD_SUFFIXES:
            raise ValueError(
                "upload expects a binary payload (for example weights.bin). "
                "Convert first with `cauldron convert ... --pack`, then upload weights.bin. "
                "Pass --allow-raw-upload to bypass this guard."
            )

    if args.all:
        suffix = Path(args.all).suffix.lower()
        if suffix in _SOURCE_UPLOAD_SUFFIXES:
            raise ValueError(
                "upload --all pattern appears to target source-format files. "
                "Chunk/upload binary payloads instead. Pass --allow-raw-upload to bypass this guard."
            )


def _cmd_upload(args: argparse.Namespace) -> int:
    _validate_upload_inputs(args)
    env = _build_upload_env(args)
    if args.accounts:
        env = _apply_accounts_env(env, args.accounts, require_weights_keypair=True)
    if args.all:
        rc = upload_all_chunks(args.all, extra_args=args.extra_args, env=env)
    else:
        if not args.file:
            print("upload requires --file or --all")
            return 1
        rc = upload_model_chunk(Path(args.file), extra_args=args.extra_args, env=env)
    if rc != 0:
        print(f"Upload failed with code {rc}")
        return rc
    return 0


def _cmd_deploy(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest)

    if args.input:
        load_and_convert(
            manifest_path=manifest_path,
            input_path=Path(args.input),
            template=args.template,
            output_path=Path(args.output) if args.output else None,
            scale_q16=args.scale_q16,
            w1_scale_q16=args.w1_scale_q16,
            w2_scale_q16=args.w2_scale_q16,
            w3_scale_q16=args.w3_scale_q16,
            w4_scale_q16=args.w4_scale_q16,
            update_manifest=not args.no_update_manifest,
            input_dim_override=args.input_dim,
            output_dim_override=args.output_dim,
            hidden_dim_override=args.hidden_dim,
            hidden_dim1_override=args.hidden_dim1,
            hidden_dim2_override=args.hidden_dim2,
            hidden_dim3_override=args.hidden_dim3,
            bias=not args.no_bias,
            keymap=_parse_keymap(args.keymap),
            input_dim_a_override=args.input_dim_a,
            input_dim_b_override=args.input_dim_b,
            embed_dim_override=args.embed_dim,
            tree_count_override=args.tree_count,
            tree_node_count_override=args.tree_node_count,
        )

    if not args.no_pack:
        pack_manifest(
            manifest_path,
            update_size=True,
            write=True,
            create_missing=False,
        )

    results = []
    if not args.no_chunk:
        results = chunk_manifest(manifest_path, args.chunk_size, Path(args.out_dir) if args.out_dir else None)

    if args.upload:
        env = _build_upload_env(args)
        if args.accounts:
            env = _apply_accounts_env(env, args.accounts, require_weights_keypair=True)
        for result in results:
            for chunk in result.chunks:
                rc = upload_model_chunk(chunk, env=env)
                if rc != 0:
                    print(f"Upload failed for {chunk}")
                    return rc

    print("Deploy complete")
    return 0


def _cmd_accounts_init(args: argparse.Namespace) -> int:
    cfg = _load_solana_cli_config()
    pda_mode = not bool(getattr(args, "legacy_accounts", False))
    if bool(getattr(args, "pda", False)) and not pda_mode:
        raise ValueError("--pda and --legacy-accounts are mutually exclusive")
    if not pda_mode:
        if args.vm_seed is not None:
            raise ValueError("--vm-seed is only valid for seeded account mode")
        if args.authority is not None or args.authority_keypair is not None:
            raise ValueError("--authority/--authority-keypair are only valid for seeded account mode")
    if pda_mode and args.ram_count and args.ram_count > 14:
        raise ValueError("PDA mode supports at most 14 RAM segments (slots 2..15)")

    out_path = Path(args.out) if args.out else None
    if out_path is None:
        if args.manifest:
            out_path = Path(args.manifest).parent / "frostbite-accounts.toml"
        else:
            out_path = Path("frostbite-accounts.toml")

    cluster = {
        "rpc_url": args.rpc_url or cfg.get("json_rpc_url"),
        "program_id": args.program_id or cfg.get("program_id") or DEFAULT_PROGRAM_ID,
        "payer": args.payer or cfg.get("keypair_path"),
    }

    vm_entry: dict[str, str | int] = {}
    if args.vm:
        vm_entry["pubkey"] = args.vm
    elif args.vm_keypair:
        vm_entry["keypair"] = args.vm_keypair
    elif args.vm_file:
        vm_entry["pubkey"] = _load_pubkey_file(args.vm_file)
    elif not pda_mode:
        vm_entry["pubkey"] = "REPLACE_ME"
    if pda_mode:
        vm_entry["seed"] = args.vm_seed if args.vm_seed is not None else secrets.randbits(64)
        vm_entry["account_model"] = "seeded"
        if args.authority:
            vm_entry["authority"] = args.authority
        elif args.authority_keypair:
            vm_entry["authority_keypair"] = args.authority_keypair

    segments: list[dict[str, str | bool | int]] = []
    weights_entry: dict[str, str | bool | int] = {
        "index": 1,
        "slot": 1,
        "kind": "weights",
        "writable": False,
    }
    if args.weights:
        weights_entry["pubkey"] = args.weights
    elif args.weights_keypair:
        weights_entry["keypair"] = args.weights_keypair
    elif not pda_mode:
        weights_entry["pubkey"] = "REPLACE_ME"
    segments.append(weights_entry)

    ram_entries: list[dict[str, str | bool | int]] = []
    for ram in args.ram or []:
        ram_entries.append({"pubkey": ram, "writable": True})
    for ram_keypair in args.ram_keypair or []:
        ram_entries.append({"keypair": ram_keypair, "writable": True})
    if args.ram_file:
        ram_entries.extend(_load_mapped_file(args.ram_file, True))
    if args.ram_count:
        for _ in range(args.ram_count):
            if pda_mode:
                ram_entries.append({"writable": True})
            else:
                ram_entries.append({"pubkey": "REPLACE_ME", "writable": True})
    if pda_mode and len(ram_entries) > 14:
        raise ValueError("PDA mode supports at most 14 RAM segments total (slots 2..15)")

    for idx, entry in enumerate(ram_entries, start=2):
        segment: dict[str, str | bool | int] = {
            "index": idx,
            "slot": idx,
            "kind": "ram",
            "writable": bool(entry.get("writable", True)),
        }
        if "pubkey" in entry:
            segment["pubkey"] = entry["pubkey"]  # type: ignore[assignment]
        if "keypair" in entry:
            segment["keypair"] = entry["keypair"]  # type: ignore[assignment]
        if isinstance(args.ram_bytes, int) and args.ram_bytes > 0:
            segment["bytes"] = args.ram_bytes
        segments.append(segment)

    data = {"cluster": cluster, "vm": vm_entry, "segments": segments}
    write_accounts(out_path, data)
    print(f"Wrote accounts file: {out_path}")
    return 0


def _cmd_accounts_show(args: argparse.Namespace) -> int:
    accounts = load_accounts(args.accounts)
    cluster = accounts.get("cluster") if isinstance(accounts.get("cluster"), dict) else {}
    vm = accounts.get("vm") if isinstance(accounts.get("vm"), dict) else {}
    vm_seed: int | None = None
    vm_pubkey = resolve_pubkey(vm)
    mapped_lines: list[str] = []
    derived_error: str | None = None
    try:
        vm_seed = parse_vm_seed(vm)
    except Exception as exc:
        derived_error = f"invalid vm.seed: {exc}"
    try:
        info, mapped_lines = _accounts_segment_metas(args.accounts)
        vm_pubkey = info.get("vm_pubkey") or vm_pubkey
    except Exception as exc:
        if derived_error:
            derived_error = f"{derived_error}; {exc}"
        else:
            derived_error = str(exc)
    if not vm_pubkey:
        vm_pubkey = "<missing>"

    print("Accounts:")
    if cluster:
        if isinstance(cluster.get("rpc_url"), str):
            print(f"  rpc_url: {cluster['rpc_url']}")
        if isinstance(cluster.get("program_id"), str):
            print(f"  program_id: {cluster['program_id']}")
        if isinstance(cluster.get("payer"), str):
            print(f"  payer: {cluster['payer']}")
    if vm_seed is not None:
        print(f"  vm_seed: {vm_seed}")
    print(f"  vm: {vm_pubkey}")

    segments = parse_segments(accounts)
    if not segments:
        print("  segments: <none>")
        return 0
    print("  segments:")
    sorted_segments = sorted(segments, key=lambda seg: seg.index)
    for idx, seg in enumerate(sorted_segments):
        pubkey = seg.pubkey or (
            resolve_pubkey({"keypair": _resolve_accounts_path(args.accounts, seg.keypair)}) if seg.keypair else None
        )
        if not pubkey and idx < len(mapped_lines):
            line = mapped_lines[idx]
            if ":" in line:
                pubkey = line.split(":", 1)[1].strip()
        if not pubkey:
            pubkey = "<missing>"
        mode = "rw" if seg.writable else "ro"
        print(f"    seg {seg.index} (slot {seg.slot}): {seg.kind} {mode} {pubkey}")
    if derived_error:
        print(f"  note: {derived_error}")
    return 0


def _cmd_accounts_export(args: argparse.Namespace) -> int:
    _, lines = _accounts_segment_metas(args.accounts)
    out_path = Path(args.out) if args.out else Path("mapped_accounts.txt")
    out_path.write_text("\n".join(lines) + "\n")
    print(f"Wrote mapped accounts: {out_path}")
    return 0


def _cmd_accounts_create(args: argparse.Namespace) -> int:
    accounts_path = args.accounts
    info, mapped_lines = _accounts_segment_metas(
        accounts_path,
        program_id_override=args.program_id,
        payer_override=args.payer,
    )
    vm_seed = info.get("vm_seed")
    if isinstance(vm_seed, str) and vm_seed:
        return _cmd_accounts_create_pda(args, accounts_path, info, mapped_lines, int(vm_seed))

    env = os.environ.copy()
    if args.rpc_url:
        env["FROSTBITE_RPC_URL"] = args.rpc_url
    elif info.get("rpc_url"):
        env["FROSTBITE_RPC_URL"] = info["rpc_url"]
    if args.payer:
        env["FROSTBITE_PAYER_KEYPAIR"] = args.payer
    elif info.get("payer"):
        env["FROSTBITE_PAYER_KEYPAIR"] = info["payer"]
    if args.program_id:
        env["FROSTBITE_PROGRAM_ID"] = args.program_id
    elif info.get("program_id"):
        env["FROSTBITE_PROGRAM_ID"] = info["program_id"]
    elif "FROSTBITE_PROGRAM_ID" not in env:
        env["FROSTBITE_PROGRAM_ID"] = DEFAULT_PROGRAM_ID

    mapped_path = Path(args.mapped_out) if args.mapped_out else Path("mapped_accounts.txt")
    mapped_path.write_text("\n".join(mapped_lines) + "\n")

    vm_pubkey = info.get("vm_pubkey")
    if not vm_pubkey:
        raise ValueError("accounts file missing vm pubkey")
    vm_file = args.vm_file or "frostbite_vm_accounts.txt"
    ram_file = args.ram_file or "frostbite_ram_accounts.txt"

    run_onchain = _resolve_run_onchain()
    cmd = [run_onchain]
    if args.program_path:
        cmd.extend([args.program_path, "--load"])
    cmd.extend(
        [
            "--vm",
            vm_pubkey,
            "--mapped-file",
            str(mapped_path),
            "--ram-save",
            ram_file,
            "--vm-save",
            vm_file,
            "--instructions",
            "1",
        ]
    )

    if args.ram_count is not None:
        cmd.extend(["--ram-count", str(args.ram_count)])
    if args.ram_bytes is not None:
        cmd.extend(["--ram-bytes", str(args.ram_bytes)])
    if args.rpc_url:
        cmd.extend(["--rpc", args.rpc_url])
    elif info.get("rpc_url"):
        cmd.extend(["--rpc", info["rpc_url"]])
    if args.payer:
        cmd.extend(["--keypair", args.payer])
    elif info.get("payer"):
        cmd.extend(["--keypair", info["payer"]])
    if args.program_id:
        cmd.extend(["--program-id", args.program_id])
    elif info.get("program_id"):
        cmd.extend(["--program-id", info["program_id"]])
    else:
        cmd.extend(["--program-id", DEFAULT_PROGRAM_ID])
    if args.no_simulate:
        cmd.append("--no-simulate")
    if args.verbose:
        cmd.append("--verbose")

    print("Running:", " ".join(cmd))
    proc = subprocess.run(cmd, env=env)
    return proc.returncode


def _cmd_accounts_create_pda(
    args: argparse.Namespace,
    accounts_path: str,
    info: dict[str, str | None],
    mapped_lines: list[str],
    vm_seed: int,
) -> int:
    accounts = load_accounts(accounts_path)
    vm = accounts.get("vm") if isinstance(accounts.get("vm"), dict) else {}
    _validate_vm_authority_binding(accounts_path, vm)
    segments = parse_segments(accounts)
    default_ram_bytes = args.ram_bytes if isinstance(args.ram_bytes, int) and args.ram_bytes > 0 else 262_144

    segment_specs: list[str] = []
    for seg in segments:
        kind = seg.kind.strip().lower()
        if kind == "ram":
            payload_bytes = seg.bytes if isinstance(seg.bytes, int) and seg.bytes > 0 else default_ram_bytes
            segment_specs.append(f"ram:{seg.slot}:{payload_bytes}")
            continue
        if kind == "weights" and isinstance(seg.bytes, int) and seg.bytes > 0:
            segment_specs.append(f"weights:{seg.slot}:{seg.bytes}")

    env = os.environ.copy()
    if args.rpc_url:
        env["FROSTBITE_RPC_URL"] = args.rpc_url
    elif isinstance(info.get("rpc_url"), str):
        env["FROSTBITE_RPC_URL"] = info["rpc_url"]
    if args.payer:
        env["FROSTBITE_PAYER_KEYPAIR"] = args.payer
    elif isinstance(info.get("payer"), str):
        env["FROSTBITE_PAYER_KEYPAIR"] = info["payer"]
    if args.program_id:
        env["FROSTBITE_PROGRAM_ID"] = args.program_id
    elif isinstance(info.get("program_id"), str):
        env["FROSTBITE_PROGRAM_ID"] = info["program_id"]
    elif "FROSTBITE_PROGRAM_ID" not in env:
        env["FROSTBITE_PROGRAM_ID"] = DEFAULT_PROGRAM_ID

    authority_keypair_path: str | None = None
    if isinstance(vm.get("authority_keypair"), str) and vm.get("authority_keypair"):
        authority_keypair_path = _resolve_accounts_path(accounts_path, vm["authority_keypair"])
        env["FROSTBITE_AUTHORITY_KEYPAIR"] = authority_keypair_path
    authority_pubkey = resolve_authority_pubkey(
        accounts,
        authority_keypair_override=authority_keypair_path or env.get("FROSTBITE_PAYER_KEYPAIR"),
    )
    if authority_pubkey:
        env["FROSTBITE_AUTHORITY_PUBKEY"] = authority_pubkey
    if authority_keypair_path is None and authority_pubkey and "FROSTBITE_PAYER_KEYPAIR" in env:
        payer_pubkey = resolve_pubkey({"keypair": env["FROSTBITE_PAYER_KEYPAIR"]})
        if payer_pubkey and payer_pubkey != authority_pubkey:
            raise ValueError(
                "PDA account creation authority differs from payer signer; set vm.authority_keypair "
                "or use --payer that matches vm.authority"
            )

    mapped_path = Path(args.mapped_out) if args.mapped_out else Path("mapped_accounts.txt")
    mapped_path.write_text("\n".join(mapped_lines) + "\n")

    rust_tools = Path(__file__).resolve().parent / "rust_tools"
    cmd = ["cargo", "run", "--bin", "init_pda_accounts", "--", "--vm-seed", str(vm_seed)]
    for spec in segment_specs:
        cmd.extend(["--segment", spec])

    print("Running:", " ".join(cmd))
    proc = subprocess.run(cmd, env=env, cwd=str(rust_tools))
    return proc.returncode


def _prepare_pda_ops_env(
    accounts_path: str,
    *,
    rpc_url: str | None,
    program_id: str | None,
    payer: str | None,
) -> tuple[dict[str, str], str]:
    info, _ = _accounts_segment_metas(
        accounts_path,
        program_id_override=program_id,
        payer_override=payer,
    )
    vm_seed = info.get("vm_seed")
    if not isinstance(vm_seed, str) or not vm_seed:
        raise ValueError("accounts operation requires vm.seed (PDA mode)")

    env = os.environ.copy()
    if rpc_url:
        env["FROSTBITE_RPC_URL"] = rpc_url
    elif info.get("rpc_url"):
        env["FROSTBITE_RPC_URL"] = info["rpc_url"]
    if payer:
        env["FROSTBITE_PAYER_KEYPAIR"] = payer
    elif info.get("payer"):
        env["FROSTBITE_PAYER_KEYPAIR"] = info["payer"]
    if program_id:
        env["FROSTBITE_PROGRAM_ID"] = program_id
    elif info.get("program_id"):
        env["FROSTBITE_PROGRAM_ID"] = info["program_id"]
    elif "FROSTBITE_PROGRAM_ID" not in env:
        env["FROSTBITE_PROGRAM_ID"] = DEFAULT_PROGRAM_ID

    env = _apply_accounts_env(env, accounts_path, require_weights_keypair=False)
    return env, vm_seed


def _run_pda_account_ops(env: dict[str, str], args: list[str]) -> int:
    rust_tools = Path(__file__).resolve().parent / "rust_tools"
    cmd = ["cargo", "run", "--bin", "pda_account_ops", "--", *args]
    print("Running:", " ".join(cmd))
    proc = subprocess.run(cmd, env=env, cwd=str(rust_tools))
    return proc.returncode


def _cmd_accounts_clear(args: argparse.Namespace) -> int:
    if args.slot < 1 or args.slot > 15:
        raise ValueError("slot must be in range 1..15")
    if args.offset < 0:
        raise ValueError("offset must be >= 0")
    if args.length < 0:
        raise ValueError("length must be >= 0")
    if args.length == 0 and args.offset != 0:
        raise ValueError("length=0 requires offset=0")

    env, vm_seed = _prepare_pda_ops_env(
        args.accounts,
        rpc_url=args.rpc_url,
        program_id=args.program_id,
        payer=args.payer,
    )
    return _run_pda_account_ops(
        env,
        [
            "clear-segment",
            "--vm-seed",
            vm_seed,
            "--kind",
            args.kind,
            "--slot",
            str(args.slot),
            "--offset",
            str(args.offset),
            "--len",
            str(args.length),
        ],
    )


def _cmd_accounts_close_segment(args: argparse.Namespace) -> int:
    if args.slot < 1 or args.slot > 15:
        raise ValueError("slot must be in range 1..15")

    env, vm_seed = _prepare_pda_ops_env(
        args.accounts,
        rpc_url=args.rpc_url,
        program_id=args.program_id,
        payer=args.payer,
    )
    cmd = [
        "close-segment",
        "--vm-seed",
        vm_seed,
        "--kind",
        args.kind,
        "--slot",
        str(args.slot),
    ]
    if args.recipient:
        cmd.extend(["--recipient", args.recipient])
    return _run_pda_account_ops(env, cmd)


def _cmd_accounts_close_vm(args: argparse.Namespace) -> int:
    env, vm_seed = _prepare_pda_ops_env(
        args.accounts,
        rpc_url=args.rpc_url,
        program_id=args.program_id,
        payer=args.payer,
    )
    cmd = ["close-vm", "--vm-seed", vm_seed]
    if args.recipient:
        cmd.extend(["--recipient", args.recipient])
    return _run_pda_account_ops(env, cmd)


def _cmd_program_load(args: argparse.Namespace) -> int:
    info, _ = _accounts_segment_metas(
        args.accounts,
        program_id_override=args.program_id,
        payer_override=args.payer,
    )

    env = os.environ.copy()
    if args.rpc_url:
        env["FROSTBITE_RPC_URL"] = args.rpc_url
    elif info.get("rpc_url"):
        env["FROSTBITE_RPC_URL"] = info["rpc_url"]
    if args.payer:
        env["FROSTBITE_PAYER_KEYPAIR"] = args.payer
    elif info.get("payer"):
        env["FROSTBITE_PAYER_KEYPAIR"] = info["payer"]
    if args.program_id:
        env["FROSTBITE_PROGRAM_ID"] = args.program_id
    elif info.get("program_id"):
        env["FROSTBITE_PROGRAM_ID"] = info["program_id"]
    elif "FROSTBITE_PROGRAM_ID" not in env:
        env["FROSTBITE_PROGRAM_ID"] = DEFAULT_PROGRAM_ID

    vm_pubkey = info.get("vm_pubkey")
    if not vm_pubkey:
        raise ValueError("accounts file missing vm pubkey")

    run_onchain = _resolve_run_onchain()
    cmd = [
        run_onchain,
        args.program,
        "--vm",
        vm_pubkey,
        "--load",
        "--load-only",
    ]

    if args.rpc_url:
        cmd.extend(["--rpc", args.rpc_url])
    elif info.get("rpc_url"):
        cmd.extend(["--rpc", info["rpc_url"]])
    if args.payer:
        cmd.extend(["--keypair", args.payer])
    elif info.get("payer"):
        cmd.extend(["--keypair", info["payer"]])
    if args.program_id:
        cmd.extend(["--program-id", args.program_id])
    elif info.get("program_id"):
        cmd.extend(["--program-id", info["program_id"]])
    else:
        cmd.extend(["--program-id", DEFAULT_PROGRAM_ID])
    if args.verbose:
        cmd.append("--verbose")

    print("Running:", " ".join(cmd))
    proc = subprocess.run(cmd, env=env)
    return proc.returncode


def _cmd_invoke(args: argparse.Namespace) -> int:
    if args.fast:
        if args.program_path:
            print("--fast ignores --program-path; program should already be loaded")
            args.program_path = None
        args.no_simulate = True

    info, mapped_lines = _accounts_segment_metas(
        args.accounts,
        program_id_override=args.program_id,
        payer_override=args.payer,
    )

    env = os.environ.copy()
    if args.rpc_url:
        env["FROSTBITE_RPC_URL"] = args.rpc_url
    elif info.get("rpc_url"):
        env["FROSTBITE_RPC_URL"] = info["rpc_url"]
    if args.payer:
        env["FROSTBITE_PAYER_KEYPAIR"] = args.payer
    elif info.get("payer"):
        env["FROSTBITE_PAYER_KEYPAIR"] = info["payer"]
    if args.program_id:
        env["FROSTBITE_PROGRAM_ID"] = args.program_id
    elif info.get("program_id"):
        env["FROSTBITE_PROGRAM_ID"] = info["program_id"]
    elif "FROSTBITE_PROGRAM_ID" not in env:
        env["FROSTBITE_PROGRAM_ID"] = DEFAULT_PROGRAM_ID

    vm_pubkey = info.get("vm_pubkey")
    if not vm_pubkey:
        raise ValueError("accounts file missing vm pubkey")

    mapped_path = Path(args.mapped_out) if args.mapped_out else Path("mapped_accounts.txt")
    mapped_path.write_text("\n".join(mapped_lines) + "\n")
    has_writable_mapped_segments = any(line.startswith("rw:") for line in mapped_lines)

    run_onchain = _resolve_run_onchain()
    cmd = [run_onchain]
    if args.program_path:
        cmd.extend([args.program_path, "--load"])
    cmd.extend(
        [
            "--vm",
            vm_pubkey,
            "--mapped-file",
            str(mapped_path),
            "--instructions",
            str(args.instructions),
        ]
    )
    if args.ram_count is not None:
        cmd.extend(["--ram-count", str(args.ram_count)])
    elif has_writable_mapped_segments:
        cmd.extend(["--ram-count", "0"])
    if args.ram_bytes is not None:
        cmd.extend(["--ram-bytes", str(args.ram_bytes)])
    if args.compute_limit is not None:
        cmd.extend(["--compute-limit", str(args.compute_limit)])
    if args.max_tx is not None:
        cmd.extend(["--max-tx", str(args.max_tx)])
    if args.rpc_url:
        cmd.extend(["--rpc", args.rpc_url])
    elif info.get("rpc_url"):
        cmd.extend(["--rpc", info["rpc_url"]])
    if args.payer:
        cmd.extend(["--keypair", args.payer])
    elif info.get("payer"):
        cmd.extend(["--keypair", info["payer"]])
    if args.program_id:
        cmd.extend(["--program-id", args.program_id])
    elif info.get("program_id"):
        cmd.extend(["--program-id", info["program_id"]])
    else:
        cmd.extend(["--program-id", DEFAULT_PROGRAM_ID])
    if args.no_simulate:
        cmd.append("--no-simulate")
    if args.verbose:
        cmd.append("--verbose")

    print("Running:", " ".join(cmd))
    proc = subprocess.run(cmd, env=env)
    return proc.returncode


def _cmd_train(args: argparse.Namespace) -> int:
    from .training.cli import run_train_from_args

    return run_train_from_args(args)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog=os.path.basename(sys.argv[0]))
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_validate = sub.add_parser("validate", help="Validate a manifest")
    p_validate.add_argument("manifest", help="Path to frostbite-model.toml")
    p_validate.add_argument("--json", action="store_true", help="Emit errors as lines")
    p_validate.set_defaults(func=_cmd_validate)

    p_show = sub.add_parser("show", help="Print key manifest sections")
    p_show.add_argument("manifest", help="Path to frostbite-model.toml")
    p_show.set_defaults(func=_cmd_show)

    p_init = sub.add_parser("init", help="Initialize a model project")
    p_init.add_argument("path", help="Destination directory")
    p_init.add_argument(
        "--template",
        choices=[
            "linear",
            "softmax",
            "naive_bayes",
            "two_tower",
            "mlp",
            "mlp2",
            "mlp3",
            "cnn1d",
            "tiny_cnn",
            "tree",
            "custom",
        ],
        default="linear",
        help="Template to use",
    )
    p_init.add_argument(
        "--manifest",
        default="frostbite-model.toml",
        help="Manifest filename",
    )
    p_init.add_argument(
        "--copy-guest",
        action="store_true",
        help="Write full guest template (default)",
    )
    p_init.add_argument(
        "--stub",
        action="store_true",
        help="Write a stub guest file instead of the full template",
    )
    p_init.add_argument(
        "--no-weights",
        action="store_true",
        help="Skip creating weights.bin placeholder files",
    )
    p_init.set_defaults(func=_cmd_init)

    p_pack = sub.add_parser("pack", help="Compute hashes and update manifest")
    p_pack.add_argument("manifest", help="Path to frostbite-model.toml")
    p_pack.add_argument(
        "--update-size",
        action="store_true",
        help="Update size_bytes from file sizes",
    )
    p_pack.add_argument(
        "--dry-run",
        action="store_true",
        help="Print updates without writing the manifest",
    )
    p_pack.add_argument(
        "--create-missing",
        action="store_true",
        help="Create missing weights files using size_bytes",
    )
    p_pack.set_defaults(func=_cmd_pack)

    p_convert = sub.add_parser("convert", help="Convert weights to Frostbite layout")
    p_convert.add_argument("--manifest", required=True, help="Path to frostbite-model.toml")
    p_convert.add_argument("--input", required=True, help="Path to input .json or .npz")
    p_convert.add_argument(
        "--template",
        choices=["linear", "softmax", "naive_bayes", "two_tower", "mlp", "mlp2", "mlp3", "cnn1d", "tiny_cnn", "tree"],
        help="Override template inference",
    )
    p_convert.add_argument("--output", help="Output weights.bin path")
    p_convert.add_argument("--scale-q16", type=int, help="Override linear scale")
    p_convert.add_argument("--w1-scale-q16", type=int, help="Override MLP W1 scale")
    p_convert.add_argument("--w2-scale-q16", type=int, help="Override MLP W2 scale")
    p_convert.add_argument("--w3-scale-q16", type=int, help="Override MLP3 W3 scale")
    p_convert.add_argument("--w4-scale-q16", type=int, help="Override MLP3 W4 scale")
    p_convert.add_argument("--input-dim", type=int, help="Override input dimension")
    p_convert.add_argument("--output-dim", type=int, help="Override output dimension")
    p_convert.add_argument("--hidden-dim", type=int, help="Override hidden dimension (MLP)")
    p_convert.add_argument("--hidden-dim1", type=int, help="Hidden dimension 1 (MLP2/MLP3)")
    p_convert.add_argument("--hidden-dim2", type=int, help="Hidden dimension 2 (MLP2/MLP3)")
    p_convert.add_argument("--hidden-dim3", type=int, help="Hidden dimension 3 (MLP3)")
    p_convert.add_argument("--input-dim-a", type=int, help="Two-tower input dim for tower A")
    p_convert.add_argument("--input-dim-b", type=int, help="Two-tower input dim for tower B")
    p_convert.add_argument("--embed-dim", type=int, help="Two-tower embedding dimension")
    p_convert.add_argument("--tree-count", type=int, help="Tree count (GBDT)")
    p_convert.add_argument("--tree-node-count", type=int, help="Nodes per tree")
    p_convert.add_argument("--no-bias", action="store_true", help="Omit bias term (linear)")
    p_convert.add_argument(
        "--keymap",
        action="append",
        help="Map input keys (dst=src), e.g. --keymap w=linear.weight",
    )
    p_convert.add_argument(
        "--no-update-manifest",
        action="store_true",
        help="Do not update weights.scales in the manifest",
    )
    p_convert.add_argument(
        "--pack",
        action="store_true",
        help="Run pack to update hash/size after conversion",
    )
    p_convert.set_defaults(func=_cmd_convert)

    p_build = sub.add_parser("build-guest", help="Patch guest config and build")
    p_build.add_argument("--manifest", required=True, help="Path to frostbite-model.toml")
    p_build.add_argument("--guest", help="Path to guest directory (default: ./guest)")
    p_build.add_argument(
        "--template",
        choices=[
            "linear",
            "softmax",
            "naive_bayes",
            "two_tower",
            "mlp",
            "mlp2",
            "mlp3",
            "cnn1d",
            "tiny_cnn",
            "tree",
            "custom",
        ],
        help="Override template inference",
    )
    p_build.add_argument(
        "--schema-hash",
        choices=["auto", "manifest", "none"],
        default="auto",
        help="Schema hash mode (default: auto)",
    )
    p_build.add_argument(
        "--target",
        default="riscv64imac-unknown-none-elf",
        help="Rust target triple",
    )
    p_build.add_argument("--debug", action="store_true", help="Build debug instead of release")
    p_build.add_argument("--no-build", action="store_true", help="Only write config.rs")
    p_build.set_defaults(func=_cmd_build_guest)

    p_chunk = sub.add_parser("chunk", help="Chunk weights for upload")
    p_chunk.add_argument("--manifest", help="Path to frostbite-model.toml")
    p_chunk.add_argument("--file", help="Weights file to chunk")
    p_chunk.add_argument("--chunk-size", type=int, help="Override chunk size in bytes")
    p_chunk.add_argument("--out-dir", help="Output directory for chunks")
    p_chunk.set_defaults(func=_cmd_chunk)

    p_schema = sub.add_parser("schema-hash", help="Compute schema hash")
    p_schema.add_argument("--manifest", required=True, help="Path to frostbite-model.toml")
    p_schema.add_argument(
        "--update-manifest",
        action="store_true",
        help="Write schema_hash32 into [schema.custom]",
    )
    p_schema.set_defaults(func=_cmd_schema_hash)

    p_input = sub.add_parser("input", help="Pack input payload for a model")
    p_input.add_argument("--manifest", required=True, help="Path to frostbite-model.toml")
    p_input.add_argument("--data", help="JSON payload file (or - for stdin)")
    p_input.add_argument("--input-bin", help="Raw input binary (custom schema)")
    p_input.add_argument("--out", help="Output payload path (default: input.bin)")
    p_input.add_argument("--header", action="store_true", help="Force FBH1 header")
    p_input.add_argument("--no-header", action="store_true", help="Disable FBH1 header")
    p_input.add_argument("--crc", action="store_true", help="Include CRC32 in FBH1 header")
    p_input.add_argument(
        "--schema-hash",
        choices=["auto", "manifest", "none"],
        default="auto",
        help="Schema hash mode for FBH1 header",
    )
    p_input.set_defaults(func=_cmd_input)

    p_input_write = sub.add_parser("input-write", help="Write input payload + control block to VM")
    p_input_write.add_argument("--manifest", required=True, help="Path to frostbite-model.toml")
    p_input_write.add_argument("--accounts", required=True, help="Accounts file")
    p_input_write.add_argument("--data", help="JSON payload file (or - for stdin)")
    p_input_write.add_argument("--input-bin", help="Raw input binary (custom schema)")
    p_input_write.add_argument("--header", action="store_true", help="Force FBH1 header")
    p_input_write.add_argument("--no-header", action="store_true", help="Disable FBH1 header")
    p_input_write.add_argument("--crc", action="store_true", help="Include CRC32 in FBH1 header")
    p_input_write.add_argument(
        "--schema-hash",
        choices=["auto", "manifest", "none"],
        default="auto",
        help="Schema hash mode for FBH1 header",
    )
    p_input_write.add_argument("--rpc-url", help="Override RPC URL")
    p_input_write.add_argument("--payer", help="Override payer keypair path")
    p_input_write.add_argument("--program-id", help=argparse.SUPPRESS)
    p_input_write.add_argument("--chunk-size", type=int, help="Chunk size for write_account")
    p_input_write.set_defaults(func=_cmd_input_write)

    p_output = sub.add_parser("output", help="Read model output from VM scratch")
    p_output.add_argument("--manifest", required=True, help="Path to frostbite-model.toml")
    p_output.add_argument("--accounts", required=True, help="Accounts file")
    p_output.add_argument("--rpc-url", help="Override RPC URL")
    p_output.add_argument("--format", choices=["auto", "i32", "u32", "f32", "u8", "hex", "raw"], default="auto")
    p_output.add_argument("--use-max", action="store_true", help="Use abi.output_max when output_len is zero")
    p_output.add_argument("--out", help="Write raw output bytes to file")
    p_output.set_defaults(func=_cmd_output)

    p_upload = sub.add_parser("upload", help="Upload weights via Rust example")
    p_upload.add_argument("--file", help="Path to chunk file to upload")
    p_upload.add_argument("--all", help="Glob pattern for chunk files")
    p_upload.add_argument(
        "--cluster",
        choices=["localnet", "devnet", "mainnet", "surfpool"],
        help="Cluster to target (overrides Solana CLI config)",
    )
    p_upload.add_argument("--rpc-url", help="Override RPC URL")
    p_upload.add_argument("--payer", help="Override payer keypair path")
    p_upload.add_argument("--program-id", help=argparse.SUPPRESS)
    p_upload.add_argument("--accounts", help="Accounts file (frostbite-accounts.toml)")
    p_upload.add_argument(
        "--allow-raw-upload",
        action="store_true",
        help="Bypass source-format upload guard (unsafe; advanced/debug only)",
    )
    p_upload.add_argument(
        "--extra-args",
        nargs=argparse.REMAINDER,
        help="Extra args passed to the Rust example",
    )
    p_upload.set_defaults(func=_cmd_upload)

    p_deploy = sub.add_parser("deploy", help="Convert, pack, chunk, and optionally upload")
    p_deploy.add_argument("--manifest", required=True, help="Path to frostbite-model.toml")
    p_deploy.add_argument("--input", help="Weights input (.json/.npz/.npy/.pt/.safetensors)")
    p_deploy.add_argument("--output", help="Output weights.bin path")
    p_deploy.add_argument(
        "--template",
        choices=["linear", "softmax", "naive_bayes", "two_tower", "mlp", "mlp2", "mlp3", "cnn1d", "tiny_cnn", "tree"],
        help="Override template inference",
    )
    p_deploy.add_argument("--scale-q16", type=int, help="Override linear scale")
    p_deploy.add_argument("--w1-scale-q16", type=int, help="Override MLP W1 scale")
    p_deploy.add_argument("--w2-scale-q16", type=int, help="Override MLP W2 scale")
    p_deploy.add_argument("--w3-scale-q16", type=int, help="Override MLP3 W3 scale")
    p_deploy.add_argument("--w4-scale-q16", type=int, help="Override MLP3 W4 scale")
    p_deploy.add_argument("--input-dim", type=int, help="Override input dimension")
    p_deploy.add_argument("--output-dim", type=int, help="Override output dimension")
    p_deploy.add_argument("--hidden-dim", type=int, help="Override hidden dimension (MLP)")
    p_deploy.add_argument("--hidden-dim1", type=int, help="Hidden dimension 1 (MLP2/MLP3)")
    p_deploy.add_argument("--hidden-dim2", type=int, help="Hidden dimension 2 (MLP2/MLP3)")
    p_deploy.add_argument("--hidden-dim3", type=int, help="Hidden dimension 3 (MLP3)")
    p_deploy.add_argument("--input-dim-a", type=int, help="Two-tower input dim for tower A")
    p_deploy.add_argument("--input-dim-b", type=int, help="Two-tower input dim for tower B")
    p_deploy.add_argument("--embed-dim", type=int, help="Two-tower embedding dimension")
    p_deploy.add_argument("--tree-count", type=int, help="Tree count (GBDT)")
    p_deploy.add_argument("--tree-node-count", type=int, help="Nodes per tree")
    p_deploy.add_argument("--no-bias", action="store_true", help="Omit bias term (linear)")
    p_deploy.add_argument(
        "--keymap",
        action="append",
        help="Map input keys (dst=src), e.g. --keymap w=linear.weight",
    )
    p_deploy.add_argument(
        "--no-update-manifest",
        action="store_true",
        help="Do not update weights.scales in the manifest",
    )
    p_deploy.add_argument("--no-pack", action="store_true", help="Skip pack step")
    p_deploy.add_argument("--no-chunk", action="store_true", help="Skip chunk step")
    p_deploy.add_argument("--chunk-size", type=int, help="Override chunk size in bytes")
    p_deploy.add_argument("--out-dir", help="Output directory for chunks")
    p_deploy.add_argument("--upload", action="store_true", help="Upload chunks after chunking")
    p_deploy.add_argument(
        "--cluster",
        choices=["localnet", "devnet", "mainnet", "surfpool"],
        help="Cluster to target (overrides Solana CLI config)",
    )
    p_deploy.add_argument("--rpc-url", help="Override RPC URL")
    p_deploy.add_argument("--payer", help="Override payer keypair path")
    p_deploy.add_argument("--program-id", help=argparse.SUPPRESS)
    p_deploy.add_argument("--accounts", help="Accounts file (frostbite-accounts.toml)")
    p_deploy.set_defaults(func=_cmd_deploy)

    p_accounts = sub.add_parser("accounts", help="Manage account mappings")
    p_accounts_sub = p_accounts.add_subparsers(dest="accounts_cmd", required=True)

    p_accounts_init = p_accounts_sub.add_parser("init", help="Create a frostbite-accounts.toml")
    p_accounts_init.add_argument("--manifest", help="Path to frostbite-model.toml")
    p_accounts_init.add_argument("--out", help="Output path for accounts file")
    p_accounts_init.add_argument("--rpc-url", help="RPC URL override")
    p_accounts_init.add_argument("--program-id", help=argparse.SUPPRESS)
    p_accounts_init.add_argument("--payer", help="Payer keypair path")
    p_accounts_init.add_argument(
        "--pda",
        action="store_true",
        help="Seeded deterministic mode (default; kept for backwards compatibility)",
    )
    p_accounts_init.add_argument(
        "--legacy-accounts",
        action="store_true",
        help="Use legacy non-seeded account placeholders (requires manual account pubkeys/keypairs)",
    )
    p_accounts_init.add_argument("--vm-seed", type=int, help="VM seed for deterministic mode (u64)")
    p_accounts_init.add_argument("--authority", help="Authority pubkey for deterministic derivation")
    p_accounts_init.add_argument(
        "--authority-keypair", help="Authority keypair for deterministic derivation"
    )
    p_accounts_init.add_argument("--vm", help="VM account pubkey")
    p_accounts_init.add_argument("--vm-keypair", help="VM account keypair path")
    p_accounts_init.add_argument("--vm-file", help="VM pubkey file (from frostbite-run-onchain)")
    p_accounts_init.add_argument("--weights", help="Weights account pubkey")
    p_accounts_init.add_argument("--weights-keypair", help="Weights account keypair path")
    p_accounts_init.add_argument("--ram", action="append", help="RAM account pubkey (repeatable)")
    p_accounts_init.add_argument("--ram-keypair", action="append", help="RAM account keypair path (repeatable)")
    p_accounts_init.add_argument("--ram-file", help="RAM accounts file (ro:/rw: format)")
    p_accounts_init.add_argument("--ram-count", type=int, help="Number of RAM segments to placeholder")
    p_accounts_init.add_argument("--ram-bytes", type=int, help="Default RAM payload bytes in PDA mode")
    p_accounts_init.set_defaults(func=_cmd_accounts_init)

    p_accounts_show = p_accounts_sub.add_parser("show", help="Show account mapping")
    p_accounts_show.add_argument("--accounts", required=True, help="Accounts file")
    p_accounts_show.set_defaults(func=_cmd_accounts_show)

    p_accounts_export = p_accounts_sub.add_parser("export", help="Export mapped accounts file")
    p_accounts_export.add_argument("--accounts", required=True, help="Accounts file")
    p_accounts_export.add_argument("--out", help="Output path (default: mapped_accounts.txt)")
    p_accounts_export.set_defaults(func=_cmd_accounts_export)

    p_accounts_create = p_accounts_sub.add_parser("create", help="Create VM/RAM accounts on-chain")
    p_accounts_create.add_argument("--accounts", required=True, help="Accounts file")
    p_accounts_create.add_argument("--program-path", help="Optional program ELF to load")
    p_accounts_create.add_argument("--rpc-url", help="RPC URL override")
    p_accounts_create.add_argument("--program-id", help=argparse.SUPPRESS)
    p_accounts_create.add_argument("--payer", help="Payer keypair path")
    p_accounts_create.add_argument("--ram-count", type=int, help="Number of RAM accounts to create")
    p_accounts_create.add_argument("--ram-bytes", type=int, help="Bytes per RAM account")
    p_accounts_create.add_argument("--vm-file", help="VM pubkey output file")
    p_accounts_create.add_argument("--ram-file", help="RAM pubkey output file")
    p_accounts_create.add_argument("--mapped-out", help="Mapped accounts file output")
    p_accounts_create.add_argument("--no-simulate", action="store_true")
    p_accounts_create.add_argument("--verbose", action="store_true")
    p_accounts_create.set_defaults(func=_cmd_accounts_create)

    p_accounts_clear = p_accounts_sub.add_parser(
        "clear", help="Clear bytes in a deterministic segment payload"
    )
    p_accounts_clear.add_argument("--accounts", required=True, help="Accounts file")
    p_accounts_clear.add_argument(
        "--kind", required=True, choices=["weights", "ram"], help="Segment kind"
    )
    p_accounts_clear.add_argument("--slot", required=True, type=int, help="Segment slot (1..15)")
    p_accounts_clear.add_argument(
        "--offset", type=int, default=0, help="Payload offset to clear from"
    )
    p_accounts_clear.add_argument(
        "--length",
        type=int,
        default=0,
        help="Bytes to clear (0 clears entire payload; requires offset=0)",
    )
    p_accounts_clear.add_argument("--rpc-url", help="RPC URL override")
    p_accounts_clear.add_argument("--program-id", help=argparse.SUPPRESS)
    p_accounts_clear.add_argument("--payer", help="Payer keypair path")
    p_accounts_clear.set_defaults(func=_cmd_accounts_clear)

    p_accounts_close_segment = p_accounts_sub.add_parser(
        "close-segment", help="Close a deterministic segment and drain lamports"
    )
    p_accounts_close_segment.add_argument("--accounts", required=True, help="Accounts file")
    p_accounts_close_segment.add_argument(
        "--kind", required=True, choices=["weights", "ram"], help="Segment kind"
    )
    p_accounts_close_segment.add_argument(
        "--slot", required=True, type=int, help="Segment slot (1..15)"
    )
    p_accounts_close_segment.add_argument(
        "--recipient",
        help="Recipient pubkey for drained lamports (default: payer)",
    )
    p_accounts_close_segment.add_argument("--rpc-url", help="RPC URL override")
    p_accounts_close_segment.add_argument("--program-id", help=argparse.SUPPRESS)
    p_accounts_close_segment.add_argument("--payer", help="Payer keypair path")
    p_accounts_close_segment.set_defaults(func=_cmd_accounts_close_segment)

    p_accounts_close_vm = p_accounts_sub.add_parser(
        "close-vm", help="Close a deterministic VM account and drain lamports"
    )
    p_accounts_close_vm.add_argument("--accounts", required=True, help="Accounts file")
    p_accounts_close_vm.add_argument(
        "--recipient",
        help="Recipient pubkey for drained lamports (default: payer)",
    )
    p_accounts_close_vm.add_argument("--rpc-url", help="RPC URL override")
    p_accounts_close_vm.add_argument("--program-id", help=argparse.SUPPRESS)
    p_accounts_close_vm.add_argument("--payer", help="Payer keypair path")
    p_accounts_close_vm.set_defaults(func=_cmd_accounts_close_vm)

    p_program = sub.add_parser("program", help="Program helpers")
    p_program_sub = p_program.add_subparsers(dest="program_cmd", required=True)

    p_program_load = p_program_sub.add_parser("load", help="Load guest ELF into an existing VM")
    p_program_load.add_argument("program", help="Path to guest ELF")
    p_program_load.add_argument("--accounts", required=True, help="Accounts file")
    p_program_load.add_argument("--rpc-url", help="RPC URL override")
    p_program_load.add_argument("--program-id", help=argparse.SUPPRESS)
    p_program_load.add_argument("--payer", help="Payer keypair path")
    p_program_load.add_argument("--verbose", action="store_true")
    p_program_load.set_defaults(func=_cmd_program_load)

    p_invoke = sub.add_parser("invoke", help="Invoke a VM using accounts mapping")
    p_invoke.add_argument("--accounts", required=True, help="Accounts file")
    p_invoke.add_argument("--program-path", help="Optional program ELF to load")
    p_invoke.add_argument("--rpc-url", help="RPC URL override")
    p_invoke.add_argument("--program-id", help=argparse.SUPPRESS)
    p_invoke.add_argument("--payer", help="Payer keypair path")
    p_invoke.add_argument("--instructions", type=int, default=50000)
    p_invoke.add_argument(
        "--ram-count",
        type=int,
        help="Override temp RAM account count (default auto: 0 when mapped writable segments exist)",
    )
    p_invoke.add_argument(
        "--ram-bytes",
        type=int,
        help="Bytes per temp RAM account when temp RAM creation is enabled",
    )
    p_invoke.add_argument("--compute-limit", type=int, help="Compute unit limit")
    p_invoke.add_argument("--max-tx", type=int, help="Maximum tx count")
    p_invoke.add_argument("--mapped-out", help="Mapped accounts file output")
    p_invoke.add_argument("--fast", action="store_true", help="Skip preflight sim; assume program/input staged")
    p_invoke.add_argument("--no-simulate", action="store_true")
    p_invoke.add_argument("--verbose", action="store_true")
    p_invoke.set_defaults(func=_cmd_invoke)

    p_train = sub.add_parser("train", help="Train a model and export weights")
    p_train.add_argument("--manifest", required=True, help="Path to frostbite-model.toml")
    p_train.add_argument(
        "--template",
        choices=[
            "linear",
            "softmax",
            "naive_bayes",
            "two_tower",
            "mlp",
            "mlp2",
            "mlp3",
            "cnn1d",
            "tiny_cnn",
            "tree",
        ],
        help="Override template inference",
    )
    p_train.add_argument("--data", required=True, help="Training dataset (.csv or .npz)")
    p_train.add_argument("--label-col", help="CSV label column (name or index)")
    p_train.add_argument("--task", choices=["regression", "classification"], default="regression")
    p_train.add_argument("--epochs", type=int, default=50)
    p_train.add_argument("--batch-size", type=int, default=64)
    p_train.add_argument("--lr", type=float, default=1e-3)
    p_train.add_argument("--val-split", type=float, default=0.1)
    p_train.add_argument("--seed", type=int, default=123)
    p_train.add_argument("--hidden-dim", type=int, help="Hidden dimension (MLP)")
    p_train.add_argument("--hidden-dim1", type=int, help="Hidden dimension 1 (MLP2/MLP3)")
    p_train.add_argument("--hidden-dim2", type=int, help="Hidden dimension 2 (MLP2/MLP3)")
    p_train.add_argument("--hidden-dim3", type=int, help="Hidden dimension 3 (MLP3)")
    p_train.add_argument("--kernel-size", type=int, help="Kernel size (CNN)")
    p_train.add_argument("--out-channels", type=int, help="Out channels (CNN)")
    p_train.add_argument("--stride", type=int, help="Stride (CNN)")
    p_train.add_argument("--input-height", type=int, help="Input height (tiny_cnn)")
    p_train.add_argument("--input-width", type=int, help="Input width (tiny_cnn)")
    p_train.add_argument("--input-dim-a", type=int, help="Two-tower input dim for tower A")
    p_train.add_argument("--input-dim-b", type=int, help="Two-tower input dim for tower B")
    p_train.add_argument("--embed-dim", type=int, help="Two-tower embedding dimension")
    p_train.add_argument("--tree-max-depth", type=int, help="Max depth for tree training")
    p_train.add_argument("--no-bias", action="store_true", help="Train without bias terms")
    p_train.add_argument("--no-convert", action="store_true", help="Skip convert step")
    p_train.add_argument("--output-dir", help="Output directory for weights.json")
    p_train.add_argument("--calibrate-percentile", type=float, help="Percentile for weight calibration")
    p_train.add_argument(
        "--input-calibrate-percentile",
        type=float,
        help="Percentile for input calibration (writes input_calibration.json)",
    )
    p_train.set_defaults(func=_cmd_train)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except FileNotFoundError as exc:
        print(str(exc))
        return 1
    except (ValidationError, ValueError) as exc:
        print(str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
