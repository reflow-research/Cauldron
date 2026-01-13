# Frostbite Model Manifest Spec v0.1

This document formalizes the schema enums and exact validation rules for
`frostbite-model.toml`. It is the single source of truth for manifest parsing
and ModelKit validation.

Normative language: "MUST", "SHOULD", and "MAY" are used as in RFC 2119.

## Environment assumptions
- ISA: RV64IMAC, little-endian.
- Registers and PC are 64-bit.
- Virtual addresses are 32-bit and segmented: top 4 bits are segment index,
  low 28 bits are offset. Segment size limit is 0x1000_0000 (256MB).

## Required tables
- [model]
- [abi]
- [schema]
- one of [schema.vector] | [schema.time_series] | [schema.graph] | [schema.custom]
- [[segments]]
- [limits]
- [weights] and [[weights.blobs]] if the model uses weights

## Optional tables
- [validation]
- [build]
- [metadata]

Unknown keys are allowed only under [build] and [metadata]. Unknown keys
elsewhere MUST cause validation failure.

### Tooling hints (non-normative)

Cauldron uses `[build]` for template-specific constants that are not part of the
core spec. These are optional and ignored by validators that only enforce the
spec:

- `hidden_dim` (MLP templates)
- `hidden_offset` (scratch offset for the hidden buffer)
- `has_bias` (linear templates)
- `stack_guard` (bytes reserved for stack guard)
- `weights_offset` (optional base offset into weights blob)

## Enums

### model.arch
- "rv64imac" (only allowed value)

### model.endianness
- "little" (only allowed value)

### schema.type
- "vector"
- "time_series"
- "graph"
- "custom"

### schema.*.dtype
Allowed dtypes and byte widths:
- "f32" (4)
- "f16" (2)
- "i32" (4)
- "i16" (2)
- "i8" (1)
- "u32" (4)
- "u8" (1)

### weights.quantization
- "q8"
- "q4"
- "f16"
- "f32"
- "custom"

### weights.header_format
- "none" (default)
- "rvcd-v1" (implies data_offset=12 if not specified)

### segments.kind
- "scratch"
- "weights"
- "input"
- "output"
- "custom"

### segments.access
- "ro"
- "rw"
- "wo"

### validation.mode
- "minimal"
- "guest"

### model.profile (optional)
- "finance-int" (integer-only, Q16 fixed-point)

## Schema blocks

### Vector schema
```
[schema]
type = "vector"

[schema.vector]
input_dtype = "f32"
input_shape = [64]
output_dtype = "f32"
output_shape = [1]
```

### Time-series schema
```
[schema]
type = "time_series"

[schema.time_series]
input_dtype = "f32"
window = 128
features = 16
stride = 1           # optional, default 1
output_dtype = "f32"
output_shape = [1]
```

### Graph schema
```
[schema]
type = "graph"

[schema.graph]
input_dtype = "f32"
node_feature_dim = 16
edge_feature_dim = 8
max_nodes = 512
max_edges = 4096
output_dtype = "f32"
output_shape = [1]
```

### Custom schema
```
[schema]
type = "custom"

[schema.custom]
input_blob_size = 1024
output_blob_size = 16
alignment = 8            # optional, default abi.alignment
layout_doc = "docs/layout.md"   # optional
schema_hash32 = "0xA1B2C3D4"     # optional
```

Optional custom field annotations (for tooling only):
```
[[schema.custom.fields]]
name = "feature_vec"
offset = 0
dtype = "f32"
shape = [64]
```

## Payload layouts (default)

All payloads are little-endian. Unless otherwise noted, payload layouts are
defined relative to the start of the *payload* region.

If `validation.mode = "guest"`, the host prepends a 32-byte FBH1 header to the
input buffer. In that case:
- `input_ptr` points to the FBH1 header.
- The payload starts at `input_ptr + 32`.
- All offsets below are relative to the payload start.

### Vector payload
Flat, row-major contiguous array of `input_shape`.

```
payload[0..input_bytes)

offset  size
0       input_bytes  (input_shape flattened)
```

### Time-series payload
Time-major order (t0 features, then t1 features, ...). For `window=W` and
`features=F`, the payload is `W * F` elements of `input_dtype`.

```
payload[0..input_bytes)

offset  size
0       input_bytes  (t0[f0..F-1], t1[f0..F-1], ...)
```

### Graph payload
Header + node features + edge indices + edge features.

```
payload layout:

offset  size
0       4   node_count (u32)
4       4   edge_count (u32)
8       4   reserved0 (u32)
12      4   reserved1 (u32)
16      ... node features (node_count * node_feature_dim)
...     ... edge indices (edge_count * 2 * u32)
...     ... edge features (edge_count * edge_feature_dim)
```

Constraints:
- `node_count <= max_nodes`
- `edge_count <= max_edges`
- Node features are stored as `input_dtype`.
- Edge features are stored as `input_dtype`.
- Edge index pairs are `(src, dst)` with u32 indices.

## Integer-first profile (finance-int)

When `model.profile = "finance-int"`, the following additional rules apply:
- `schema.*.input_dtype` MUST be `i32`.
- `schema.*.output_dtype` MUST be `i32`.
- Inputs/outputs are interpreted as **Q16 fixed-point** values.
- `weights.quantization` MUST be `q8` or `q4`.
- `weights.dtype` MUST be `i8` (or `i4` if q4 is introduced later).
- `weights.scales` MUST provide the Q16 scale(s) used by the guest template.
- Float dtypes (`f32`, `f16`) are not allowed under this profile.

