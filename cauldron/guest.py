"""Guest config generation and build helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
from typing import Any, Dict, Optional

from .constants import DEFAULT_SCRATCH_MIN, MIN_RESERVED_TAIL
from .convert import infer_template
from .manifest import load_manifest
from .schema import SCHEMA_IDS, parse_hash32, schema_hash32
from .util import product


DEFAULT_STACK_GUARD = 0x4000
DEFAULT_HIDDEN_OFFSET = 0x3000
DEFAULT_CONV_OFFSET = 0x3000
DEFAULT_Q16 = 1 << 16


@dataclass
class GuestConfig:
    template: str
    control_offset: int
    input_max: int
    output_max: int
    scratch_min: int
    reserved_tail: int
    stack_guard: int
    stack_ptr: int
    expected_schema_id: int
    expected_schema_hash: int
    input_dim: Optional[int] = None
    output_dim: Optional[int] = None
    hidden_dim: Optional[int] = None
    hidden_offset: Optional[int] = None
    hidden_dim1: Optional[int] = None
    hidden_dim2: Optional[int] = None
    hidden_dim3: Optional[int] = None
    hidden_offset1: Optional[int] = None
    hidden_offset2: Optional[int] = None
    hidden_offset3: Optional[int] = None
    input_blob_size: Optional[int] = None
    output_blob_size: Optional[int] = None
    weights_seg: Optional[int] = None
    weights_offset: Optional[int] = None
    weights_data_offset: Optional[int] = None
    w_scale_q16: Optional[int] = None
    w1_scale_q16: Optional[int] = None
    w2_scale_q16: Optional[int] = None
    w3_scale_q16: Optional[int] = None
    w4_scale_q16: Optional[int] = None
    has_bias: Optional[bool] = None
    apply_softmax: Optional[bool] = None
    input_dim_a: Optional[int] = None
    input_dim_b: Optional[int] = None
    embed_dim: Optional[int] = None
    embed_a_offset: Optional[int] = None
    embed_b_offset: Optional[int] = None
    dot_shift: Optional[int] = None
    tree_count: Optional[int] = None
    tree_node_count: Optional[int] = None
    tree_stride: Optional[int] = None
    input_len: Optional[int] = None
    input_channels: Optional[int] = None
    input_height: Optional[int] = None
    input_width: Optional[int] = None
    kernel_size: Optional[int] = None
    stride: Optional[int] = None
    out_channels: Optional[int] = None
    conv_offset: Optional[int] = None


def _get_table(manifest: Dict[str, Any], name: str) -> Dict[str, Any]:
    tbl = manifest.get(name)
    if isinstance(tbl, dict):
        return tbl
    return {}


def _resolve_schema(manifest: Dict[str, Any]) -> tuple[str, int, Optional[int], Optional[int], Optional[int], Optional[int]]:
    schema = _get_table(manifest, "schema")
    schema_type = schema.get("type")
    if schema_type not in SCHEMA_IDS:
        raise ValueError("schema.type must be vector, time_series, graph, or custom")
    schema_id = SCHEMA_IDS[schema_type]

    input_dim: Optional[int] = None
    output_dim: Optional[int] = None
    input_blob_size: Optional[int] = None
    output_blob_size: Optional[int] = None

    if schema_type == "vector":
        vec = _get_table(schema, "vector")
        input_shape = vec.get("input_shape")
        output_shape = vec.get("output_shape")
        if not isinstance(input_shape, list) or not isinstance(output_shape, list):
            raise ValueError("schema.vector input_shape/output_shape required")
        input_dim = product(input_shape)
        output_dim = product(output_shape)
    elif schema_type == "time_series":
        ts = _get_table(schema, "time_series")
        window = ts.get("window")
        features = ts.get("features")
        output_shape = ts.get("output_shape")
        if not isinstance(window, int) or not isinstance(features, int):
            raise ValueError("schema.time_series window/features required")
        if not isinstance(output_shape, list):
            raise ValueError("schema.time_series output_shape required")
        input_dim = window * features
        output_dim = product(output_shape)
    elif schema_type == "graph":
        gr = _get_table(schema, "graph")
        node_dim = gr.get("node_feature_dim")
        output_shape = gr.get("output_shape")
        if not isinstance(node_dim, int):
            raise ValueError("schema.graph node_feature_dim required")
        if not isinstance(output_shape, list):
            raise ValueError("schema.graph output_shape required")
        input_dim = node_dim
        output_dim = product(output_shape)
    elif schema_type == "custom":
        custom = _get_table(schema, "custom")
        input_blob_size = custom.get("input_blob_size")
        output_blob_size = custom.get("output_blob_size")
        if not isinstance(input_blob_size, int) or not isinstance(output_blob_size, int):
            raise ValueError("schema.custom input_blob_size/output_blob_size required")

    return schema_type, schema_id, input_dim, output_dim, input_blob_size, output_blob_size


def _resolve_weights(manifest: Dict[str, Any]) -> Dict[str, Any]:
    weights = _get_table(manifest, "weights")
    if not weights:
        return {}
    blobs = weights.get("blobs")
    if not isinstance(blobs, list) or not blobs:
        return {}
    blob = blobs[0]
    if not isinstance(blob, dict):
        return {}
    header_format = weights.get("header_format", "none")
    data_offset = blob.get("data_offset")
    if data_offset is None:
        if header_format == "rvcd-v1":
            data_offset = 12
        else:
            data_offset = 0
    seg_index = blob.get("segment_index")
    if seg_index is None:
        segments = manifest.get("segments")
        if isinstance(segments, list):
            for seg in segments:
                if not isinstance(seg, dict):
                    continue
                if seg.get("kind") == "weights":
                    seg_index = seg.get("index")
                    if isinstance(seg_index, int):
                        break
    return {
        "segment_index": seg_index,
        "data_offset": data_offset,
    }


def _resolve_stack(abi: Dict[str, Any], build: Dict[str, Any]) -> tuple[int, int, int, int]:
    scratch_min = abi.get("scratch_min", DEFAULT_SCRATCH_MIN)
    reserved_tail = abi.get("reserved_tail", MIN_RESERVED_TAIL)
    stack_guard = build.get("stack_guard", DEFAULT_STACK_GUARD)
    if not isinstance(scratch_min, int) or scratch_min <= 0:
        raise ValueError("abi.scratch_min must be a positive integer")
    if not isinstance(reserved_tail, int) or reserved_tail < 0:
        raise ValueError("abi.reserved_tail must be a non-negative integer")
    if not isinstance(stack_guard, int) or stack_guard < 0:
        raise ValueError("build.stack_guard must be a non-negative integer")
    if scratch_min <= reserved_tail + stack_guard:
        raise ValueError("scratch_min too small for stack guard and reserved_tail")
    stack_ptr = scratch_min - reserved_tail - stack_guard
    return scratch_min, reserved_tail, stack_guard, stack_ptr


def _resolve_expected_hash(manifest: Dict[str, Any], mode: str) -> int:
    if mode == "none":
        return 0
    if mode == "manifest":
        custom = _get_table(_get_table(manifest, "schema"), "custom")
        value = custom.get("schema_hash32")
        if isinstance(value, str):
            try:
                return parse_hash32(value)
            except ValueError:
                return 0
        return 0
    if mode == "auto":
        return schema_hash32(manifest)
    raise ValueError("schema-hash mode must be auto, manifest, or none")


def generate_guest_config(
    manifest: Dict[str, Any],
    template: str | None = None,
    schema_hash_mode: str = "auto",
) -> GuestConfig:
    weights = _resolve_weights(manifest)
    build = _get_table(manifest, "build")
    abi = _get_table(manifest, "abi")
    schema = _get_table(manifest, "schema")

    resolved_template = template or infer_template(_get_table(manifest, "weights").get("layout"))
    if resolved_template is None:
        schema_type = _get_table(manifest, "schema").get("type")
        if schema_type == "custom":
            resolved_template = "custom"
        else:
            raise ValueError("Unable to infer template; pass --template")

    schema_type, schema_id, input_dim, output_dim, input_blob_size, output_blob_size = _resolve_schema(manifest)

    if resolved_template in ("linear", "mlp", "mlp2", "mlp3", "softmax", "naive_bayes", "tree"):
        if schema_type not in ("vector", "time_series"):
            raise ValueError("schema type is incompatible with template")
    if resolved_template == "cnn1d" and schema_type != "time_series":
        raise ValueError("schema type is incompatible with cnn1d template")
    if resolved_template == "tiny_cnn" and schema_type != "vector":
        raise ValueError("schema type is incompatible with tiny_cnn template")
    if resolved_template == "two_tower" and schema_type != "vector":
        raise ValueError("schema type is incompatible with two_tower template")
    if resolved_template == "custom" and schema_type != "custom":
        raise ValueError("schema type is incompatible with custom template")

    scratch_min, reserved_tail, stack_guard, stack_ptr = _resolve_stack(abi, build)
    expected_hash = _resolve_expected_hash(manifest, schema_hash_mode)

    control_offset = abi.get("control_offset", 0)
    input_max = abi.get("input_max", 0)
    output_max = abi.get("output_max", 0)

    if not isinstance(control_offset, int):
        raise ValueError("abi.control_offset must be an integer")
    if not isinstance(input_max, int):
        raise ValueError("abi.input_max must be an integer")
    if not isinstance(output_max, int):
        raise ValueError("abi.output_max must be an integer")

    weights_seg = weights.get("segment_index")
    weights_data_offset = weights.get("data_offset")

    weights_offset = build.get("weights_offset", 0)
    if not isinstance(weights_offset, int):
        raise ValueError("build.weights_offset must be an integer when provided")

    has_bias = build.get("has_bias", True)

    scales = _get_table(manifest.get("weights", {}), "scales")

    config = GuestConfig(
        template=resolved_template,
        control_offset=control_offset,
        input_max=input_max,
        output_max=output_max,
        scratch_min=scratch_min,
        reserved_tail=reserved_tail,
        stack_guard=stack_guard,
        stack_ptr=stack_ptr,
        expected_schema_id=schema_id,
        expected_schema_hash=expected_hash,
    )

    if resolved_template in ("linear", "mlp", "mlp2", "mlp3", "softmax", "naive_bayes", "tree", "cnn1d", "tiny_cnn"):
        if input_dim is None or output_dim is None:
            raise ValueError("schema type is incompatible with template")
        config.input_dim = input_dim
        config.output_dim = output_dim
        config.weights_seg = weights_seg if isinstance(weights_seg, int) else 1
        config.weights_offset = weights_offset
        config.weights_data_offset = weights_data_offset if isinstance(weights_data_offset, int) else 0

    if resolved_template == "linear":
        config.w_scale_q16 = scales.get("w_scale_q16", DEFAULT_Q16)
        config.has_bias = bool(has_bias)

    if resolved_template in ("softmax", "naive_bayes"):
        config.w_scale_q16 = scales.get("w_scale_q16", DEFAULT_Q16)
        config.has_bias = bool(has_bias)
        apply_softmax = build.get("apply_softmax", True)
        config.apply_softmax = bool(apply_softmax)

    if resolved_template == "mlp":
        hidden_dim = build.get("hidden_dim")
        if not isinstance(hidden_dim, int):
            raise ValueError("build.hidden_dim is required for MLP templates")
        config.hidden_dim = hidden_dim
        hidden_offset = build.get("hidden_offset", DEFAULT_HIDDEN_OFFSET)
        if not isinstance(hidden_offset, int):
            raise ValueError("build.hidden_offset must be an integer when provided")
        config.hidden_offset = hidden_offset
        config.w1_scale_q16 = scales.get("w1_scale_q16", DEFAULT_Q16)
        config.w2_scale_q16 = scales.get("w2_scale_q16", DEFAULT_Q16)

    if resolved_template == "mlp2":
        hidden_dim1 = build.get("hidden_dim1")
        hidden_dim2 = build.get("hidden_dim2")
        if not isinstance(hidden_dim1, int) or not isinstance(hidden_dim2, int):
            raise ValueError("build.hidden_dim1 and build.hidden_dim2 required for mlp2")
        config.hidden_dim1 = hidden_dim1
        config.hidden_dim2 = hidden_dim2
        hidden_offset1 = build.get("hidden_offset1", DEFAULT_HIDDEN_OFFSET)
        if not isinstance(hidden_offset1, int):
            raise ValueError("build.hidden_offset1 must be an integer when provided")
        hidden_offset2 = build.get("hidden_offset2", hidden_offset1 + hidden_dim1 * 4)
        if not isinstance(hidden_offset2, int):
            raise ValueError("build.hidden_offset2 must be an integer when provided")
        config.hidden_offset1 = hidden_offset1
        config.hidden_offset2 = hidden_offset2
        config.w1_scale_q16 = scales.get("w1_scale_q16", DEFAULT_Q16)
        config.w2_scale_q16 = scales.get("w2_scale_q16", DEFAULT_Q16)
        config.w3_scale_q16 = scales.get("w3_scale_q16", DEFAULT_Q16)
        config.has_bias = bool(build.get("has_bias", True))

    if resolved_template == "mlp3":
        hidden_dim1 = build.get("hidden_dim1")
        hidden_dim2 = build.get("hidden_dim2")
        hidden_dim3 = build.get("hidden_dim3")
        if not isinstance(hidden_dim1, int) or not isinstance(hidden_dim2, int) or not isinstance(hidden_dim3, int):
            raise ValueError("build.hidden_dim1/hidden_dim2/hidden_dim3 required for mlp3")
        config.hidden_dim1 = hidden_dim1
        config.hidden_dim2 = hidden_dim2
        config.hidden_dim3 = hidden_dim3
        hidden_offset1 = build.get("hidden_offset1", DEFAULT_HIDDEN_OFFSET)
        if not isinstance(hidden_offset1, int):
            raise ValueError("build.hidden_offset1 must be an integer when provided")
        hidden_offset2 = build.get("hidden_offset2", hidden_offset1 + hidden_dim1 * 4)
        if not isinstance(hidden_offset2, int):
            raise ValueError("build.hidden_offset2 must be an integer when provided")
        hidden_offset3 = build.get("hidden_offset3", hidden_offset2 + hidden_dim2 * 4)
        if not isinstance(hidden_offset3, int):
            raise ValueError("build.hidden_offset3 must be an integer when provided")
        config.hidden_offset1 = hidden_offset1
        config.hidden_offset2 = hidden_offset2
        config.hidden_offset3 = hidden_offset3
        config.w1_scale_q16 = scales.get("w1_scale_q16", DEFAULT_Q16)
        config.w2_scale_q16 = scales.get("w2_scale_q16", DEFAULT_Q16)
        config.w3_scale_q16 = scales.get("w3_scale_q16", DEFAULT_Q16)
        config.w4_scale_q16 = scales.get("w4_scale_q16", DEFAULT_Q16)
        config.has_bias = bool(build.get("has_bias", True))

    if resolved_template == "custom":
        config.input_blob_size = input_blob_size
        config.output_blob_size = output_blob_size

    if resolved_template == "two_tower":
        if input_dim is None or output_dim is None:
            raise ValueError("schema input_dim required for two_tower")
        if output_dim != 1:
            raise ValueError("two_tower template requires output_dim = 1")
        input_dim_a = build.get("tower_input_a")
        input_dim_b = build.get("tower_input_b")
        embed_dim = build.get("embed_dim")
        if not isinstance(input_dim_a, int) or not isinstance(input_dim_b, int):
            raise ValueError("build.tower_input_a and build.tower_input_b required for two_tower")
        if not isinstance(embed_dim, int):
            raise ValueError("build.embed_dim required for two_tower")
        if input_dim_a + input_dim_b != input_dim:
            raise ValueError("tower_input_a + tower_input_b must equal schema input_dim")
        config.input_dim_a = input_dim_a
        config.input_dim_b = input_dim_b
        config.embed_dim = embed_dim
        config.output_dim = 1
        config.weights_seg = weights_seg if isinstance(weights_seg, int) else 1
        config.weights_offset = weights_offset
        config.weights_data_offset = weights_data_offset if isinstance(weights_data_offset, int) else 0
        config.w1_scale_q16 = scales.get("w1_scale_q16", DEFAULT_Q16)
        config.w2_scale_q16 = scales.get("w2_scale_q16", DEFAULT_Q16)
        config.has_bias = bool(build.get("has_bias", True))
        embed_offset = build.get("embed_offset", DEFAULT_HIDDEN_OFFSET)
        if not isinstance(embed_offset, int):
            raise ValueError("build.embed_offset must be an integer when provided")
        config.embed_a_offset = embed_offset
        config.embed_b_offset = embed_offset + embed_dim * 4
        config.dot_shift = int(build.get("dot_shift", 16))

    if resolved_template == "cnn1d":
        ts = _get_table(schema, "time_series")
        window = ts.get("window")
        features = ts.get("features")
        if not isinstance(window, int) or not isinstance(features, int):
            raise ValueError("schema.time_series window/features required for cnn1d")
        kernel_size = build.get("kernel_size")
        out_channels = build.get("out_channels")
        stride = build.get("stride", 1)
        conv_offset = build.get("conv_offset", DEFAULT_CONV_OFFSET)
        if not isinstance(kernel_size, int) or kernel_size < 1:
            raise ValueError("build.kernel_size required for cnn1d")
        if not isinstance(out_channels, int) or out_channels < 1:
            raise ValueError("build.out_channels required for cnn1d")
        if not isinstance(stride, int) or stride < 1:
            raise ValueError("build.stride must be >= 1 for cnn1d")
        if not isinstance(conv_offset, int):
            raise ValueError("build.conv_offset must be an integer when provided")
        config.input_len = window
        config.input_channels = features
        config.kernel_size = kernel_size
        config.out_channels = out_channels
        config.stride = stride
        config.conv_offset = conv_offset
        config.w1_scale_q16 = scales.get("w1_scale_q16", DEFAULT_Q16)
        config.w2_scale_q16 = scales.get("w2_scale_q16", DEFAULT_Q16)
        config.has_bias = bool(build.get("has_bias", True))

    if resolved_template == "tiny_cnn":
        vec = _get_table(schema, "vector")
        input_shape = vec.get("input_shape")
        input_height = build.get("input_height")
        input_width = build.get("input_width")
        if (input_height is None or input_width is None) and isinstance(input_shape, list) and len(input_shape) == 2:
            input_height, input_width = input_shape
        if not isinstance(input_height, int) or not isinstance(input_width, int):
            raise ValueError("build.input_height/input_width required for tiny_cnn")
        if input_height * input_width != config.input_dim:
            raise ValueError("tiny_cnn input_height * input_width must equal schema input_dim")
        kernel_size = build.get("kernel_size")
        out_channels = build.get("out_channels")
        stride = build.get("stride", 1)
        conv_offset = build.get("conv_offset", DEFAULT_CONV_OFFSET)
        if not isinstance(kernel_size, int) or kernel_size < 1:
            raise ValueError("build.kernel_size required for tiny_cnn")
        if not isinstance(out_channels, int) or out_channels < 1:
            raise ValueError("build.out_channels required for tiny_cnn")
        if not isinstance(stride, int) or stride < 1:
            raise ValueError("build.stride must be >= 1 for tiny_cnn")
        if not isinstance(conv_offset, int):
            raise ValueError("build.conv_offset must be an integer when provided")
        config.input_height = input_height
        config.input_width = input_width
        config.kernel_size = kernel_size
        config.out_channels = out_channels
        config.stride = stride
        config.conv_offset = conv_offset
        config.w1_scale_q16 = scales.get("w1_scale_q16", DEFAULT_Q16)
        config.w2_scale_q16 = scales.get("w2_scale_q16", DEFAULT_Q16)
        config.has_bias = bool(build.get("has_bias", True))

    if resolved_template == "tree":
        tree_count = build.get("tree_count", 1)
        tree_node_count = build.get("tree_node_count")
        tree_stride = build.get("tree_stride")
        if not isinstance(tree_count, int) or tree_count < 1:
            raise ValueError("build.tree_count must be >= 1 for tree template")
        if not isinstance(tree_node_count, int) or tree_node_count < 1:
            raise ValueError("build.tree_node_count required for tree template")
        if tree_stride is None:
            tree_stride = tree_node_count * 20
        if not isinstance(tree_stride, int) or tree_stride <= 0:
            raise ValueError("build.tree_stride must be a positive integer when provided")
        if config.output_dim != 1:
            raise ValueError("tree template requires output_dim = 1")
        config.tree_count = tree_count
        config.tree_node_count = tree_node_count
        config.tree_stride = tree_stride

    return config


def render_config(config: GuestConfig) -> str:
    lines = ["//! Auto-generated config constants (patched by Cauldron).", ""]
    lines.append(f"pub const CONTROL_OFFSET: usize = 0x{config.control_offset:04X};")
    lines.append(f"pub const INPUT_MAX: usize = {config.input_max};")
    lines.append(f"pub const OUTPUT_MAX: usize = {config.output_max};")
    lines.append("")
    lines.append(f"pub const SCRATCH_MIN: usize = {config.scratch_min};")
    lines.append(f"pub const RESERVED_TAIL: usize = {config.reserved_tail};")
    lines.append(f"pub const STACK_GUARD: usize = 0x{config.stack_guard:X};")
    lines.append(f"pub const STACK_PTR: usize = {config.stack_ptr};")

    if config.template in ("linear", "mlp", "mlp2", "mlp3", "softmax", "naive_bayes", "tree", "cnn1d", "tiny_cnn"):
        lines.append("")
        lines.append(f"pub const INPUT_DIM: usize = {config.input_dim};")
        if config.template == "mlp":
            lines.append(f"pub const HIDDEN_DIM: usize = {config.hidden_dim};")
        lines.append(f"pub const OUTPUT_DIM: usize = {config.output_dim};")
        lines.append("")
        lines.append(f"pub const WEIGHTS_SEG: u32 = {config.weights_seg};")
        lines.append(f"pub const WEIGHTS_OFFSET: usize = {config.weights_offset};")
        lines.append(f"pub const WEIGHTS_DATA_OFFSET: usize = {config.weights_data_offset};")

    if config.template == "linear":
        lines.append("")
        lines.append(f"pub const W_SCALE_Q16: i32 = {config.w_scale_q16};")
        lines.append(f"pub const HAS_BIAS: bool = {str(bool(config.has_bias)).lower()};")

    if config.template in ("softmax", "naive_bayes"):
        lines.append("")
        lines.append(f"pub const W_SCALE_Q16: i32 = {config.w_scale_q16};")
        lines.append(f"pub const HAS_BIAS: bool = {str(bool(config.has_bias)).lower()};")
        lines.append(f"pub const APPLY_SOFTMAX: bool = {str(bool(config.apply_softmax)).lower()};")

    if config.template == "mlp":
        lines.append("")
        lines.append(f"pub const W1_SCALE_Q16: i32 = {config.w1_scale_q16};")
        lines.append(f"pub const W2_SCALE_Q16: i32 = {config.w2_scale_q16};")
        lines.append("")
        lines.append(f"pub const HIDDEN_OFFSET: usize = 0x{config.hidden_offset:X};")

    if config.template == "mlp2":
        lines.append("")
        lines.append(f"pub const HIDDEN_DIM1: usize = {config.hidden_dim1};")
        lines.append(f"pub const HIDDEN_DIM2: usize = {config.hidden_dim2};")
        lines.append(f"pub const W1_SCALE_Q16: i32 = {config.w1_scale_q16};")
        lines.append(f"pub const W2_SCALE_Q16: i32 = {config.w2_scale_q16};")
        lines.append(f"pub const W3_SCALE_Q16: i32 = {config.w3_scale_q16};")
        lines.append(f"pub const HAS_BIAS: bool = {str(bool(config.has_bias)).lower()};")
        lines.append("")
        lines.append(f"pub const HIDDEN1_OFFSET: usize = 0x{config.hidden_offset1:X};")
        lines.append(f"pub const HIDDEN2_OFFSET: usize = 0x{config.hidden_offset2:X};")

    if config.template == "mlp3":
        lines.append("")
        lines.append(f"pub const HIDDEN_DIM1: usize = {config.hidden_dim1};")
        lines.append(f"pub const HIDDEN_DIM2: usize = {config.hidden_dim2};")
        lines.append(f"pub const HIDDEN_DIM3: usize = {config.hidden_dim3};")
        lines.append(f"pub const W1_SCALE_Q16: i32 = {config.w1_scale_q16};")
        lines.append(f"pub const W2_SCALE_Q16: i32 = {config.w2_scale_q16};")
        lines.append(f"pub const W3_SCALE_Q16: i32 = {config.w3_scale_q16};")
        lines.append(f"pub const W4_SCALE_Q16: i32 = {config.w4_scale_q16};")
        lines.append(f"pub const HAS_BIAS: bool = {str(bool(config.has_bias)).lower()};")
        lines.append("")
        lines.append(f"pub const HIDDEN1_OFFSET: usize = 0x{config.hidden_offset1:X};")
        lines.append(f"pub const HIDDEN2_OFFSET: usize = 0x{config.hidden_offset2:X};")
        lines.append(f"pub const HIDDEN3_OFFSET: usize = 0x{config.hidden_offset3:X};")

    if config.template == "cnn1d":
        lines.append("")
        lines.append(f"pub const INPUT_LEN: usize = {config.input_len};")
        lines.append(f"pub const INPUT_CHANNELS: usize = {config.input_channels};")
        lines.append(f"pub const KERNEL_SIZE: usize = {config.kernel_size};")
        lines.append(f"pub const STRIDE: usize = {config.stride};")
        lines.append(f"pub const OUT_CHANNELS: usize = {config.out_channels};")
        lines.append(f"pub const W1_SCALE_Q16: i32 = {config.w1_scale_q16};")
        lines.append(f"pub const W2_SCALE_Q16: i32 = {config.w2_scale_q16};")
        lines.append(f"pub const HAS_BIAS: bool = {str(bool(config.has_bias)).lower()};")
        lines.append("")
        lines.append(f"pub const CONV_OFFSET: usize = 0x{config.conv_offset:X};")

    if config.template == "tiny_cnn":
        lines.append("")
        lines.append(f"pub const INPUT_HEIGHT: usize = {config.input_height};")
        lines.append(f"pub const INPUT_WIDTH: usize = {config.input_width};")
        lines.append(f"pub const KERNEL_SIZE: usize = {config.kernel_size};")
        lines.append(f"pub const STRIDE: usize = {config.stride};")
        lines.append(f"pub const OUT_CHANNELS: usize = {config.out_channels};")
        lines.append(f"pub const W1_SCALE_Q16: i32 = {config.w1_scale_q16};")
        lines.append(f"pub const W2_SCALE_Q16: i32 = {config.w2_scale_q16};")
        lines.append(f"pub const HAS_BIAS: bool = {str(bool(config.has_bias)).lower()};")
        lines.append("")
        lines.append(f"pub const CONV_OFFSET: usize = 0x{config.conv_offset:X};")

    if config.template == "two_tower":
        lines.append("")
        lines.append(f"pub const INPUT_DIM_A: usize = {config.input_dim_a};")
        lines.append(f"pub const INPUT_DIM_B: usize = {config.input_dim_b};")
        lines.append(f"pub const EMBED_DIM: usize = {config.embed_dim};")
        lines.append(f"pub const OUTPUT_DIM: usize = {config.output_dim};")
        lines.append("")
        lines.append(f"pub const WEIGHTS_SEG: u32 = {config.weights_seg};")
        lines.append(f"pub const WEIGHTS_OFFSET: usize = {config.weights_offset};")
        lines.append(f"pub const WEIGHTS_DATA_OFFSET: usize = {config.weights_data_offset};")
        lines.append("")
        lines.append(f"pub const W1_SCALE_Q16: i32 = {config.w1_scale_q16};")
        lines.append(f"pub const W2_SCALE_Q16: i32 = {config.w2_scale_q16};")
        lines.append(f"pub const HAS_BIAS: bool = {str(bool(config.has_bias)).lower()};")
        lines.append(f"pub const DOT_SHIFT: u32 = {config.dot_shift};")
        lines.append("")
        lines.append(f"pub const EMBED_A_OFFSET: usize = 0x{config.embed_a_offset:X};")
        lines.append(f"pub const EMBED_B_OFFSET: usize = 0x{config.embed_b_offset:X};")

    if config.template == "tree":
        lines.append("")
        lines.append(f"pub const TREE_COUNT: usize = {config.tree_count};")
        lines.append(f"pub const TREE_NODE_COUNT: usize = {config.tree_node_count};")
        lines.append(f"pub const TREE_STRIDE: usize = {config.tree_stride};")

    if config.template == "custom":
        lines.append("")
        lines.append(f"pub const INPUT_BLOB_SIZE: usize = {config.input_blob_size};")
        lines.append(f"pub const OUTPUT_BLOB_SIZE: usize = {config.output_blob_size};")

    lines.append("")
    lines.append(f"pub const EXPECTED_SCHEMA_HASH: u32 = 0x{config.expected_schema_hash:08X};")
    lines.append(f"pub const EXPECTED_SCHEMA_ID: u32 = {config.expected_schema_id};")
    lines.append("")
    return "\n".join(lines)


def write_guest_config(
    manifest_path: Path,
    guest_dir: Path,
    template: str | None = None,
    schema_hash_mode: str = "auto",
) -> Path:
    manifest = load_manifest(manifest_path)
    cfg = generate_guest_config(manifest, template=template, schema_hash_mode=schema_hash_mode)
    out_dir = guest_dir / "src"
    out_dir.mkdir(parents=True, exist_ok=True)
    config_path = out_dir / "config.rs"
    config_path.write_text(render_config(cfg))
    return config_path


def build_guest(
    guest_dir: Path,
    target: str = "riscv64imac-unknown-none-elf",
    release: bool = True,
) -> int:
    cmd = ["cargo", "build", "--target", target]
    if release:
        cmd.append("--release")

    proc = subprocess.run(cmd, cwd=str(guest_dir))
    if proc.returncode == 0:
        return 0

    # Auto-install target if missing
    if target in ("riscv64imac-unknown-none-elf", "riscv64im-unknown-none-elf"):
        install = subprocess.run(["rustup", "target", "add", target])
        if install.returncode != 0:
            return proc.returncode
        proc = subprocess.run(cmd, cwd=str(guest_dir))
    return proc.returncode
