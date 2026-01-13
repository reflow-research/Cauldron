"""Input payload packing for Frostbite models."""

from __future__ import annotations

import base64
import json
import struct
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from .manifest import load_manifest
from .schema import SCHEMA_IDS, parse_hash32, schema_hash32
from .util import product


FBH1_MAGIC = 0x31484246  # "FBH1"
FBH1_VERSION = 1
FBH1_HEADER_LEN = 32
FBH_FLAG_HAS_CRC32 = 1 << 0
FBH_FLAG_HAS_SCHEMA_HASH = 1 << 1


_DTYPE_STRUCT = {
    "i32": "i",
    "u32": "I",
    "i16": "h",
    "i8": "b",
    "u8": "B",
    "f32": "f",
}


def _crc32(data: bytes) -> int:
    crc = 0xFFFF_FFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xEDB8_8320
            else:
                crc >>= 1
    return (~crc) & 0xFFFF_FFFF


def _flatten(values: Any) -> List[Any]:
    if isinstance(values, list):
        if values and isinstance(values[0], list):
            flat: List[Any] = []
            for row in values:
                if not isinstance(row, list):
                    raise ValueError("nested list must contain lists")
                flat.extend(row)
            return flat
        return values
    return [values]


def _pack_values(dtype: str, values: Iterable[Any]) -> bytes:
    values_list = list(values)
    if not values_list:
        return b""
    if dtype == "f16":
        try:
            import numpy as np  # type: ignore
        except ImportError as exc:
            raise ImportError("numpy is required to pack f16 values") from exc
        arr = np.array(values_list, dtype=np.float16)
        return arr.tobytes()
    fmt = _DTYPE_STRUCT.get(dtype)
    if fmt is None:
        raise ValueError(f"Unsupported dtype: {dtype}")
    return struct.pack("<" + fmt * len(values_list), *values_list)


def _schema_type(manifest: Dict[str, Any]) -> str:
    schema = manifest.get("schema")
    if not isinstance(schema, dict):
        raise ValueError("schema table missing")
    stype = schema.get("type")
    if stype not in SCHEMA_IDS:
        raise ValueError("schema.type must be vector, time_series, graph, or custom")
    return stype


def _schema_id(stype: str) -> int:
    return SCHEMA_IDS[stype]


def load_payload_from_path(path: Path) -> Any:
    if str(path) == "-":
        import sys

        data = json.loads(sys.stdin.read())
        return data
    data = json.loads(path.read_text())
    if isinstance(data, dict):
        for key in ("input", "data", "payload"):
            if key in data:
                return data[key]
    return data


def _pack_vector(manifest: Dict[str, Any], payload: Any) -> bytes:
    schema = manifest["schema"]["vector"]
    dtype = schema.get("input_dtype")
    shape = schema.get("input_shape")
    if not isinstance(shape, list):
        raise ValueError("schema.vector.input_shape must be a list")
    expected = product(shape)
    flat = _flatten(payload)
    if len(flat) != expected:
        raise ValueError(f"vector payload length mismatch: {len(flat)} != {expected}")
    return _pack_values(dtype, flat)


def _pack_time_series(manifest: Dict[str, Any], payload: Any) -> bytes:
    schema = manifest["schema"]["time_series"]
    dtype = schema.get("input_dtype")
    window = schema.get("window")
    features = schema.get("features")
    if not isinstance(window, int) or not isinstance(features, int):
        raise ValueError("schema.time_series window/features required")

    if isinstance(payload, list) and payload and isinstance(payload[0], list):
        if len(payload) != window:
            raise ValueError("time_series window length mismatch")
        flat: List[Any] = []
        for row in payload:
            if not isinstance(row, list) or len(row) != features:
                raise ValueError("time_series row length mismatch")
            flat.extend(row)
    else:
        flat = _flatten(payload)

    expected = window * features
    if len(flat) != expected:
        raise ValueError(f"time_series payload length mismatch: {len(flat)} != {expected}")
    return _pack_values(dtype, flat)


