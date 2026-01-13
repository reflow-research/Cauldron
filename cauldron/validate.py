"""Manifest validation against the Frostbite spec."""

from __future__ import annotations

from typing import Any, Dict, List

from .constants import (
    ALLOWED_ARCH,
    ALLOWED_ENDIANNESS,
    ALLOWED_HEADER_FORMAT,
    ALLOWED_PROFILE,
    ALLOWED_QUANT,
    ALLOWED_SCHEMA_TYPES,
    ALLOWED_SEGMENT_ACCESS,
    ALLOWED_SEGMENT_KIND,
    ALLOWED_VALIDATION_MODE,
    DTYPE_SIZES,
    DEFAULT_SCRATCH_MIN,
    MAX_SEGMENT_BYTES,
    MIN_CONTROL_SIZE,
    MIN_RESERVED_TAIL,
    SCALE_KEYS,
)
from .util import is_semver, is_slug, product


class ValidationError(Exception):
    """Raised when a manifest fails validation."""


def validate_manifest(manifest: Dict[str, Any]) -> List[str]:
    errors: List[str] = []

    def err(msg: str) -> None:
        errors.append(msg)

    # Required tables
    for key in ("model", "abi", "schema", "segments", "limits"):
        if key not in manifest:
            err(f"Missing required table: [{key}]")

    # Unknown top-level keys (allow build/metadata)
    allowed_top = {"model", "abi", "schema", "segments", "weights", "limits", "validation", "build", "metadata"}
    for key in manifest.keys():
        if key not in allowed_top:
            err(f"Unknown top-level key: {key}")

    model = manifest.get("model")
    abi = manifest.get("abi")
    schema = manifest.get("schema")
    limits = manifest.get("limits")
    segments = manifest.get("segments")
    weights = manifest.get("weights")
    validation = manifest.get("validation")

    # Model
    if model is None:
        err("model table missing")
    elif not isinstance(model, dict):
        err("model must be a table")
    else:
        allowed_model_keys = {"id", "version", "abi_version", "arch", "endianness", "vaddr_bits", "profile"}
        for key in model.keys():
            if key not in allowed_model_keys:
                err(f"Unknown model key: {key}")
        mid = model.get("id")
        if not isinstance(mid, str) or not is_slug(mid):
            err("model.id must be a slug: [a-z0-9_-]+")
        mver = model.get("version")
        if not isinstance(mver, str) or not is_semver(mver):
            err("model.version must be semver (X.Y.Z)")
        arch = model.get("arch")
        if arch not in ALLOWED_ARCH:
            err("model.arch must be 'rv64imac'")
        endian = model.get("endianness")
        if endian not in ALLOWED_ENDIANNESS:
            err("model.endianness must be 'little'")
        vaddr_bits = model.get("vaddr_bits")
        if vaddr_bits != 32:
            err("model.vaddr_bits must be 32")
        profile = model.get("profile")
        if profile is not None and profile not in ALLOWED_PROFILE:
            err("model.profile must be 'finance-int' when provided")

    # ABI
    if abi is None:
        err("abi table missing")
    elif not isinstance(abi, dict):
        err("abi must be a table")
    else:
        allowed_abi_keys = {
            "entry",
            "control_offset",
            "control_size",
            "input_offset",
            "input_max",
            "output_offset",
            "output_max",
            "scratch_min",
            "alignment",
            "reserved_tail",
        }
        for key in abi.keys():
            if key not in allowed_abi_keys:
                err(f"Unknown abi key: {key}")

        entry = abi.get("entry")
        if not isinstance(entry, int):
            err("abi.entry must be an integer")
        elif entry >> 28 != 0:
            err("abi.entry must reside in segment 0 (top 4 bits = 0)")

        alignment = abi.get("alignment")
        if alignment not in (4, 8):
            err("abi.alignment must be 4 or 8")

        control_offset = abi.get("control_offset")
        control_size = abi.get("control_size")
        input_offset = abi.get("input_offset")
        input_max = abi.get("input_max")
        output_offset = abi.get("output_offset")
        output_max = abi.get("output_max")
        scratch_min = abi.get("scratch_min", DEFAULT_SCRATCH_MIN)
        reserved_tail = abi.get("reserved_tail", MIN_RESERVED_TAIL)

        for name, val in (
            ("abi.control_offset", control_offset),
            ("abi.input_offset", input_offset),
            ("abi.output_offset", output_offset),
        ):
            if not isinstance(val, int):
                err(f"{name} must be an integer")
            elif alignment in (4, 8) and (val % alignment != 0):
                err(f"{name} must be aligned to abi.alignment")

        if not isinstance(control_size, int) or control_size < MIN_CONTROL_SIZE:
            err("abi.control_size must be >= 64")
        if not isinstance(input_max, int) or input_max <= 0:
            err("abi.input_max must be a positive integer")
        if not isinstance(output_max, int) or output_max <= 0:
            err("abi.output_max must be a positive integer")
        if not isinstance(scratch_min, int) or scratch_min < DEFAULT_SCRATCH_MIN:
            err("abi.scratch_min must be >= 262144")
        if not isinstance(reserved_tail, int) or reserved_tail < MIN_RESERVED_TAIL:
            err("abi.reserved_tail must be >= 32")

        if (
            isinstance(control_offset, int)
            and isinstance(control_size, int)
            and isinstance(scratch_min, int)
            and isinstance(reserved_tail, int)
        ):
            if control_offset + control_size > scratch_min - reserved_tail:
                err("control_offset + control_size exceeds scratch bounds")

        if (
            isinstance(input_offset, int)
            and isinstance(input_max, int)
            and isinstance(scratch_min, int)
            and isinstance(reserved_tail, int)
        ):
            if input_offset + input_max > scratch_min - reserved_tail:
                err("input_offset + input_max exceeds scratch bounds")

        if (
            isinstance(output_offset, int)
            and isinstance(output_max, int)
            and isinstance(scratch_min, int)
            and isinstance(reserved_tail, int)
        ):
            if output_offset + output_max > scratch_min - reserved_tail:
                err("output_offset + output_max exceeds scratch bounds")

    # Segments
    if segments is None:
        err("segments table missing")
    elif not isinstance(segments, list) or not segments:
        err("segments must be a non-empty array")
    else:
        seen = set()
        has_scratch = False
        for seg in segments:
            if not isinstance(seg, dict):
                err("segments entries must be tables")
                continue
            idx = seg.get("index")
            kind = seg.get("kind")
            access = seg.get("access")
            source = seg.get("source")
            allowed_seg_keys = {"index", "kind", "access", "source"}
            for key in seg.keys():
                if key not in allowed_seg_keys:
                    err(f"Unknown segments key: {key}")
            if not isinstance(idx, int) or not (0 <= idx <= 15):
                err("segments.index must be 0..15")
            elif idx in seen:
                err("segments.index values must be unique")
            else:
                seen.add(idx)
            if kind not in ALLOWED_SEGMENT_KIND:
                err("segments.kind is invalid")
            if access not in ALLOWED_SEGMENT_ACCESS:
                err("segments.access is invalid")
            if idx == 0:
                if kind != "scratch" or access != "rw":
                    err("segment 0 must be scratch with rw access")
                has_scratch = True
            if kind == "weights":
                if not isinstance(source, str) or not source.startswith("weights:"):
                    err("weights segment source must be weights:<name>")
            if kind == "input" and source != "io:input":
                err("input segment source must be io:input")
            if kind == "output" and source != "io:output":
                err("output segment source must be io:output")
            if kind == "custom":
                if not isinstance(source, str) or not source.startswith("custom:"):
                    err("custom segment source must be custom:<label>")
        if not has_scratch:
            err("segments must include index=0 scratch segment")

    # Weights
    has_weight_segment = any(
        isinstance(seg, dict) and seg.get("kind") == "weights" for seg in segments or []
    )
    if has_weight_segment and not isinstance(weights, dict):
        err("weights table is required when weights segments exist")

    blob_names = set()
    if isinstance(weights, dict):
        allowed_weights_keys = {"layout", "quantization", "dtype", "scale", "header_format", "blobs", "scales"}
        for key in weights.keys():
            if key not in allowed_weights_keys:
                err(f"Unknown weights key: {key}")
        layout_val = weights.get("layout")
        if not isinstance(layout_val, str) or not layout_val:
            err("weights.layout must be a non-empty string")
        if weights.get("quantization") not in ALLOWED_QUANT:
            err("weights.quantization is invalid")
        header_fmt = weights.get("header_format", "none")
        if header_fmt not in ALLOWED_HEADER_FORMAT:
            err("weights.header_format is invalid")

        blobs = weights.get("blobs")
        if not isinstance(blobs, list) or not blobs:
            err("weights.blobs must be a non-empty array")
        else:
            for blob in blobs:
                if not isinstance(blob, dict):
                    err("weights.blobs entries must be tables")
                    continue
                allowed_blob_keys = {
                    "name",
                    "file",
                    "hash",
                    "size_bytes",
                    "chunk_size",
                    "data_offset",
                    "segment_index",
                }
                for key in blob.keys():
                    if key not in allowed_blob_keys:
                        err(f"Unknown weights.blobs key: {key}")
                name = blob.get("name")
                if not isinstance(name, str) or not name:
                    err("weights.blobs.name must be a string")
                else:
                    if name in blob_names:
                        err("weights.blobs.name must be unique")
                    blob_names.add(name)

                if not isinstance(blob.get("file"), str):
                    err("weights.blobs.file must be a string")
                h = blob.get("hash")
                if not isinstance(h, str) or not h.startswith("sha256:"):
                    err("weights.blobs.hash must start with sha256:")
                size_bytes = blob.get("size_bytes")
                if not isinstance(size_bytes, int) or size_bytes <= 0:
                    err("weights.blobs.size_bytes must be > 0")
                chunk_size = blob.get("chunk_size")
                if chunk_size is not None and (not isinstance(chunk_size, int) or chunk_size <= 0):
                    err("weights.blobs.chunk_size must be > 0 when provided")
                data_offset = blob.get("data_offset")
                if data_offset is not None and (not isinstance(data_offset, int) or data_offset < 0):
                    err("weights.blobs.data_offset must be >= 0")

                effective_offset = None
                if isinstance(data_offset, int):
                    effective_offset = data_offset
                elif header_fmt == "rvcd-v1":
                    effective_offset = 12
                else:
                    effective_offset = 0

                if isinstance(size_bytes, int) and isinstance(effective_offset, int):
                    if effective_offset + size_bytes > MAX_SEGMENT_BYTES:
                        err("weights blob exceeds segment limit")

        scales = weights.get("scales")
        if scales is not None:
            if not isinstance(scales, dict):
                err("weights.scales must be a table")
            else:
                for key in scales:
                    if key not in SCALE_KEYS:
                        err(f"weights.scales.{key} is not allowed")
                for key, val in scales.items():
                    if not isinstance(val, int) or val <= 0:
                        err(f"weights.scales.{key} must be positive integer")

        # Ensure all weights segments reference an existing blob
        if blob_names and isinstance(segments, list):
            for seg in segments:
                if not isinstance(seg, dict):
                    continue
                if seg.get("kind") != "weights":
                    continue
                source = seg.get("source")
                if isinstance(source, str) and source.startswith("weights:"):
                    name = source.split(":", 1)[1]
                    if name not in blob_names:
                        err(f"weights segment references unknown blob: {name}")

    # Schema
    schema_type = schema.get("type") if isinstance(schema, dict) else None
    if schema_type not in ALLOWED_SCHEMA_TYPES:
        err("schema.type must be one of: vector, time_series, graph, custom")
    else:
        # exactly one schema subtable
        subtable = schema.get(schema_type)
        if not isinstance(subtable, dict):
            err(f"schema.{schema_type} table is required")
    if schema is None:
        err("schema table missing")
    elif not isinstance(schema, dict):
        err("schema must be a table")
    else:
        allowed_schema_keys = {"type", "vector", "time_series", "graph", "custom"}
        for key in schema.keys():
            if key not in allowed_schema_keys:
                err(f"Unknown schema key: {key}")
        # Reject extra schema subtables beyond schema.type
        if schema_type in ALLOWED_SCHEMA_TYPES:
            for key in ("vector", "time_series", "graph", "custom"):
                if key != schema_type and key in schema:
                    err(f"schema.{key} must not be present when type={schema_type}")

    def dtype_size(name: str) -> int:
        size = DTYPE_SIZES.get(name)
        if size is None:
            err(f"Unsupported dtype: {name}")
            return 0
        return size

    def ensure_pos_int_list(values, label: str) -> bool:
        if not isinstance(values, list) or not values:
            err(f"{label} must be a non-empty array")
            return False
        ok = True
        for v in values:
            if not isinstance(v, int) or v <= 0:
                err(f"{label} must contain positive integers")
                ok = False
        return ok

    if schema_type == "vector" and isinstance(schema.get("vector"), dict):
        s = schema["vector"]
        allowed_vec_keys = {"input_dtype", "input_shape", "output_dtype", "output_shape"}
        for key in s.keys():
            if key not in allowed_vec_keys:
                err(f"Unknown schema.vector key: {key}")
        in_dt = s.get("input_dtype")
        out_dt = s.get("output_dtype")
        in_shape = s.get("input_shape")
        out_shape = s.get("output_shape")
        if in_dt not in DTYPE_SIZES:
            err("schema.vector.input_dtype is invalid")
        if out_dt not in DTYPE_SIZES:
            err("schema.vector.output_dtype is invalid")
        in_shape_ok = ensure_pos_int_list(in_shape, "schema.vector.input_shape")
        out_shape_ok = ensure_pos_int_list(out_shape, "schema.vector.output_shape")
        if in_dt in DTYPE_SIZES and in_shape_ok and isinstance(abi, dict):
            input_bytes = product(in_shape) * dtype_size(in_dt)
            if isinstance(abi.get("input_max"), int) and input_bytes > abi["input_max"]:
                err("schema.vector input exceeds abi.input_max")
        if out_dt in DTYPE_SIZES and out_shape_ok and isinstance(abi, dict):
            output_bytes = product(out_shape) * dtype_size(out_dt)
            if isinstance(abi.get("output_max"), int) and output_bytes > abi["output_max"]:
                err("schema.vector output exceeds abi.output_max")

    if schema_type == "time_series" and isinstance(schema.get("time_series"), dict):
        s = schema["time_series"]
        allowed_ts_keys = {"input_dtype", "window", "features", "stride", "output_dtype", "output_shape"}
        for key in s.keys():
            if key not in allowed_ts_keys:
                err(f"Unknown schema.time_series key: {key}")
        in_dt = s.get("input_dtype")
        out_dt = s.get("output_dtype")
        window = s.get("window")
        features = s.get("features")
        stride = s.get("stride")
        if not isinstance(window, int) or window < 1:
            err("schema.time_series.window must be >= 1")
        if not isinstance(features, int) or features < 1:
            err("schema.time_series.features must be >= 1")
        if stride is not None and (not isinstance(stride, int) or stride < 1):
            err("schema.time_series.stride must be >= 1")
        if in_dt not in DTYPE_SIZES:
            err("schema.time_series.input_dtype is invalid")
        if out_dt not in DTYPE_SIZES:
            err("schema.time_series.output_dtype is invalid")
        if in_dt in DTYPE_SIZES and isinstance(window, int) and isinstance(features, int) and isinstance(abi, dict):
            input_bytes = window * features * dtype_size(in_dt)
            if isinstance(abi.get("input_max"), int) and input_bytes > abi["input_max"]:
                err("schema.time_series input exceeds abi.input_max")
        out_shape = s.get("output_shape")
        out_shape_ok = ensure_pos_int_list(out_shape, "schema.time_series.output_shape")
        if out_dt in DTYPE_SIZES and out_shape_ok and isinstance(abi, dict):
            output_bytes = product(out_shape) * dtype_size(out_dt)
            if isinstance(abi.get("output_max"), int) and output_bytes > abi["output_max"]:
                err("schema.time_series output exceeds abi.output_max")

    if schema_type == "graph" and isinstance(schema.get("graph"), dict):
        s = schema["graph"]
        allowed_graph_keys = {
            "input_dtype",
            "node_feature_dim",
            "edge_feature_dim",
            "max_nodes",
            "max_edges",
            "output_dtype",
            "output_shape",
        }
        for key in s.keys():
            if key not in allowed_graph_keys:
                err(f"Unknown schema.graph key: {key}")
        in_dt = s.get("input_dtype")
        out_dt = s.get("output_dtype")
        max_nodes = s.get("max_nodes")
        max_edges = s.get("max_edges")
        node_dim = s.get("node_feature_dim")
        edge_dim = s.get("edge_feature_dim")
        if not isinstance(max_nodes, int) or max_nodes < 1:
            err("schema.graph.max_nodes must be >= 1")
        if not isinstance(max_edges, int) or max_edges < 0:
            err("schema.graph.max_edges must be >= 0")
        if not isinstance(node_dim, int) or node_dim < 1:
            err("schema.graph.node_feature_dim must be >= 1")
        if not isinstance(edge_dim, int) or edge_dim < 0:
            err("schema.graph.edge_feature_dim must be >= 0")
        if in_dt not in DTYPE_SIZES:
            err("schema.graph.input_dtype is invalid")
        if out_dt not in DTYPE_SIZES:
            err("schema.graph.output_dtype is invalid")
        if (
            in_dt in DTYPE_SIZES
            and isinstance(max_nodes, int)
            and isinstance(max_edges, int)
            and isinstance(node_dim, int)
            and isinstance(edge_dim, int)
            and node_dim >= 1
            and edge_dim >= 0
            and isinstance(abi, dict)
        ):
            header_bytes = 16
            node_bytes = max_nodes * node_dim * dtype_size(in_dt)
            edge_index_bytes = max_edges * 2 * 4
            edge_feat_bytes = max_edges * edge_dim * dtype_size(in_dt)
            input_bytes = header_bytes + node_bytes + edge_index_bytes + edge_feat_bytes
            if isinstance(abi.get("input_max"), int) and input_bytes > abi["input_max"]:
                err("schema.graph input exceeds abi.input_max")
        out_shape = s.get("output_shape")
        out_shape_ok = ensure_pos_int_list(out_shape, "schema.graph.output_shape")
        if out_dt in DTYPE_SIZES and out_shape_ok and isinstance(abi, dict):
            output_bytes = product(out_shape) * dtype_size(out_dt)
            if isinstance(abi.get("output_max"), int) and output_bytes > abi["output_max"]:
                err("schema.graph output exceeds abi.output_max")

    if schema_type == "custom" and isinstance(schema.get("custom"), dict):
        s = schema["custom"]
        allowed_custom_keys = {
            "input_blob_size",
            "output_blob_size",
            "alignment",
            "layout_doc",
            "schema_hash32",
            "fields",
        }
        for key in s.keys():
            if key not in allowed_custom_keys:
                err(f"Unknown schema.custom key: {key}")
        in_blob = s.get("input_blob_size")
        out_blob = s.get("output_blob_size")
        if not isinstance(in_blob, int) or in_blob < 1:
            err("schema.custom.input_blob_size must be >= 1")
        if not isinstance(out_blob, int) or out_blob < 1:
            err("schema.custom.output_blob_size must be >= 1")
        if isinstance(abi, dict) and isinstance(abi.get("input_max"), int) and isinstance(in_blob, int):
            if in_blob > abi["input_max"]:
                err("schema.custom input_blob_size exceeds abi.input_max")
        if isinstance(abi, dict) and isinstance(abi.get("output_max"), int) and isinstance(out_blob, int):
            if out_blob > abi["output_max"]:
                err("schema.custom output_blob_size exceeds abi.output_max")
        align = s.get("alignment")
        if align is not None and align not in (4, 8):
            err("schema.custom.alignment must be 4 or 8")
        sch = s.get("schema_hash32")
        if sch is not None:
            if not isinstance(sch, str):
                err("schema.custom.schema_hash32 must be a hex string")
            else:
                if not (sch.startswith("0x") and len(sch) == 10):
                    err("schema.custom.schema_hash32 must be 32-bit hex (0xXXXXXXXX)")
                else:
                    hex_part = sch[2:]
                    try:
                        int(hex_part, 16)
                    except ValueError:
                        err("schema.custom.schema_hash32 must be 32-bit hex (0xXXXXXXXX)")

    # Profile enforcement
    if isinstance(model, dict) and model.get("profile") == "finance-int":
        # enforce integer IO
        stype = schema_type
        if stype in ("vector", "time_series", "graph"):
            s = schema.get(stype, {}) if isinstance(schema, dict) else {}
            if s.get("input_dtype") != "i32":
                err("finance-int requires input_dtype=i32")
            if s.get("output_dtype") != "i32":
                err("finance-int requires output_dtype=i32")
        if isinstance(weights, dict):
            layout = weights.get("layout")
            layout_str = layout.lower() if isinstance(layout, str) else ""
            is_tree_layout = "tree" in layout_str or "gbdt" in layout_str
            if is_tree_layout:
                if weights.get("quantization") not in ("custom",):
                    err("finance-int tree requires weights.quantization custom")
                if weights.get("dtype") not in ("i32",):
                    err("finance-int tree requires weights.dtype i32")
            else:
                if weights.get("quantization") not in ("q8", "q4"):
                    err("finance-int requires weights.quantization q8 or q4")
                if weights.get("dtype") not in ("i8",):
                    err("finance-int requires weights.dtype i8")
                if not isinstance(weights.get("scales"), dict):
                    err("finance-int requires weights.scales with Q16 values")

    # Validation mode
    if validation is not None:
        if not isinstance(validation, dict):
            err("validation must be a table")
        else:
            allowed_validation_keys = {"mode"}
            for key in validation.keys():
                if key not in allowed_validation_keys:
                    err(f"Unknown validation key: {key}")
            mode = validation.get("mode")
            if mode not in ALLOWED_VALIDATION_MODE:
                err("validation.mode must be minimal or guest")

    # Limits
    if limits is None:
        err("limits table missing")
    elif not isinstance(limits, dict):
        err("limits must be a table")
    else:
        allowed_limits_keys = {"max_instructions", "cu_budget"}
        for key in limits.keys():
            if key not in allowed_limits_keys:
                err(f"Unknown limits key: {key}")
        if not isinstance(limits.get("max_instructions"), int):
            err("limits.max_instructions must be an integer")
        if not isinstance(limits.get("cu_budget"), int):
            err("limits.cu_budget must be an integer")

    return errors


def raise_on_errors(errors: List[str]) -> None:
    if errors:
        raise ValidationError("\n".join(errors))