ModelKit SHOULD default to this profile for finance model templates.

## Exact validation rules

### Global
- [model], [abi], [schema], [limits], and [[segments]] MUST exist.
- `model.id` MUST match regex `[a-z0-9_-]+`.
- `model.version` MUST be valid semver.
- `model.arch` MUST be "rv64imac".
- `model.endianness` MUST be "little".
- `model.vaddr_bits` MUST be 32.
- `abi.entry` MUST be a u32 and MUST refer to segment 0 (top 4 bits = 0).
- `abi.alignment` MUST be 4 or 8.
- `abi.control_offset`, `abi.input_offset`, `abi.output_offset` MUST be aligned
  to `abi.alignment`.
- `abi.control_size` MUST be >= 64 bytes.
- `abi.scratch_min` MUST be >= 262144.
- `abi.reserved_tail` MUST be >= 32.
- Offsets MUST fit in scratch:
  - `control_offset + control_size <= scratch_min - reserved_tail`
  - `input_offset + input_max <= scratch_min - reserved_tail`
  - `output_offset + output_max <= scratch_min - reserved_tail`

### Segments
- `segments.index` MUST be unique and in [0, 15].
- A segment with `index = 0` MUST exist and MUST be `{kind="scratch",access="rw"}`.
- For `kind = "weights"`, `source` MUST be `weights:<name>` matching a
  `weights.blobs.name`.
- For `kind = "input"`, `source` MUST be `io:input`.
- For `kind = "output"`, `source` MUST be `io:output`.
- For `kind = "custom"`, `source` MUST be `custom:<label>`.

### Weights (if present)
- `[weights]` MUST exist if any `segments.kind = "weights"`.
- `weights.layout` and `weights.quantization` MUST be non-empty strings.
- `weights.blobs` MUST contain at least one entry.
- Each blob MUST define `name`, `file`, `hash`, `size_bytes`.
- `hash` MUST begin with `sha256:`.
- `size_bytes` MUST be > 0.
- `chunk_size` MUST be > 0 if specified.
- `data_offset` MUST be < 0x1000_0000.
- `data_offset + size_bytes` MUST be <= 0x1000_0000.
- If `weights.header_format = "rvcd-v1"` and `data_offset` is omitted,
  `data_offset = 12` is implied.

#### Weights scales (optional)

`[weights.scales]` is optional. If present, allowed keys are:
- `w_scale_q16`
- `w1_scale_q16`
- `w2_scale_q16`

All scale values MUST be positive i32 values interpreted as Q16 fixed-point.
ModelKit MAY inline these into guest template constants at build time.

### Schema-specific

#### Vector
- `input_shape` and `output_shape` MUST be non-empty arrays of positive ints.
- `input_dtype` and `output_dtype` MUST be in the dtype enum.
- `input_bytes = prod(input_shape) * sizeof(input_dtype)` MUST be <= `abi.input_max`.
- `output_bytes = prod(output_shape) * sizeof(output_dtype)` MUST be <= `abi.output_max`.

#### Time-series
- `window` and `features` MUST be >= 1.
- `stride` MUST be >= 1 if present.
- `input_dtype` and `output_dtype` MUST be in the dtype enum.
- `input_bytes = window * features * sizeof(input_dtype)` MUST be <= `abi.input_max`.
- `output_bytes = prod(output_shape) * sizeof(output_dtype)` MUST be <= `abi.output_max`.

#### Graph
- `max_nodes` MUST be >= 1.
- `max_edges` MUST be >= 0.
- `node_feature_dim` MUST be >= 1.
- `edge_feature_dim` MUST be >= 0.
- `input_dtype` and `output_dtype` MUST be in the dtype enum.
- Graph input bytes are computed as:
  - `header_bytes = 16` (u32 node_count, edge_count, reserved0, reserved1)
  - `node_bytes = max_nodes * node_feature_dim * sizeof(input_dtype)`
  - `edge_index_bytes = max_edges * 2 * 4` (u32 pairs)
  - `edge_feat_bytes = max_edges * edge_feature_dim * sizeof(input_dtype)`
  - `input_bytes = header_bytes + node_bytes + edge_index_bytes + edge_feat_bytes`
  - `input_bytes` MUST be <= `abi.input_max`
- `output_bytes = prod(output_shape) * sizeof(output_dtype)` MUST be <= `abi.output_max`.

#### Custom
- `input_blob_size` MUST be >= 1 and <= `abi.input_max`.
- `output_blob_size` MUST be >= 1 and <= `abi.output_max`.
- `alignment` MUST be 4 or 8 if present.
- If `schema_hash32` is present, it MUST be a 32-bit hex string `0x...`.

### Validation mode
- If `validation.mode = "guest"`, ModelKit MUST prepend a FBH1 header to input
  payload and the guest template MUST validate it before inference.

CRC32 is optional. If the FBH1 `has_crc32` flag is not set, no CRC validation
is performed.

## Notes
- This spec intentionally separates manifest validation from runtime behavior.
- Schema payload layouts beyond the size formulas are defined in the guest
  templates and SDK helpers.