def _normalize_edges(edges: Any) -> List[Tuple[int, int]]:
    if isinstance(edges, list) and edges and isinstance(edges[0], list):
        out: List[Tuple[int, int]] = []
        for pair in edges:
            if not isinstance(pair, list) or len(pair) != 2:
                raise ValueError("edge pairs must be [src, dst]")
            out.append((int(pair[0]), int(pair[1])))
        return out
    if isinstance(edges, list):
        if len(edges) % 2 != 0:
            raise ValueError("edge list length must be even")
        out = []
        for i in range(0, len(edges), 2):
            out.append((int(edges[i]), int(edges[i + 1])))
        return out
    raise ValueError("edges must be a list")


def _pick_payload(payload: Dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        if key in payload:
            return payload[key]
    return None


def _pack_graph(manifest: Dict[str, Any], payload: Dict[str, Any]) -> bytes:
    schema = manifest["schema"]["graph"]
    dtype = schema.get("input_dtype")
    node_dim = schema.get("node_feature_dim")
    edge_dim = schema.get("edge_feature_dim")
    max_nodes = schema.get("max_nodes")
    max_edges = schema.get("max_edges")
    if not isinstance(node_dim, int) or not isinstance(edge_dim, int):
        raise ValueError("schema.graph node_feature_dim/edge_feature_dim required")
    if not isinstance(max_nodes, int) or not isinstance(max_edges, int):
        raise ValueError("schema.graph max_nodes/max_edges required")

    nodes = _pick_payload(payload, ["nodes", "node_features"])
    edges = _pick_payload(payload, ["edges", "edge_index", "edge_indices"])
    edge_features = _pick_payload(payload, ["edge_features", "edge_attrs"])

    if nodes is None or edges is None:
        raise ValueError("graph payload requires nodes and edges")

    if not isinstance(nodes, list):
        raise ValueError("nodes must be a list")

    node_count = payload.get("node_count")
    if node_count is None:
        node_count = len(nodes)
    if not isinstance(node_count, int) or node_count < 0:
        raise ValueError("node_count must be a non-negative integer")
    if node_count > max_nodes:
        raise ValueError("node_count exceeds schema.graph.max_nodes")

    if len(nodes) != node_count:
        raise ValueError("node_count does not match nodes length")

    flat_nodes: List[Any] = []
    for row in nodes:
        if not isinstance(row, list) or len(row) != node_dim:
            raise ValueError("node feature row length mismatch")
        flat_nodes.extend(row)

    edge_pairs = _normalize_edges(edges)
    edge_count = payload.get("edge_count")
    if edge_count is None:
        edge_count = len(edge_pairs)
    if not isinstance(edge_count, int) or edge_count < 0:
        raise ValueError("edge_count must be a non-negative integer")
    if edge_count > max_edges:
        raise ValueError("edge_count exceeds schema.graph.max_edges")
    if len(edge_pairs) != edge_count:
        raise ValueError("edge_count does not match edges length")

    flat_edges: List[int] = []
    for src, dst in edge_pairs:
        flat_edges.extend([src, dst])

    flat_edge_features: List[Any] = []
    if edge_dim > 0:
        if edge_features is None:
            raise ValueError("edge_features required for edge_feature_dim > 0")
        if not isinstance(edge_features, list) or len(edge_features) != edge_count:
            raise ValueError("edge_features length mismatch")
        for row in edge_features:
            if not isinstance(row, list) or len(row) != edge_dim:
                raise ValueError("edge feature row length mismatch")
            flat_edge_features.extend(row)

    buf = bytearray()
    buf.extend(struct.pack("<IIII", node_count, edge_count, 0, 0))
    buf.extend(_pack_values(dtype, flat_nodes))
    if flat_edges:
        buf.extend(struct.pack("<" + "I" * len(flat_edges), *flat_edges))
    if flat_edge_features:
        buf.extend(_pack_values(dtype, flat_edge_features))
    return bytes(buf)


def _custom_payload_from_json(payload: Any) -> bytes:
    if isinstance(payload, dict):
        if "payload_hex" in payload:
            hex_str = str(payload["payload_hex"])
            if hex_str.startswith("0x"):
                hex_str = hex_str[2:]
            return bytes.fromhex(hex_str)
        if "payload_base64" in payload:
            return base64.b64decode(str(payload["payload_base64"]))
        if "payload" in payload:
            return _custom_payload_from_json(payload["payload"])
    if isinstance(payload, list):
        return bytes(int(b) & 0xFF for b in payload)
    if isinstance(payload, str):
        if payload.startswith("0x"):
            return bytes.fromhex(payload[2:])
        try:
            return base64.b64decode(payload)
        except Exception as exc:
            raise ValueError("custom payload string must be hex or base64") from exc
    raise ValueError("unsupported custom payload format")


def _pack_custom(manifest: Dict[str, Any], payload: Any) -> bytes:
    schema = manifest["schema"]["custom"]
    input_size = schema.get("input_blob_size")
    if not isinstance(input_size, int) or input_size <= 0:
        raise ValueError("schema.custom.input_blob_size required")
    if isinstance(payload, (bytes, bytearray)):
        data = bytes(payload)
    else:
        data = _custom_payload_from_json(payload)
    if len(data) < input_size:
        raise ValueError("custom payload smaller than input_blob_size")
    return data


def pack_payload(manifest: Dict[str, Any], payload: Any) -> bytes:
    stype = _schema_type(manifest)
    if stype == "vector":
        return _pack_vector(manifest, payload)
    if stype == "time_series":
        return _pack_time_series(manifest, payload)
    if stype == "graph":
        if not isinstance(payload, dict):
            raise ValueError("graph payload must be an object")
        return _pack_graph(manifest, payload)
    if stype == "custom":
        return _pack_custom(manifest, payload)
    raise ValueError("unsupported schema type")


def pack_fbh1_header(
    payload: bytes,
    schema_type: str,
    include_crc: bool,
    include_schema_hash: bool,
    schema_hash_value: int,
) -> bytes:
    flags = 0
    crc_val = 0
    if include_crc:
        flags |= FBH_FLAG_HAS_CRC32
        crc_val = _crc32(payload)
    if include_schema_hash:
        flags |= FBH_FLAG_HAS_SCHEMA_HASH
    schema_id = _schema_id(schema_type)
    header = struct.pack(
        "<IHHIIIIII",
        FBH1_MAGIC,
        FBH1_VERSION,
        flags,
        FBH1_HEADER_LEN,
        schema_id,
        len(payload),
        crc_val,
        schema_hash_value if include_schema_hash else 0,
        0,
    )
    return header


def resolve_schema_hash(manifest: Dict[str, Any], mode: str) -> int:
    if mode == "none":
        return 0
    if mode == "auto":
        return schema_hash32(manifest)
    if mode == "manifest":
        custom = manifest.get("schema", {}).get("custom", {})
        value = custom.get("schema_hash32")
        if isinstance(value, str):
            return parse_hash32(value)
        return 0
    raise ValueError("schema-hash mode must be auto, manifest, or none")


def pack_input(
    manifest_path: Path,
    payload: Any,
    include_header: bool,
    include_crc: bool,
    schema_hash_mode: str,
) -> bytes:
    manifest = load_manifest(manifest_path)
    payload_bytes = pack_payload(manifest, payload)
    if not include_header:
        return payload_bytes
    stype = _schema_type(manifest)
    schema_hash_value = resolve_schema_hash(manifest, schema_hash_mode)
    include_schema_hash = schema_hash_mode != "none" and schema_hash_value != 0
    header = pack_fbh1_header(
        payload_bytes,
        stype,
        include_crc=include_crc,
        include_schema_hash=include_schema_hash,
        schema_hash_value=schema_hash_value,
    )
    return header + payload_bytes


def write_input(
    manifest_path: Path,
    payload: Any,
    output_path: Path,
    include_header: bool,
    include_crc: bool,
    schema_hash_mode: str,
) -> Path:
    data = pack_input(
        manifest_path,
        payload,
        include_header=include_header,
        include_crc=include_crc,
        schema_hash_mode=schema_hash_mode,
    )
    output_path.write_bytes(data)
    return output_path
